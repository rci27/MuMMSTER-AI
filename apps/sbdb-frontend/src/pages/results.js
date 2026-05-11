import React, { useState, useMemo, useEffect } from "react"
import { graphql, Link } from "gatsby"
import Layout from "../components/Layout"

function getDriveEmbedUrl(url) {
  if (!url) return null
  const match = url.match(/[?&]id=([^&]+)/)
  if (match) return `https://drive.google.com/file/d/${match[1]}/preview`
  const match2 = url.match(/\/d\/([^/]+)/)
  if (match2) return `https://drive.google.com/file/d/${match2[1]}/preview`
  return url
}

function getYouTubeThumbnail(url) {
  if (!url) return null
  const match = url.match(/embed\/([^?]+)/)
  if (match) return `https://img.youtube.com/vi/${match[1]}/mqdefault.jpg`
  return null
}

export default function ResultsPage({ data }) {
  const allRows = data.allSbdbResult.nodes
  const years = [...new Set(allRows.map(r => r.Year))].sort((a, b) => b - a)
  const [selectedYear, setSelectedYear] = useState(years[0])
  const [sortCol, setSortCol] = useState("Place")
  const [sortDir, setSortDir] = useState("asc")
  const [showModal, setShowModal] = useState(false)
  const [activeVideo, setActiveVideo] = useState(null)

  useEffect(() => {
    if (showModal) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => { document.body.style.overflow = "" }
  }, [showModal])

  function bandSlug(name) {
    return name.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
  }

  function handleSort(col) {
    if (sortCol === col) {
      setSortDir(d => d === "asc" ? "desc" : "asc")
    } else {
      setSortCol(col)
      setSortDir("asc")
    }
  }

  function sortArrow(col) {
    if (sortCol !== col) return <span style={{ color: "#3a5472", marginLeft: "4px", fontSize: "10px" }}>↕</span>
    return <span style={{ color: "#c8a84b", marginLeft: "4px", fontSize: "10px" }}>{sortDir === "asc" ? "↑" : "↓"}</span>
  }

  const yearRows = allRows.filter(r => r.Year === selectedYear)
  const hasScores = yearRows.some(r => r.music_playing)
  const era = yearRows[0]?.era || ""
  const pointSheet = yearRows[0]?.point_sheet || null
  const embedUrl = getDriveEmbedUrl(pointSheet)

  function eraClass(e) {
    if (e === "contemporary") return "sb-era sb-era-contemporary"
    if (e === "modern") return "sb-era sb-era-modern"
    return "sb-era sb-era-premodern"
  }

  function numVal(v) {
    const n = parseFloat(v)
    return isNaN(n) ? -Infinity : n
  }

  const displayRows = useMemo(() => {
    let rows = [...yearRows]
    rows.sort((a, b) => {
      let av, bv
      switch (sortCol) {
        case "Place": av = numVal(a.Place); bv = numVal(b.Place); break
        case "Band": av = (a.Band || "").toLowerCase(); bv = (b.Band || "").toLowerCase(); break
        case "Total": av = numVal(a.total_points); bv = numVal(b.total_points); break
        case "Music": av = numVal(a.music_playing); bv = numVal(b.music_playing); break
        case "GE Music": av = numVal(a.ge_music); bv = numVal(b.ge_music); break
        case "Visual": av = numVal(a.visual_performance); bv = numVal(b.visual_performance); break
        case "GE Visual": av = numVal(a.ge_visual); bv = numVal(b.ge_visual); break
        case "Captain": av = (a.Captain || "").toLowerCase(); bv = (b.Captain || "").toLowerCase(); break
        case "Order": av = numVal(a.march_order); bv = numVal(b.march_order); break
        default: av = numVal(a.Place); bv = numVal(b.Place)
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1
      if (av > bv) return sortDir === "asc" ? 1 : -1
      return 0
    })
    return rows
  }, [yearRows, sortCol, sortDir])

  const thStyle = { cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }
  const thActiveStyle = { ...thStyle, color: "#c8a84b" }

  return (
    <Layout title="Competition Results" activePage="results">

      {/* Modal */}
      {showModal && (
        <div
          onClick={() => setShowModal(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.85)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "1rem",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "#111c2d",
              border: "1px solid #1f3352",
              borderRadius: "12px",
              width: "100%",
              maxWidth: "900px",
              height: "85vh",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
            }}
          >
            {/* Modal header */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "1rem 1.25rem",
              borderBottom: "1px solid #1f3352",
              background: "#0f1a2b",
              flexShrink: 0,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span style={{ fontSize: "1rem" }}>📄</span>
                <span style={{
                  fontFamily: "'Playfair Display', Georgia, serif",
                  fontSize: "1rem", fontWeight: 700, color: "#f4f8fc"
                }}>
                  {selectedYear} Point Sheet
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <a
                  href={pointSheet}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: "0.78rem", color: "#9a7e35",
                    border: "1px solid #1f3352", borderRadius: "6px",
                    padding: "0.3rem 0.75rem", textDecoration: "none",
                    transition: "color 0.15s",
                  }}
                >
                  Open in Drive ↗
                </a>
                <button
                  onClick={() => setShowModal(false)}
                  style={{
                    background: "none", border: "1px solid #1f3352",
                    color: "#6e8faf", borderRadius: "6px",
                    padding: "0.3rem 0.75rem", cursor: "pointer",
                    fontSize: "0.82rem", transition: "color 0.15s, border-color 0.15s",
                  }}
                >
                  ✕ Close
                </button>
              </div>
            </div>
            {/* iframe */}
            <iframe
              src={embedUrl}
              style={{ flex: 1, border: "none", background: "#0b1220" }}
              title={`${selectedYear} Point Sheet`}
              allow="autoplay"
            />
          </div>
        </div>
      )}

      {/* Controls row */}
      <div className="sb-controls">
        <span className="sb-ctrl-label">Year</span>
        <select
          className="sb-ctrl-select"
          value={selectedYear}
          onChange={e => { setSelectedYear(e.target.value); setSortCol("Place"); setSortDir("asc"); setShowModal(false); setActiveVideo(null) }}
        >
          {years.map(y => <option key={y} value={y}>{y}</option>)}
        </select>
<Link
          to={`/parade`}
          style={{
            marginLeft: "auto",
            display: "inline-flex", flexDirection: "column", alignItems: "center",
            gap: "0.2rem", background: "#111c2d", border: "1px solid #1f3352",
            color: "#6e8faf", fontSize: "0.62rem", fontWeight: 500,
            padding: "0.5rem 1rem", borderRadius: "8px", textDecoration: "none",
            minWidth: "90px", textTransform: "uppercase", letterSpacing: "0.08em",
            transition: "border-color 0.15s, color 0.15s",
            cursor: "pointer",
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          Parade Info
        </Link>
        {pointSheet && (
          <button
            onClick={() => setShowModal(true)}
            style={{
              display: "inline-flex", flexDirection: "column", alignItems: "center",
              gap: "0.2rem", background: "rgba(200,168,75,0.08)",
              border: "1px solid #9a7e35", color: "#c8a84b",
              fontSize: "0.62rem", fontWeight: 600,
              padding: "0.5rem 1rem", borderRadius: "8px",
              minWidth: "90px", textTransform: "uppercase", letterSpacing: "0.08em",
              cursor: "pointer", fontFamily: "inherit",
              transition: "background 0.15s",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            Point Sheet
          </button>
        )}
      </div>

      {/* Results table */}
      <div className="sb-table-wrap">
        <table className="sb-table">
          <thead>
            <tr>
              <th style={{width:"82px"}}>Video</th>
              <th style={sortCol === "Place" ? thActiveStyle : thStyle} onClick={() => handleSort("Place")}>Place{sortArrow("Place")}</th>
              <th style={sortCol === "Band" ? thActiveStyle : thStyle} onClick={() => handleSort("Band")}>Band{sortArrow("Band")}</th>
              <th style={sortCol === "Total" ? thActiveStyle : thStyle} onClick={() => handleSort("Total")}>Total{sortArrow("Total")}</th>
              {hasScores && <>
                <th style={sortCol === "Music" ? thActiveStyle : thStyle} onClick={() => handleSort("Music")}>Music{sortArrow("Music")}</th>
                <th style={sortCol === "GE Music" ? thActiveStyle : thStyle} onClick={() => handleSort("GE Music")}>GE Music{sortArrow("GE Music")}</th>
                <th style={sortCol === "Visual" ? thActiveStyle : thStyle} onClick={() => handleSort("Visual")}>Visual{sortArrow("Visual")}</th>
                <th style={sortCol === "GE Visual" ? thActiveStyle : thStyle} onClick={() => handleSort("GE Visual")}>GE Visual{sortArrow("GE Visual")}</th>
              </>}
              <th style={sortCol === "Captain" ? thActiveStyle : thStyle} onClick={() => handleSort("Captain")}>Captain{sortArrow("Captain")}</th>
              <th style={sortCol === "Order" ? thActiveStyle : thStyle} onClick={() => handleSort("Order")}>Order{sortArrow("Order")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {displayRows.length === 0 && (
              <tr>
                <td colSpan={hasScores ? 10 : 6} style={{ textAlign: "center", color: "#6e8faf", padding: "2rem" }}>
                  No results found.
                </td>
              </tr>
            )}
            {displayRows.map(r => (
              <tr key={r.Band} className={String(r.Place) === "1" ? "sb-winner" : ""}>
                <td style={{padding:0, width:"82px", verticalAlign:"middle"}}>
                  {r.YouTube ? (
                    <div
                      onClick={() => setActiveVideo(activeVideo === r.YouTube ? null : r.YouTube)}
                      style={{
                        width:"82px", height:"46px", background:"#1a2d47",
                        display:"flex", alignItems:"center", justifyContent:"center",
                        position:"relative", cursor:"pointer", overflow:"hidden",
                        borderRight:"1px solid #1f3352",
                      }}
                    >
                      {getYouTubeThumbnail(r.YouTube) && (
                        <img
                          src={getYouTubeThumbnail(r.YouTube)}
                          alt=""
                          style={{width:"100%", height:"100%", objectFit:"cover", position:"absolute", inset:0}}
                          onError={e => { e.target.style.display="none" }}
                        />
                      )}
                      <div style={{
                        position:"absolute", inset:0, display:"flex",
                        alignItems:"center", justifyContent:"center",
                        background: activeVideo === r.YouTube ? "rgba(0,0,0,0.5)" : "rgba(0,0,0,0.25)"
                      }}>
                        <div style={{
                          width:"20px", height:"20px",
                          background:"rgba(200,168,75,0.85)", borderRadius:"50%",
                          display:"flex", alignItems:"center", justifyContent:"center"
                        }}>
                          <div style={{
                            width:0, height:0, borderStyle:"solid",
                            borderWidth:"4px 0 4px 7px",
                            borderColor:"transparent transparent transparent #0b1220",
                            marginLeft:"1px"
                          }} />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div style={{width:"82px", height:"46px", background:"#0f1a2b", borderRight:"1px solid #1f3352"}} />
                  )}
                </td>
                <td>{r.Place}</td>
                <td><Link to={`/bands/${bandSlug(r.Band)}`}>{r.Band}</Link></td>
                <td className="sb-score">{r.total_points || "—"}</td>
                {hasScores && <>
                  <td>{r.music_playing || "—"}</td>
                  <td>{r.ge_music || "—"}</td>
                  <td>{r.visual_performance || "—"}</td>
                  <td>{r.ge_visual || "—"}</td>
                </>}
                <td>{r.Captain ? <Link to={`/captains/${bandSlug(r.Captain)}`}>{r.Captain}</Link> : "—"}</td>
                <td>{r.march_order || "—"}</td>
                <td></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {activeVideo && (
        <div style={{
          background:"#111c2d", border:"1px solid #1f3352",
          borderRadius:"8px", overflow:"hidden", marginTop:"1rem"
        }}>
          <div style={{
            display:"flex", alignItems:"center", justifyContent:"space-between",
            padding:"8px 14px", background:"#0f1a2b", borderBottom:"1px solid #1f3352"
          }}>
            <span style={{fontSize:"11px", fontWeight:500, color:"#f4f8fc"}}>
              {displayRows.find(r => r.YouTube === activeVideo)?.Band} — {selectedYear}
            </span>
            <div style={{display:"flex", alignItems:"center", gap:"8px"}}>
              <a href={activeVideo.replace("/embed/","/watch?v=")} target="_blank" rel="noopener noreferrer"
                style={{fontSize:"10px", color:"#9a7e35", textDecoration:"none"}}>
                Open in YouTube ↗
              </a>
              <button onClick={() => setActiveVideo(null)} style={{
                background:"none", border:"1px solid #1f3352", color:"#6e8faf",
                borderRadius:"6px", padding:"3px 10px", cursor:"pointer",
                fontSize:"10px", fontFamily:"inherit"
              }}>✕ Close</button>
            </div>
          </div>
          <iframe
            src={activeVideo}
            style={{width:"100%", aspectRatio:"16/9", border:"none", display:"block"}}
            title="Performance video"
            allowFullScreen
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          />
        </div>
      )}

      {era && (
        <p className="sb-era-note">
          Era: <span className={eraClass(era)}>{era}</span>
        </p>
      )}
    </Layout>
  )
}

export const query = graphql`
  query ResultsQuery {
    allSbdbResult(sort: { Year: DESC }) {
      nodes {
        Year
        Place
        Band
        total_points
        music_playing
        ge_music
        visual_performance
        ge_visual
        Captain
        march_order
        YouTube
        theme_title
        point_sheet
      }
    }
  }
`
