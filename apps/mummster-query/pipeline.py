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

# Signals that a question is about a person's history, tenure, or profile.
_PERSON_TENURE_RE = re.compile(
    r'\b(captain|tenure|how\s+long\s+(was|did|has|have)|served\s+(as|with)|led\s+the|'
    r'tell\s+me\s+about|profile|career|legacy|contribution|'
    r'years?\s+as\s+(captain|leader|director)|'
    r'inducted|hall\s+of\s+fame|lifetime\s+achievement|achievement\s+award|'
    r'officer\s+of\s+the\s+year|award\s+of\s+distinction|presidents?\s+award|'
    r'when\s+did\s+\w+\s+(serve|captain|lead|win|join)|'
    r'what\s+did\s+\w+\s+(win|accomplish|achieve|do))\b',
    re.IGNORECASE,
)

_PERSON_TENURE_DECOMPOSE_EXTRA = (
    "\n\nIMPORTANT — This question is about a person's history, tenure, or contribution. "
    "The decomposition MUST include ALL of the following sub-questions:\n"
    "1. Find the person in sbdb_captains using LIKE matching — retrieve every year they "
    "appear and which band(s) they were associated with.\n"
    "2. Find that band's placement in sbdb_main_results for each of those years "
    "(JOIN on Year + band name).\n"
    "3. Find the band's historical average placement across ALL years for comparison context.\n"
    "4. Check sbdb_hall_of_fame, sbdb_lifetime_achievement, sbdb_presidents_award, "
    "sbdb_award_of_distinction, sbdb_officer_of_the_year — search for the person's name "
    "in each using LIKE.\n"
    "5. Check sbdb_concepts for the band's themes in those years if available.\n"
    "Do NOT answer with just a count of years. Build the full picture of this person's "
    "contribution to Mummers history."
)

_PERSON_TENURE_SYNTHESIS_EXTRA = (
    "\n\nIMPORTANT — This question is about a person's history in the Mummers community. "
    "Write the response as a tribute that honors their contribution to string band history. "
    "Lead with their most significant achievement. If they were a captain, narrate the tenure "
    "year by year — cite specific placements, themes, and how those results compare to the "
    "band's historical average. If they received awards, weave those into the narrative. "
    "Connect results to context: a first-prize win during their tenure is a career highlight "
    "worth calling out explicitly. End with a 'Bottom Line' sentence that a Mummers fan "
    "would remember. Tone: knowledgeable, warm, specific — like a historian who knew them."
)


# ── Placement column detection (for Y-axis inversion on charts) ──────────────

_PLACEMENT_COL_RE = re.compile(
    r'\b(place(ment)?|finish(ing)?|rank(ing)?|position)\b',
    re.IGNORECASE,
)
# Words that indicate a column is a count/score/money — NOT a finishing position.
_NON_PLACEMENT_WORDS = frozenset({
    'prize', 'win', 'wins', 'won', 'count', 'total', 'sum', 'award', 'money',
    'score', 'points', 'music', 'visual', 'costume', 'effect',
})


def _is_placement_data(columns: list[str]) -> bool:
    """Return True if any result column represents finishing position (lower = better)."""
    for col in columns:
        col_lower = col.lower().strip()
        if any(w in col_lower for w in _NON_PLACEMENT_WORDS):
            continue
        if _PLACEMENT_COL_RE.search(col):
            return True
    return False


# ── Prize ambiguity detection ─────────────────────────────────────────────────

# "prize money" context — clearly the dollar-amount meaning.
_PRIZE_MONEY_RE = re.compile(
    r'\b(prize\s+money|how\s+much\s+(prize|money)|dollar(s)?|cash|monetary|'
    r'most\s+prize\s+money|total\s+prize|prize\s+amount|payout|purse)\b',
    re.IGNORECASE,
)

# Finishing-position context — ordinal directly before "prize" or "place".
_PRIZE_POSITION_RE = re.compile(
    r'\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|'
    r'sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\s+prize\b|'
    r'\b(finish(ed)?|place(d)?|came\s+in)\s+(first|second|third|in\s+(first|second|third))\b',
    re.IGNORECASE,
)

_PRIZE_CLARIFY_MSG = (
    'When you say "prize," do you mean **finishing position** '
    "(1st place, 2nd place, etc.) or **prize money** (the dollar amount awarded to the band)?\n\n"
    "Note: prize money was only awarded through **2008** — after that, no monetary prizes "
    "were given. If you're asking about competitive finishes or wins, those records cover "
    "the full range from 1901 to the present."
)


def _prize_is_ambiguous(question: str) -> bool:
    """Return True if 'prize' appears but context doesn't resolve placement vs. money."""
    if "prize" not in question.lower():
        return False
    if _PRIZE_MONEY_RE.search(question):
        return False
    if _PRIZE_POSITION_RE.search(question):
        return False
    return True


def _needs_deep_analysis(question: str) -> bool:
    return len(question) > 40 and bool(_DEEP_ANALYSIS_RE.search(question))


def _involves_marching_order(question: str) -> bool:
    return bool(_MARCHING_ORDER_RE.search(question))


