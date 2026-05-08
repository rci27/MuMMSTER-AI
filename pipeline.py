import json
import logging
import os
import re
from typing import AsyncGenerator

import anthropic
import duckdb

from schema import DB_PATH, get_system_prompt

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
ANTHROPIC_KEY_PATH = os.getenv("ANTHROPIC_KEY_PATH", "/etc/artemis-secrets/anthropic.key")

# Completed query results stored for PDF export; keyed by query_id.
query_store: dict[str, dict] = {}

# Conversation history — last MAX_HISTORY exchanges, shared across all requests
# (single-user homelab app; no per-session isolation needed).
# Each entry: {"question": str, "sql": str, "interpretation": str}
_conversation_history: list[dict] = []
MAX_HISTORY = 5

# Questions about placement, win counts, or average finish — should never use parsed_scores.
_PLACEMENT_QUESTION_RE = re.compile(
    r'\b(place|placement|finish|finishing|rank(ing)?|win|won|wins|first[\s\-]prize|'
    r'average[\s\-]finish|best[\s\-]finish|most[\s\-](wins|first|decorated)|'
    r'how[\s\-](many|often)[\s\-](did|has|have)|how[\s\-]did[\s\-]\w+[\s\-](do|finish|place)|'
    r'prize[\s\-]count|placement[\s\-]history|ever[\s\-]won|times[\s\-]won)\b',
    re.IGNORECASE,
)

# Signals that a question needs multi-query deep analysis rather than a single SQL lookup.
_DEEP_ANALYSIS_RE = re.compile(
    r'\b(trend|compar|histor|improv|regress|percentile|statistic|over[\s\-]?time|'
    r'year[\s\-]?by[\s\-]?year|decade|rate\s+of|average|mean\b|better\s+than|'
    r'worse\s+than|\bvs\.?\b|versus|how\s+has|how\s+have|how\s+did|'
    r'analys|rank(ing)?s?\s+over|field\s+average|relative\s+to)\b',
    re.IGNORECASE,
)

# Signals that a question is about marching order / draw position / performance slot.
_MARCHING_ORDER_RE = re.compile(
    r'\b(march(ing)?\s+order|march(ing)?\s+(position|slot|number|sequence)|'
    r'draw(ing)?\s+(position|order|slot|number)|performance\s+(order|slot|position)|'
    r'draw\s+number|marching\s+early|marching\s+late|first\s+to\s+march|'
    r'last\s+to\s+march|position\s+in\s+(the\s+)?parade|slot\s+in\s+(the\s+)?order|'
    r'order\s+of\s+performance|when\s+they\s+march)\b',
    re.IGNORECASE,
)

_MARCHING_DECOMPOSE_EXTRA = (
    "\n\nIMPORTANT — This question involves marching order / draw position effects. "
    "The decomposition MUST include:\n"
    "1. A tertile analysis query: use NTILE(3) OVER (PARTITION BY year ORDER BY marching_order) "
    "to group bands into early/middle/late thirds and compute average scores per tertile. "
    "This is the primary analysis — not optional.\n"
    "2. A raw marching_order vs. score query (select marching_order, total_score) for "
    "reference, so the synthesis can demonstrate why linear analysis alone is insufficient.\n"
    "Do NOT rely solely on a simple correlation or regression — the tertile grouping query "
    "is required and must be one of the numbered sub-questions."
)

_MARCHING_SYNTHESIS_EXTRA = (
    "\n\nIMPORTANT — This question involves marching order effects, which are non-linear. "
    "Your synthesis MUST:\n"
    "1. Lead with the tertile analysis as the primary finding — show how early/middle/late "
    "tertiles compare on average scores.\n"
    "2. Explicitly explain that a simple linear correlation between marching position and "
    "score would understate or miss this effect, and why tertile grouping is the correct method.\n"
    "3. State that this is a known and documented phenomenon in string band competition: "
    "later-marching bands score systematically better, likely due to judge calibration.\n"
    "4. Note the practical implication: a high placement from an early draw slot is a "
    "stronger result than the same placement from a late slot."
)


