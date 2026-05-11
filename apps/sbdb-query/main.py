import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pdf_export import generate_pdf
from pipeline import query_store, run_query_pipeline

LOG_DIR = os.getenv("LOG_DIR", "/mnt/artemis-data/logs/sbdb-query")
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/sbdb-query.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SBDB AI Query", docs_url=None, redoc_url=None)

allow_origins = [
    "https://sbdb-ai.theronlab.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class QueryRequest(BaseModel):
    question: str


class ExportRequest(BaseModel):
    chart_image: str | None = None


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


def _parse_pipeline_chunk(chunk: str):
    """Parse a pipeline SSE chunk ('event: X\\ndata: {...}\\n\\n') into (event_type, data_dict)."""
    event_type = None
    data_str = None
    for line in chunk.split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:].strip()
    if not event_type or not data_str:
        return None, None
    try:
        return event_type, json.loads(data_str)
    except json.JSONDecodeError:
        return None, None


def _transform_to_client_sse(event_type: str, data: dict) -> str:
    """Transform pipeline SSE events to the flat data:{type,...} format AskPanel.js expects."""
    if event_type == "chart":
        return f"data: {json.dumps({'type': 'chart', 'spec': data})}\n\n"
    if event_type == "refinement":
        return f"data: {json.dumps({'type': 'followup', 'question': data.get('suggestion', '')})}\n\n"
    if event_type == "complete":
        return f"data: {json.dumps({'type': 'done'})}\n\n"
    if event_type == "pipeline_error":
        return f"data: {json.dumps({'type': 'error', 'message': data.get('message', '')})}\n\n"
    if event_type == "results":
        columns = data.get("columns", [])
        dict_rows = data.get("rows", [])
        array_rows = [[row.get(c) for c in columns] for row in dict_rows]
        return f"data: {json.dumps({'type': 'results', 'columns': columns, 'rows': array_rows, 'row_count': data.get('row_count', 0)})}\n\n"
    merged = {"type": event_type, **data}
    return f"data: {json.dumps(merged)}\n\n"


@app.post("/query")
async def create_query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    query_id = str(uuid.uuid4())
    question = req.question.strip()
    logger.info("Query: %s — %r", query_id[:8], question[:80])

    async def generate():
        try:
            async for chunk in run_query_pipeline(query_id, question):
                event_type, data = _parse_pipeline_chunk(chunk)
                if event_type is not None:
                    yield _transform_to_client_sse(event_type, data)
                else:
                    yield chunk
        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/export/{query_id}")
async def export_pdf(query_id: str, req: ExportRequest):
    result = query_store.get(query_id)
    if not result:
        raise HTTPException(404, "Query result not found — results expire when the server restarts")
    pdf_bytes = generate_pdf(result, req.chart_image)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="sbdb-{query_id[:8]}.pdf"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
