import React, { useState, useRef, useEffect } from "react"

const API_URL = process.env.GATSBY_QUERY_API_URL || "https://sbdb-ai-query.theronlab.com"

function renderMarkdown(text) {
  if (!text) return ""

  function convertTables(input) {
    const lines = input.split("\n")
    const result = []
    let tableRows = []
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim()
      if (line.startsWith("|") && line.endsWith("|")) {
        if (!/^[|\s\-:]+$/.test(line)) tableRows.push(line)
      } else {
        if (tableRows.length > 0) {
          let html = "<table><thead><tr>"
          tableRows[0].split("|").filter(c => c.trim()).forEach(h => { html += `<th>${h.trim()}</th>` })
          html += "</tr></thead><tbody>"
          for (let r = 1; r < tableRows.length; r++) {
            html += "<tr>"
            tableRows[r].split("|").filter(c => c.trim()).forEach(c => { html += `<td>${c.trim()}</td>` })
            html += "</tr>"
          }
          html += "</tbody></table>"
          result.push(html)
          tableRows = []
        }
        result.push(line)
      }
    }
    if (tableRows.length > 0) {
      let html = "<table><thead><tr>"
      tableRows[0].split("|").filter(c => c.trim()).forEach(h => { html += `<th>${h.trim()}</th>` })
      html += "</tr></thead><tbody>"
      for (let r = 1; r < tableRows.length; r++) {
        html += "<tr>"
        tableRows[r].split("|").filter(c => c.trim()).forEach(c => { html += `<td>${c.trim()}</td>` })
        html += "</tr>"
      }
      html += "</tbody></table>"
      result.push(html)
    }
    return result.join("\n")
  }

  let html = convertTables(text)
  html = html
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^---+$/gm, "<hr/>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "<br/><br/>")
  return html
}

export default function AskPanel() {
  const [question, setQuestion] = useState("")
  const [status, setStatus] = useState("")
  const [sql, setSql] = useState("")
  const [showSql, setShowSql] = useState(false)
  const [rows, setRows] = useState([])
  const [columns, setColumns] = useState([])
  const [interpretation, setInterpretation] = useState("")
  const [chart, setChart] = useState(null)
  const [followup, setFollowup] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const chartRef = useRef(null)
  const chartInstance = useRef(null)

  useEffect(() => {
    if (typeof window !== "undefined" && !window.Chart) {
      const s = document.createElement("script")
      s.src = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"
      document.head.appendChild(s)
    }
  }, [])

  useEffect(() => {
    if (chart && chartRef.current) {
      if (chartInstance.current) chartInstance.current.destroy()
      if (typeof window !== "undefined" && window.Chart) {
        chartInstance.current = new window.Chart(chartRef.current, chart)
      }
    }
  }, [chart])

  async function handleAsk(e) {
    e.preventDefault()
    if (!question.trim() || loading) return
    setLoading(true)
    setError("")
    setStatus("Connecting...")
    setSql("")
    setRows([])
    setColumns([])
    setInterpretation("")
    setChart(null)
    setFollowup("")

    try {
      const res = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      })
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === "status") setStatus(evt.message)
            if (evt.type === "sql") setSql(evt.sql)
            if (evt.type === "results") { setColumns(evt.columns || []); setRows(evt.rows || []) }
            if (evt.type === "interpretation") setInterpretation(evt.text)
            if (evt.type === "chart") setChart(evt.spec)
            if (evt.type === "followup") setFollowup(evt.question)
            if (evt.type === "done") setStatus("")
            if (evt.type === "error") setError(evt.message)
          } catch {}
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setStatus("")
    }
  }

  return (
    <div className="sb-ask-panel">
      <form onSubmit={handleAsk} className="sb-ask-form">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="Ask anything — e.g. Which band has the most first prize wins since 1991?"
          className="sb-ask-input"
          disabled={loading}
        />
        <button type="submit" className="sb-ask-btn" disabled={loading || !question.trim()}>
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {status && (
        <p className="sb-ask-status">
          <span className="sb-ask-dot" />
          {status}
        </p>
      )}
      {error && <p className="sb-ask-error">{error}</p>}

      {sql && (
        <div className="sb-sql-block">
          <button className="sb-sql-toggle" onClick={() => setShowSql(s => !s)}>
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
          {showSql && <pre className="sb-sql-code">{sql}</pre>}
        </div>
      )}

      {interpretation && (
        <div className="sb-interp">
          <div dangerouslySetInnerHTML={{ __html: renderMarkdown(interpretation) }} />
        </div>
      )}

      {rows.length > 0 && (
        <div className="sb-result-wrap">
          <table className="sb-table">
            <thead>
              <tr>{columns.map(c => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((row, i) => (
                <tr key={i}>{row.map((cell, j) => <td key={j}>{cell ?? "—"}</td>)}</tr>
              ))}
            </tbody>
          </table>
          {rows.length > 50 && <p className="sb-trunc">Showing 50 of {rows.length} rows</p>}
        </div>
      )}

      {chart && (
        <div className="sb-chart-wrap">
          <canvas ref={chartRef} />
        </div>
      )}

      {followup && (
        <div className="sb-followup">
          <span>Try asking:</span>
          <button className="sb-followup-btn" onClick={() => setQuestion(followup)}>
            {followup}
          </button>
        </div>
      )}
    </div>
  )
}