def _needs_deep_analysis(question: str) -> bool:
    return len(question) > 40 and bool(_DEEP_ANALYSIS_RE.search(question))


def _involves_marching_order(question: str) -> bool:
    return bool(_MARCHING_ORDER_RE.search(question))


def _load_api_key() -> str:
    with open(ANTHROPIC_KEY_PATH) as f:
        return f.read().strip()


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _df_to_rows(df) -> list[dict]:
    """Serialize a DuckDB DataFrame to a JSON-safe list of dicts."""
    return json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))


def _sql_messages(history: list[dict], question: str) -> list[dict]:
    """Build the messages array for the SQL generation step, including prior exchanges."""
    msgs = []
    for item in history:
        msgs.append({
            "role": "user",
            "content": (
                f"Generate a DuckDB SQL query to answer this question:\n\n"
                f"{item['question']}\n\n"
                "Return ONLY the SQL statement."
            ),
        })
        msgs.append({"role": "assistant", "content": item["sql"]})
    msgs.append({
        "role": "user",
        "content": (
            f"Generate a DuckDB SQL query to answer this question:\n\n{question}\n\n"
            "Return ONLY the SQL statement. No explanation, no markdown fences."
        ),
    })
    return msgs


def _interp_messages(history: list[dict], question: str, sql: str,
                     row_count: int, preview: list[dict]) -> list[dict]:
    """Build the messages array for the interpretation step, including prior exchanges."""
    msgs = []
    for item in history:
        msgs.append({"role": "user", "content": item["question"]})
        msgs.append({"role": "assistant", "content": item["interpretation"]})
    follow_up_note = (
        " Reference relevant findings from the conversation history if this is a follow-up question."
        if history else ""
    )
    shown = preview[:30]
    truncation_note = (
        f" The table above shows the top 30 results. "
        f"The full dataset of **{row_count} rows** was used for all calculations — "
        f"no data is missing. Do NOT warn about missing years or data gaps due to display truncation."
        if row_count > 30 else ""
    )
    msgs.append({
        "role": "user",
        "content": (
            "You are a data analyst for the MummSTER database of Philadelphia Mummers Parade "
            "string band competition history.\n\n"
            f"Question: {question}\n"
            f"SQL used: {sql}\n"
            f"Results ({row_count} rows, showing up to 30): "
            f"{json.dumps({'sample': shown, 'total_rows': row_count})}\n\n"
            "Write a plain English interpretation (3–5 sentences). "
            "Use markdown formatting — **bold** for key findings, bullet lists for multiple points. "
            "Be specific about what the data shows. "
            "Note era boundaries or data gaps only if they reflect real absences in the underlying data, "
            "not display truncation."
            + truncation_note
            + follow_up_note
        ),
    })
    return msgs


# ── Multi-query deep analysis ─────────────────────────────────────────────────

async def _decompose_question(
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
    question: str,
    extra_context: str = "",
) -> tuple[list[str], str]:
    """Decompose a complex question into 3–5 targeted sub-questions."""
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=5000,
        thinking={"type": "enabled", "budget_tokens": 3000},
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                f"You are planning a multi-query analysis for this complex question:\n\n"
                f"{question}\n\n"
                "Decompose it into 3–5 specific sub-questions, each answerable by a single SQL query. "
                "Think about what data is needed: year-by-year scores, field averages, improvement rates, "
                "percentile positions, comparative rankings, etc."
                + extra_context + "\n\n"
                "Return ONLY a JSON array of strings, e.g.:\n"
                '["What were Band X\'s scores each year?", "What was the field average by year?", ...]\n'
                "No explanation, no markdown fences — only the JSON array."
            ),
        }],
    )
    thinking_text = ""
    result_text = ""
    for block in resp.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            result_text = block.text.strip()

    if result_text.startswith("```"):
        result_text = "\n".join(
            l for l in result_text.splitlines() if not l.startswith("```")
        ).strip()

    sub_questions = json.loads(result_text)
    if not isinstance(sub_questions, list) or not sub_questions:
        raise ValueError(f"Decomposition returned unexpected format: {result_text!r}")

    return sub_questions[:5], thinking_text