def _involves_person_tenure(question: str) -> bool:
    return bool(_PERSON_TENURE_RE.search(question))


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
    _INTERP_ROW_LIMIT = 200
    shown = preview[:_INTERP_ROW_LIMIT]
    count_note = (
        f" Showing summary of {row_count} total records."
        if row_count > _INTERP_ROW_LIMIT else ""
    )
    msgs.append({
        "role": "user",
        "content": (
            "You are MummSTER AI — the Mummers Ultimate Metrics Machine for Scoring, Trends, "
            "Evaluation and Reporting Analytics Interface. You have encyclopedic knowledge of "
            "Philadelphia string band competition history covering 1901 to 2026. "
            "When appropriate, refer to yourself and your data as 'the MummSTER AI database' "
            "— for example: 'The MummSTER AI database shows...' or "
            "'Based on MummSTER AI records...'\n\n"
            f"Question: {question}\n"
            f"SQL used: {sql}\n"
            f"Results ({row_count} rows): "
            f"{json.dumps({'rows': shown, 'total_rows': row_count})}\n\n"
            "ALWAYS go deep on the first answer — never give a minimal response and suggest a "
            "follow-up instead of answering. If the data is here, use it.\n\n"
            "For questions about a person's tenure or captaincy, proactively include: "
            "the specific years, the band's placement each year, any themes performed, "
            "scores achieved, how those results compare to the band's historical average, "
            "and what happened after the tenure ended. Do not wait to be asked for this detail.\n\n"
            "Use markdown: **bold** for key years and numbers, bullet lists or tables for "
            "multi-year data. Write with genuine enthusiasm for Mummers history. "
            "Note era context only when it adds real understanding."
            + count_note
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
                block.append(json.dumps(r["rows"][:200], indent=2))
        data_blocks.append("\n".join(block))

    resp = await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": (
                "You are MummSTER AI — the Mummers Ultimate Metrics Machine for Scoring, Trends, "
                "Evaluation and Reporting Analytics Interface. You have access to a complete "
                "database of Philadelphia string band competition history spanning 1901 to 2026. "
                "You have run multiple SQL queries to fully answer a complex question.\n\n"
                "Refer to your data source as 'the MummSTER AI database' where natural. "
                "Answer with the depth of a knowledgeable expert. When someone asks how long "
                "someone was captain, they want everything about that era: the years, the "
                "placements, the themes, the scores, how it compared to history, and what came "
                "after. Provide all of this proactively.\n\n"
                f"**Original question:** {question}\n\n"
                "**Query results:**\n\n" + "\n\n".join(data_blocks) + "\n\n"
                "Structure your response with these markdown sections:\n\n"
                "## Overall Verdict\n"
                "Direct, complete answer to the question — not a teaser.\n\n"
                "## The Full Picture\n"
                "Year-by-year detail where relevant. Use a table for multi-year or multi-band data. "
                "Cite specific placements, scores, and themes from the results.\n\n"
                "## Competitive Context\n"
                "How this compares to the field or to the band's own history — averages, "
                "standout years, peer comparison.\n\n"
                "## Notable Findings\n"
                "Anything surprising, a career highlight, an anomaly, or a lasting record.\n\n"
                "## Bottom Line\n"
                "One sentence that a Mummers fan would remember and repeat.\n\n"
                "Use **bold** for key numbers and years. Be specific — every claim should be "
                "traceable to the query results above."
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

        # Ambiguity check — ask for clarification before generating SQL.
        if _prize_is_ambiguous(question):
            yield _sse("clarification_needed", {"message": _PRIZE_CLARIFY_MSG})
            yield _sse("interpretation", {"text": _PRIZE_CLARIFY_MSG})
            yield _sse("complete", {"query_id": query_id})
            return

        system_prompt = get_system_prompt()

        if (_needs_deep_analysis(question)
                or _involves_marching_order(question)
                or _involves_person_tenure(question)):
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
            placement_chart = _is_placement_data(columns)
            placement_axis_note = (
                "\nIMPORTANT — This data shows finishing positions where 1 = 1st place = best. "
                "The Y axis MUST be inverted so 1st place appears at the TOP. "
                'Include: "scales": {"y": {"reverse": true, "min": 1, '
                '"title": {"display": true, "text": "Place (1st = Best)"}}}'
            ) if placement_chart else ""

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
                        'If yes, return ONLY a JSON object: '
                        '{"type":"bar"|"line"|"pie","labels":[...],'
                        '"datasets":[{"label":"...","data":[...]}],'
                        '"title":"...","scales":{"y":{...}}}\n'
                        "If no chart is appropriate, return exactly: null"
                        + placement_axis_note
                    ),
                }],
            )
            chart_text = chart_resp.content[0].text.strip()
            if chart_text.lower() not in ("null", "none", ""):
                try:
                    chart_spec = json.loads(chart_text)
                    # Guarantee Y-axis inversion for placement data regardless of
                    # whether the model included it in the spec.
                    if placement_chart:
                        chart_spec.setdefault("scales", {}).setdefault("y", {})
                        chart_spec["scales"]["y"]["reverse"] = True
                        chart_spec["scales"]["y"]["min"] = 1
                        chart_spec["scales"]["y"].setdefault(
                            "title", {"display": True, "text": "Place (1st = Best)"}
                        )
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
        person_tenure_question = _involves_person_tenure(question)
        decompose_extra = (
            _MARCHING_DECOMPOSE_EXTRA if marching_question
            else _PERSON_TENURE_DECOMPOSE_EXTRA if person_tenure_question
            else ""
        )
        synthesis_extra = (
            _MARCHING_SYNTHESIS_EXTRA if marching_question
            else _PERSON_TENURE_SYNTHESIS_EXTRA if person_tenure_question
            else ""
        )

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
