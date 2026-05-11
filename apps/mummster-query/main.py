import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pdf_export import generate_pdf
from pipeline import query_store, run_query_pipeline

LOG_DIR = os.getenv("LOG_DIR", "/mnt/artemis-data/logs/mummster-query")
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/mummster-query.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="MummSTER Query Interface", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Holds pending questions until the SSE stream endpoint consumes them.
_pending: dict[str, str] = {}


class QueryRequest(BaseModel):
    question: str


class ExportRequest(BaseModel):
    chart_image: str | None = None


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/query")
async def create_query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    query_id = str(uuid.uuid4())
    _pending[query_id] = req.question.strip()
    logger.info("Query created: %s — %r", query_id[:8], req.question[:80])
    return {"query_id": query_id}


@app.get("/stream/{query_id}")
async def stream_query(query_id: str):
    question = _pending.pop(query_id, None)
    if question is None:
        raise HTTPException(404, "Query not found")

    async def generate():
        try:
            async for chunk in run_query_pipeline(query_id, question):
                yield chunk
        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=True)
            yield f"event: pipeline_error\ndata: {json.dumps({'message': str(exc)})}\n\n"

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
        headers={"Content-Disposition": f'attachment; filename="mummster-{query_id[:8]}.pdf"'},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