async def _run_sub_query_sql(
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
    sub_question: str,
) -> tuple[str, str]:
    """Generate SQL for a single sub-question. Returns (sql, thinking_text)."""
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "enabled", "budget_tokens": 2000},
        system=system_prompt,
        messages=_sql_messages([], sub_question),
    )
    thinking_text = ""
    sql = ""
    for block in resp.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            sql = block.text.strip()

    if sql.startswith("```"):
        sql = "\n".join(l for l in sql.splitlines() if not l.startswith("```")).strip()

    return sql, thinking_text


async def _synthesize_results(
    client: anthropic.AsyncAnthropic,
    question: str,
    sub_results: list[dict],
    extra_context: str = "",
) -> str:
    """Synthesize multiple sub-query results into a structured analytical narrative."""
    data_blocks = []
    for i, r in enumerate(sub_results, 1):
        block = [f"### Sub-query {i}: {r['question']}"]
        if r["error"]:
            block.append(f"**Error:** {r['error']}")
        else:
            block.append(f"**{r['row_count']} rows returned**")
            if r["rows"]:
                block.append(json.dumps(r["rows"][:30], indent=2))
        data_blocks.append("\n".join(block))

    resp = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": (
                "You are a research analyst for the MummSTER database of Philadelphia Mummers Parade "
                "string band competition history. You have run multiple SQL queries to answer a "
                "complex question. Synthesize all results into a structured analytical response.\n\n"
                f"**Original question:** {question}\n\n"
                "**Query results:**\n\n" + "\n\n".join(data_blocks) + "\n\n"
                "Write your response as a research analyst would. Structure it with these markdown sections:\n\n"
                "## Overall Verdict\n"
                "Direct answer to the question in 1–2 sentences.\n\n"
                "## Supporting Evidence\n"
                "Specific numbers from the data. Use a table if comparing multiple bands or years.\n\n"
                "## Competitive Context\n"
                "How this compares to the field — field averages, percentile position, peer comparison.\n\n"
                "## Notable Findings\n"
                "Anything surprising, a standout year, an anomaly, or a trend worth highlighting.\n\n"
                "## Bottom Line\n"
                "One plain-English sentence a Mummers fan without stats knowledge would understand.\n\n"
                "Use **bold** for key numbers, bullet lists for multiple points, and tables for comparative data. "
                "Note any data gaps or era-boundary caveats. Be specific — cite actual numbers from the results."
                + extra_context
            ),
        }],
    )
    return resp.content[0].text.strip()


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_query_pipeline(query_id: str, question: str) -> AsyncGenerator[str, None]:
    client: anthropic.AsyncAnthropic | None = None

    try:
        try:
            api_key = _load_api_key()
        except OSError:
            yield _sse("pipeline_error", {"message": "Anthropic API key not found. Place key at " + ANTHROPIC_KEY_PATH})
            return

        client = anthropic.AsyncAnthropic(api_key=api_key)
        system_prompt = get_system_prompt()

        if _needs_deep_analysis(question) or _involves_marching_order(question):
            async for chunk in _run_multi_query_pipeline(query_id, question, client, system_prompt):
                yield chunk
        else:
            async for chunk in _run_single_query_pipeline(query_id, question, client, system_prompt):
                yield chunk

    except Exception as exc:
        logger.error("Unhandled pipeline error: %s", exc, exc_info=True)
        yield _sse("pipeline_error", {"message": str(exc)})


