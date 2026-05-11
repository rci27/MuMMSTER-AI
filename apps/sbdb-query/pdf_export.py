from datetime import datetime


def generate_pdf(result: dict, chart_image: str | None = None) -> bytes:
    from weasyprint import HTML

    rows = result.get("rows", [])
    columns = result.get("columns", [])
    row_count = result.get("row_count", 0)

    header_cells = "".join(f"<th>{_esc(c)}</th>" for c in columns)
    body_rows = []
    for row in rows[:100]:
        cells = "".join(f"<td>{_esc(str(row.get(c, '')))}</td>" for c in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    table_html = (
        f"<table><thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    ) if body_rows else "<p>No rows returned.</p>"

    truncation_note = (
        f'<p class="note">Showing 100 of {row_count:,} rows.</p>'
        if row_count > 100 else ""
    )

    chart_html = (
        f'<div class="chart-wrap"><img src="{chart_image}" alt="Chart"></div>'
        if chart_image else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @page {{ margin: 2cm; }}
  body {{ font-family: Georgia, "Times New Roman", serif; font-size: 11pt; color: #1a1a1a; line-height: 1.5; }}
  h1 {{ font-size: 20pt; color: #0d1b2a; border-bottom: 2px solid #c9a227; padding-bottom: 6px; margin-bottom: 4px; }}
  .subtitle {{ font-size: 9pt; color: #666; margin-bottom: 24px; }}
  h2 {{ font-size: 13pt; color: #0d1b2a; margin-top: 22px; margin-bottom: 6px; }}
  .question {{ background: #f5f1e8; border-left: 4px solid #c9a227; padding: 10px 14px; font-style: italic; border-radius: 0 4px 4px 0; }}
  .interpretation {{ line-height: 1.7; }}
  .chart-wrap {{ margin: 12px 0; text-align: center; }}
  .chart-wrap img {{ max-width: 100%; max-height: 300px; }}
  pre {{ background: #f8f8f8; border: 1px solid #ddd; padding: 10px 12px; font-size: 8.5pt; white-space: pre-wrap; word-break: break-all; border-radius: 4px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 8.5pt; margin-top: 8px; }}
  th {{ background: #0d1b2a; color: #fff; padding: 6px 8px; text-align: left; font-weight: normal; }}
  td {{ border-bottom: 1px solid #e8e8e8; padding: 5px 8px; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #fafaf8; }}
  .refinement {{ background: #fffde7; border: 1px solid #f0c040; padding: 10px 14px; border-radius: 4px; font-style: italic; }}
  .note {{ font-size: 8.5pt; color: #888; font-style: italic; }}
  .footer {{ margin-top: 28px; padding-top: 8px; border-top: 1px solid #e0e0e0; font-size: 8pt; color: #aaa; }}
</style>
</head>
<body>
  <h1>MummSTER Query Results</h1>
  <p class="subtitle">Philadelphia Mummers Parade — String Band Scoring Analysis &nbsp;·&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

  <h2>Question</h2>
  <div class="question">{_esc(result['question'])}</div>

  <h2>Interpretation</h2>
  <div class="interpretation">{_esc(result['interpretation'])}</div>

  {f'<h2>Chart</h2>{chart_html}' if chart_html else ''}

  <h2>SQL Query</h2>
  <pre>{_esc(result['sql'])}</pre>

  <h2>Results &nbsp;<span class="note">({row_count:,} rows)</span></h2>
  {table_html}
  {truncation_note}

  <h2>Suggested Follow-Up</h2>
  <div class="refinement">{_esc(result['refinement'])}</div>

  <div class="footer">MummSTER &nbsp;·&nbsp; Internal use only &nbsp;·&nbsp; {row_count:,} rows returned</div>
</body>
</html>"""

    return HTML(string=html).write_pdf()


def _esc(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
