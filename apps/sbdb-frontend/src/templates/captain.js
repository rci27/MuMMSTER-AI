import React, { useState, useMemo } from "react"
import { Link } from "gatsby"
import Layout from "../components/Layout"

export default function CaptainTemplate({ pageContext }) {
  const { captain, history, wins, best } = pageContext
  const [search, setSearch] = useState("")
  const [sortCol, setSortCol] = useState("Year")
  const [sortDir, setSortDir] = useState("desc")

  function bandSlug(name) {
    return name.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
  }

  const sorted = [...history].sort((a, b) => parseInt(a.Year) - parseInt(b.Year))
  const years = sorted.map(r => parseInt(r.Year)).filter(Boolean)
  const firstYear = years.length ? Math.min(...years) : "—"
  const lastYear = years.length ? Math.max(...years) : "—"
  const hasScores = history.some(r => r.music_playing)
  const uniqueBands = [...new Set(history.map(r => r.Band))].sort()

  function handleSort(col) {
    if (sortCol === col) {
      setSortDir(d => d === "asc" ? "desc" : "asc")
    } else {
      setSortCol(col)
      setSortDir(col === "Year" ? "desc" : "asc")
    }
  }

  function sortArrow(col) {
    if (sortCol !== col) return <span style={{ color: "#3a5472", marginLeft: "4px", fontSize: "10px" }}>↕</span>
    return <span style={{ color: "#c8a84b", marginLeft: "4px", fontSize: "10px" }}>{sortDir === "asc" ? "↑" : "↓"}</span>
  }

  function numVal(v) {
    const n = parseFloat(v)
    return isNaN(n) ? -Infinity : n
  }

  const displayRows = useMemo(() => {
    let rows = [...history]
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      rows = rows.filter(r =>
        (r.Year || "").toString().includes(q) ||
        (r.Band || "").toLowerCase().includes(q) ||
        (r.theme_title || "").toLowerCase().includes(q) ||
        (r.Place || "").toString().includes(q)
      )
    }
    rows.sort((a, b) => {
      let av, bv
      switch (sortCol) {
        case "Year": av = numVal(a.Year); bv = numVal(b.Year); break
        case "Band": av = (a.Band || "").toLowerCase(); bv = (b.Band || "").toLowerCase(); break
        case "Place": av = numVal(a.Place); bv = numVal(b.Place); break
        case "Total": av = numVal(a.total_points); bv = numVal(b.total_points); break
        case "Music": av = numVal(a.music_playing); bv = numVal(b.music_playing); break
        case "GE M": av = numVal(a.ge_music); bv = numVal(b.ge_music); break
        case "Visual": av = numVal(a.visual_performance); bv = numVal(b.visual_performance); break
        case "GE V": av = numVal(a.ge_visual); bv = numVal(b.ge_visual); break
        case "Theme": av = (a.theme_title || "").toLowerCase(); bv = (b.theme_title || "").toLowerCase(); break
        default: av = numVal(a.Year); bv = numVal(b.Year)
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1
      if (av > bv) return sortDir === "asc" ? 1 : -1
      return 0
    })
    return rows
  }, [history, search, sortCol, sortDir])

  const thStyle = { cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }
  const thActiveStyle = { ...thStyle, color: "#c8a84b" }

  const chartRows = sorted.filter(r => parseInt(r.Place))
  const maxPlace = Math.max(...chartRows.map(r => parseInt(r.Place) || 1), 20)
  const W = 600, H = 140, PAD = 28
  const pts = chartRows.map((r, i) => {
    const x = PAD + (i / Math.max(chartRows.length - 1, 1)) * (W - PAD * 2)
    const y = PAD + ((parseInt(r.Place) - 1) / Math.max(maxPlace - 1, 1)) * (H - PAD * 2)
    return `${x},${y}`
  }).join(" ")

  const labelYears = []
  if (chartRows.length > 0) {
    labelYears.push(chartRows[0].Year)
    if (chartRows.length > 2) labelYears.push(chartRows[Math.floor(chartRows.length / 2)].Year)
    if (chartRows.length > 1) labelYears.push(chartRows[chartRows.length - 1].Year)
  }

  return (
    <Layout activePage="results">
      <Link to="/results" className="sb-band-back">← Results</Link>

      <div className="sb-band-hdr">
        <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", marginBottom: "0.5rem" }}>
          <div style={{
            width: "90px", height: "90px",
            background: "rgba(200,168,75,0.12)",
            border: "1px solid #9a7e35",
            borderRadius: "12px",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
            fontSize: "36px", fontWeight: 500,
            fontFamily: "'Playfair Display', Georgia, serif",
            color: "#c8a84b",
          }}>
            {captain.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="sb-band-title">{captain}</div>
            <div style={{ fontSize: "0.78rem", color: "#6e8faf", marginTop: "0.25rem" }}>
              Captain · {uniqueBands.length === 1 ? uniqueBands[0] : `${uniqueBands.length} bands`}
            </div>
          </div>
        </div>
      </div>

      <div className="sb-band-stats-row">
        <div className="sb-bstat"><span className="sb-bstat-num">{firstYear}–{lastYear}</span><span className="sb-bstat-label">Years active</span></div>
        <div className="sb-bstat"><span className="sb-bstat-num">{history.length}</span><span className="sb-bstat-label">Parades</span></div>
        <div className="sb-bstat"><span className="sb-bstat-num">{wins}</span><span className="sb-bstat-label">First prizes</span></div>
        <div className="sb-bstat"><span className="sb-bstat-num">{best ? `${best}${best === 1 ? "st" : best === 2 ? "nd" : best === 3 ? "rd" : "th"}` : "—"}</span><span className="sb-bstat-label">Best placement</span></div>
      </div>

      {uniqueBands.length > 1 && (
        <div style={{
          background: "#111c2d", border: "1px solid #1f3352",
          borderRadius: "10px", padding: "1rem 1.5rem",
          marginTop: "1.5rem", display: "flex", gap: "0.5rem", flexWrap: "wrap",
          alignItems: "center",
        }}>
          <span style={{ fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: "#3a5472", marginRight: "0.5rem" }}>Bands</span>
          {uniqueBands.map(b => (
            <Link key={b} to={`/bands/${bandSlug(b)}`} style={{
              fontSize: "0.78rem", color: "#c8a84b",
              background: "rgba(200,168,75,0.08)", border: "1px solid #9a7e35",
              borderRadius: "99px", padding: "2px 10px", textDecoration: "none",
            }}>{b}</Link>
          ))}
        </div>
      )}

      {chartRows.length > 3 && (
        <div className="sb-chart-panel" style={{ marginTop: "2rem" }}>
          <div className="sb-chart-title">Placement history — all years</div>
          <svg viewBox={`0 0 ${W} ${H}`} className="sb-chart-svg">
            {[1, 5, 10, 15].filter(p => p <= maxPlace).map(p => {
              const y = PAD + ((p - 1) / Math.max(maxPlace - 1, 1)) * (H - PAD * 2)
              return (
                <g key={p}>
                  <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#1f3352" strokeWidth="0.5" />
                  <text x={PAD - 4} y={y + 4} textAnchor="end" fontSize="8" fill="#3a5472">{p}</text>
                </g>
              )
            })}
            <polyline fill="none" stroke="#c8a84b" strokeWidth="2" points={pts} />
            {chartRows.map((r, i) => {
              const x = PAD + (i / Math.max(chartRows.length - 1, 1)) * (W - PAD * 2)
              const y = PAD + ((parseInt(r.Place) - 1) / Math.max(maxPlace - 1, 1)) * (H - PAD * 2)
              return <circle key={i} cx={x} cy={y} r="3" fill="#c8a84b" />
            })}
          </svg>
          <div className="sb-chart-labels">
            {labelYears.map((y, i) => <span key={i}>{y}</span>)}
          </div>
          <p className="sb-chart-note">Lower = better. 1st place at top.</p>
        </div>
      )}

      <div className="sb-history-title" style={{ marginTop: "2rem" }}>Competition History</div>

      <div style={{ marginBottom: "1rem" }}>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by year, band, theme, or place..."
          className="sb-filter"
          style={{ maxWidth: "420px", display: "block" }}
        />
      </div>

      <div className="sb-table-wrap">
        <table className="sb-table">
          <thead>
            <tr>
              <th style={sortCol === "Year" ? thActiveStyle : thStyle} onClick={() => handleSort("Year")}>Year{sortArrow("Year")}</th>
              <th style={sortCol === "Band" ? thActiveStyle : thStyle} onClick={() => handleSort("Band")}>Band{sortArrow("Band")}</th>
              <th style={sortCol === "Place" ? thActiveStyle : thStyle} onClick={() => handleSort("Place")}>Place{sortArrow("Place")}</th>
              <th style={sortCol === "Total" ? thActiveStyle : thStyle} onClick={() => handleSort("Total")}>Total{sortArrow("Total")}</th>
              {hasScores && <>
                <th style={sortCol === "Music" ? thActiveStyle : thStyle} onClick={() => handleSort("Music")}>Music{sortArrow("Music")}</th>
                <th style={sortCol === "GE M" ? thActiveStyle : thStyle} onClick={() => handleSort("GE M")}>GE M{sortArrow("GE M")}</th>
                <th style={sortCol === "Visual" ? thActiveStyle : thStyle} onClick={() => handleSort("Visual")}>Visual{sortArrow("Visual")}</th>
                <th style={sortCol === "GE V" ? thActiveStyle : thStyle} onClick={() => handleSort("GE V")}>GE V{sortArrow("GE V")}</th>
              </>}
              <th style={sortCol === "Theme" ? thActiveStyle : thStyle} onClick={() => handleSort("Theme")}>Theme{sortArrow("Theme")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {displayRows.length === 0 && (
              <tr>
                <td colSpan={hasScores ? 10 : 6} style={{ textAlign: "center", color: "#6e8faf", padding: "2rem" }}>
                  No results match "{search}"
                </td>
              </tr>
            )}
            {displayRows.map(r => (
              <tr key={r.Year + r.Band} className={String(r.Place) === "1" ? "sb-winner" : ""}>
                <td>{r.Year}</td>
                <td><Link to={`/bands/${bandSlug(r.Band)}`}>{r.Band}</Link></td>
                <td>{r.Place || "—"}</td>
                <td className="sb-score">{r.total_points || "—"}</td>
                {hasScores && <>
                  <td>{r.music_playing || "—"}</td>
                  <td>{r.ge_music || "—"}</td>
                  <td>{r.visual_performance || "—"}</td>
                  <td>{r.ge_visual || "—"}</td>
                </>}
                <td>{r.theme_title || "—"}</td>
                <td>{r.YouTube && <a href={r.YouTube} target="_blank" rel="noopener noreferrer" className="sb-yt">▶</a>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {search && displayRows.length > 0 && (
        <p style={{ marginTop: "0.75rem", fontSize: "0.78rem", color: "#6e8faf" }}>
          Showing {displayRows.length} of {history.length} years for "{search}"
          <button onClick={() => setSearch("")} style={{ marginLeft: "0.75rem", background: "none", border: "none", color: "#9a7e35", cursor: "pointer", fontSize: "0.78rem" }}>Clear ×</button>
        </p>
      )}
    </Layout>
  )
}