async def _run_single_query_pipeline(
    query_id: str,
    question: str,
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
) -> AsyncGenerator[str, None]:
    conn: duckdb.DuckDBPyConnection | None = None
    try:
        # ------------------------------------------------------------------
        # Step 1: Generate SQL with extended thinking
        # ------------------------------------------------------------------
        yield _sse("status", {"step": 1, "message": "Generating SQL…"})

        sql_parts: list[str] = []
        async with client.messages.stream(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "enabled", "budget_tokens": 5000},
            system=system_prompt,
            messages=_sql_messages(_conversation_history, question),
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta":
                        yield _sse("thinking_stream", {"text": event.delta.thinking})
                    elif event.delta.type == "text_delta":
                        sql_parts.append(event.delta.text)

        sql = "".join(sql_parts).strip()
        if sql.startswith("```"):
            sql = "\n".join(
                line for line in sql.splitlines()
                if not line.startswith("```")
            ).strip()

        yield _sse("sql", {"sql": sql})

        # ------------------------------------------------------------------
        # Step 2: Validate + auto-fix (max 2 fix attempts)
        # ------------------------------------------------------------------
        yield _sse("status", {"step": 2, "message": "Validating SQL…"})

        conn = duckdb.connect(DB_PATH, read_only=True)
        validated_sql: str | None = None
        last_error: str | None = None

        for attempt in range(3):
            if attempt > 0:
                yield _sse("status", {"step": 2, "message": f"Auto-fixing SQL (attempt {attempt}/2)…"})
                fix_resp = await client.messages.create(
                    model=MODEL,
                    max_tokens=4000,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": f"Generate DuckDB SQL for: {question}\n\nSQL only."},
                        {"role": "assistant", "content": sql},
                        {"role": "user", "content": f"That query failed:\n{last_error}\n\nFix it. Return ONLY the corrected SQL."},
                    ],
                )
                sql = fix_resp.content[0].text.strip()
                if sql.startswith("```"):
                    sql = "\n".join(l for l in sql.splitlines() if not l.startswith("```")).strip()
                yield _sse("sql_fix", {"attempt": attempt, "sql": sql})

            try:
                conn.execute(f"EXPLAIN {sql}")
                validated_sql = sql
                yield _sse("validation", {"status": "ok"})
                break
            except Exception as exc:
                last_error = str(exc)
                yield _sse("validation", {"status": "error", "error": last_error, "attempt": attempt})

        if validated_sql is None:
            yield _sse("pipeline_error", {"message": f"SQL failed after 2 fix attempts. Last error: {last_error}"})
            return

        # ------------------------------------------------------------------
        # Step 3: Execute
        # ------------------------------------------------------------------
        yield _sse("status", {"step": 3, "message": "Executing query…"})
        try:
            df = conn.execute(validated_sql).fetchdf()
            columns = list(df.columns)
            rows = _df_to_rows(df)
            row_count = len(rows)
        except Exception as exc:
            yield _sse("pipeline_error", {"message": f"Execution failed: {exc}"})
            return

        yield _sse("results", {"columns": columns, "rows": rows, "row_count": row_count})

        # Post-execution sanity checks
        used_parsed = "parsed_scores" in validated_sql.lower()

        # Check 1: placement/win-count question that touched parsed_scores — wrong even
        # if rows were returned, because parsed_scores omits ~38 years with no PDFs.
        if used_parsed and bool(_PLACEMENT_QUESTION_RE.search(question)):
            yield _sse("warning", {
                "message": (
                    "Warning: this query used parsed_scores for a placement or win-count question. "
                    "parsed_scores only covers years with parseable PDF point sheets (~21 of 59 years). "
                    "Win counts and average finish calculated from parsed_scores will be incorrect — "
                    "they silently omit years with no PDF coverage. "
                    "sbdb_main_results covers all 1,960 competition records and is the correct table."
                )
            })

        # Check 2: zero rows on a year-specific question that used parsed_scores —
        # likely the year has no PDF coverage (e.g. 1964, 1967, 1999, 2001, pre-2014).
        if row_count == 0 and used_parsed:
            has_year = bool(re.search(r'\b(19|20)\d{2}\b', question))
            if has_year:
                yield _sse("warning", {
                    "message": (
                        "Zero rows returned. The query used parsed_scores, which only covers "
                        "years with extracted PDF scoring data. The requested year likely has "
                        "no PDF coverage. For placement, results, or total points questions, "
                        "sbdb_main_results covers all years including 1964, 1967, 1999, and 2001."
                    )
                })

        # ------------------------------------------------------------------
        # Step 4: Interpret results
        # ------------------------------------------------------------------
        yield _sse("status", {"step": 4, "message": "Interpreting results…"})

        interp_resp = await client.messages.create(
            model=MODEL,
            max_tokens=1500,
            messages=_interp_messages(
                _conversation_history, question, validated_sql, row_count, rows
            ),
        )
        interpretation = interp_resp.content[0].text.strip()
        yield _sse("interpretation", {"text": interpretation})

        # ------------------------------------------------------------------
        # Step 5: Chart spec (if appropriate)
        # ------------------------------------------------------------------
        yield _sse("status", {"step": 5, "message": "Checking for chart opportunity…"})
        chart_spec: dict | None = None

        if 0 < row_count <= 100:
            chart_resp = await client.messages.create(
                model=MODEL,
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": (
                        f"MummSTER query results:\n"
                        f"Question: {question}\n"
                        f"Columns: {columns}\n"
                        f"Rows ({row_count}): {json.dumps(rows[:30])}\n\n"
                        "Should a Chart.js chart visualize this data? "
                        'If yes, return ONLY a JSON object: {"type":"bar"|"line"|"pie","labels":[...],"datasets":[{"label":"...","data":[...]}],"title":"..."}\n'
                        "If no chart is appropriate, return exactly: null"
                    ),
                }],
            )
            chart_text = chart_resp.content[0].text.strip()
            if chart_text.lower() not in ("null", "none", ""):
                try:
                    chart_spec = json.loads(chart_text)
                    yield _sse("chart", chart_spec)
                except json.JSONDecodeError:
                    logger.warning("Chart spec was not valid JSON, skipping chart")

        # ------------------------------------------------------------------
        # Step 6: Refinement suggestion
        # ------------------------------------------------------------------
        yield _sse("status", {"step": 6, "message": "Generating refinement suggestion…"})
        refine_resp = await client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f'Mummers Parade string band data question: "{question}"\n\n'
                    "Suggest ONE specific follow-up question that would give more insight. "
                    "One sentence, phrased as a question."
                ),
            }],
        )
        refinement = refine_resp.content[0].text.strip()
        yield _sse("refinement", {"suggestion": refinement})

        # ------------------------------------------------------------------
        # Append to conversation history
        # ------------------------------------------------------------------
        _conversation_history.append({
            "question": question,
            "sql": validated_sql,
            "interpretation": interpretation,
        })
        if len(_conversation_history) > MAX_HISTORY:
            del _conversation_history[:-MAX_HISTORY]

        query_store[query_id] = {
            "question": question,
            "sql": validated_sql,
            "columns": columns,
            "rows": rows,
            "row_count": row_count,
            "interpretation": interpretation,
            "refinement": refinement,
            "chart_spec": chart_spec,
        }

        yield _sse("complete", {"query_id": query_id})

    finally:
        if conn:
            conn.close()


async def _run_multi_query_pipeline(
    query_id: str,
    question: str,
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
) -> AsyncGenerator[str, None]:
    conn: duckdb.DuckDBPyConnection | None = None
    try:
        # ------------------------------------------------------------------
        # Step 1: Decompose question into sub-queries
        # ------------------------------------------------------------------
        marching_question = _involves_marching_order(question)
        decompose_extra = _MARCHING_DECOMPOSE_EXTRA if marching_question else ""
        synthesis_extra = _MARCHING_SYNTHESIS_EXTRA if marching_question else ""

        yield _sse("status", {"step": "decompose", "message": "Decomposing into sub-queries…"})

        try:
            sub_questions, decompose_thinking = await _decompose_question(
                client, system_prompt, question, extra_context=decompose_extra
            )
        except Exception as exc:
            yield _sse("pipeline_error", {"message": f"Decomposition failed: {exc}"})
            return

        if decompose_thinking:
            yield _sse("thinking_stream", {"text": decompose_thinking})

        yield _sse("status", {
            "step": "decompose_done",
            "message": f"Identified {len(sub_questions)} sub-queries",
        })

        # ------------------------------------------------------------------
        # Step 2: Generate SQL and execute each sub-query
        # ------------------------------------------------------------------
        conn = duckdb.connect(DB_PATH, read_only=True)
        sub_results: list[dict] = []

        for i, sub_q in enumerate(sub_questions, 1):
            yield _sse("status", {
                "step": f"sub_{i}",
                "message": f"Sub-query {i}/{len(sub_questions)}: {sub_q[:70]}…",
            })

            try:
                sql, sql_thinking = await _run_sub_query_sql(client, system_prompt, sub_q)
            except Exception as exc:
                sub_results.append({
                    "question": sub_q, "sql": "", "columns": [],
                    "rows": [], "row_count": 0, "error": f"SQL generation failed: {exc}",
                })
                continue

            if sql_thinking:
                yield _sse("thinking_stream", {"text": sql_thinking})

            yield _sse("sql", {"sql": sql, "label": f"Sub-query {i}: {sub_q[:50]}"})

            try:
                conn.execute(f"EXPLAIN {sql}")
                df = conn.execute(sql).fetchdf()
                rows = _df_to_rows(df)
                sub_results.append({
                    "question": sub_q,
                    "sql": sql,
                    "columns": list(df.columns),
                    "rows": rows,
                    "row_count": len(rows),
                    "error": None,
                })
            except Exception as exc:
                sub_results.append({
                    "question": sub_q, "sql": sql, "columns": [],
                    "rows": [], "row_count": 0, "error": str(exc),
                })

        # ------------------------------------------------------------------
        # Step 3: Synthesize all results into a structured narrative
        # ------------------------------------------------------------------
        yield _sse("status", {"step": "synthesize", "message": "Synthesizing results into analysis…"})

        try:
            synthesis = await _synthesize_results(client, question, sub_results, extra_context=synthesis_extra)
        except Exception as exc:
            yield _sse("pipeline_error", {"message": f"Synthesis failed: {exc}"})
            return

        yield _sse("interpretation", {"text": synthesis})

        # ------------------------------------------------------------------
        # Step 4: Refinement suggestion
        # ------------------------------------------------------------------
        yield _sse("status", {"step": "refine", "message": "Generating refinement suggestion…"})
        refine_resp = await client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f'Complex Mummers Parade analysis question: "{question}"\n\n'
                    "Suggest ONE specific follow-up analysis question that would deepen this insight. "
                    "One sentence, phrased as a question."
                ),
            }],
        )
        refinement = refine_resp.content[0].text.strip()
        yield _sse("refinement", {"suggestion": refinement})

        # ------------------------------------------------------------------
        # Store result for PDF export
        # ------------------------------------------------------------------
        combined_sql = "\n\n".join(
            f"-- Sub-query {i}: {r['question']}\n{r['sql']}"
            for i, r in enumerate(sub_results, 1)
            if r["sql"]
        )
        last_good = next((r for r in reversed(sub_results) if not r["error"]), {})

        query_store[query_id] = {
            "question": question,
            "sql": combined_sql,
            "columns": last_good.get("columns", []),
            "rows": last_good.get("rows", []),
            "row_count": last_good.get("row_count", 0),
            "interpretation": synthesis,
            "refinement": refinement,
            "chart_spec": None,
        }

        # Append to conversation history
        _conversation_history.append({
            "question": question,
            "sql": combined_sql,
            "interpretation": synthesis,
        })
        if len(_conversation_history) > MAX_HISTORY:
            del _conversation_history[:-MAX_HISTORY]

        yield _sse("complete", {"query_id": query_id})

    finally:
        if conn:
            conn.close()
