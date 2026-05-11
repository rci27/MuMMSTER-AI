import React, { useState } from "react"
import { Link, graphql } from "gatsby"
import Layout from "../components/Layout"

export default function HomePage({ data }) {
  const latest = [...(data.allSbdbResult.nodes || [])].sort((a, b) => parseInt(a.Place) - parseInt(b.Place))
  const latestYear = latest.length > 0 ? latest[0].Year : ""

  function bandSlug(name) {
    return name.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
  }

  function captainSlug(name) {
    return name.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
  }

  const [activeVideo, setActiveVideo] = useState(null)

  function getYouTubeThumbnail(url) {
    if (!url) return null
    const match = url.match(/embed\/([^?]+)/)
    if (match) return `https://img.youtube.com/vi/${match[1]}/mqdefault.jpg`
    return null
  }

  return (
    <Layout activePage="home">
      <div className="sb-hero">
        <div className="sb-hero-badge">Philadelphia Mummers String Band Division · Since 1901</div>
        <h1>
          The complete record of<br /><em>Philadelphia Mummers String Band</em> scoring and results history
        </h1>
        <p className="sb-hero-sub">
          Every competition result, every judge's score, every band — from 1901 to today. Now searchable with MummSTER AI.
        </p>
        <div className="sb-hero-cta">
          <Link to="/ask" className="sb-btn-gold">Ask MummSTER AI →</Link>
          <Link to="/results" className="sb-btn-ghost">Browse Results</Link>
        </div>
      </div>

      <div style={{
        padding: "0.85rem 1.5rem",
        borderBottom: "1px solid #1f3352",
        background: "rgba(200,168,75,0.03)",
      }}>
        <div style={{
          display: "flex", alignItems: "center", gap: "0.75rem",
          maxWidth: "640px", margin: "0 auto",
        }}>
          <span style={{
            fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.1em", color: "#c8a84b", whiteSpace: "nowrap",
          }}>Ask MummSTER AI</span>
          <Link
            to="/ask"
            style={{
              flex: 1, background: "#111c2d", color: "#6e8faf",
              border: "1px solid #1f3352", borderRadius: "6px",
              padding: "0.55rem 1rem", fontSize: "0.875rem",
              textDecoration: "none", display: "block",
              transition: "border-color 0.15s, color 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor="#9a7e35"; e.currentTarget.style.color="#f4f8fc" }}
            onMouseLeave={e => { e.currentTarget.style.borderColor="#1f3352"; e.currentTarget.style.color="#6e8faf" }}
          >
            Ask anything — e.g. Which band has won the most first prizes since 1991?
          </Link>
          <Link
            to="/ask"
            style={{
              background: "#c8a84b", color: "#0b1220", border: "none",
              borderRadius: "6px", padding: "0.55rem 1.25rem",
              fontSize: "0.875rem", fontWeight: 700, whiteSpace: "nowrap",
              textDecoration: "none", display: "inline-block",
              transition: "background 0.15s",
            }}
          >
            Ask →
          </Link>
        </div>
      </div>

      <div className="sb-stats-bar">
        <div className="sb-stat-item">
          <span className="sb-stat-num">1,960</span>
          <span className="sb-stat-label">Competition records</span>
        </div>
        <div className="sb-stat-item">
          <span className="sb-stat-num">104</span>
          <span className="sb-stat-label">String bands</span>
        </div>
        <div className="sb-stat-item">
          <span className="sb-stat-num">125</span>
          <span className="sb-stat-label">Years of history</span>
        </div>
        <div className="sb-stat-item">
          <span className="sb-stat-num">34K+</span>
          <span className="sb-stat-label">Judge scores</span>
        </div>
      </div>

      <div className="sb-feat-grid">
        <Link to="/results" className="sb-feat-card">
          <span className="sb-feat-icon">🏆</span>
          <div className="sb-feat-title">Browse Results</div>
          <div className="sb-feat-desc">Full placements and scores for every year since 1901</div>
        </Link>
        <Link to="/bands" className="sb-feat-card">
          <span className="sb-feat-icon">🎷</span>
          <div className="sb-feat-title">Band Profiles</div>
          <div className="sb-feat-desc">Complete history for all 104 string bands</div>
        </Link>
        <Link to="/parade" className="sb-feat-card">
          <span className="sb-feat-icon">📅</span>
          <div className="sb-feat-title">Parade History</div>
          <div className="sb-feat-desc">Weather, mayors, routes, and coverage since 1901</div>
        </Link>
        <Link to="/ask" className="sb-feat-card">
          <span className="sb-feat-icon">🤖</span>
          <div className="sb-feat-title">Ask MummSTER AI</div>
          <div className="sb-feat-desc">Ask anything in plain English — powered by MummSTER AI</div>
        </Link>
      </div>

      {latest.length > 0 && (
        <div className="sb-latest">
          <div className="sb-latest-header">
            <h2>{latestYear} Results</h2>
            <span className="sb-year-pill">Contemporary era</span>
            <Link to="/results" className="sb-see-all">See all years →</Link>
          </div>
          <div className="sb-table-wrap">
            <table className="sb-table">
              <thead>
                <tr>
                  <th style={{width:"82px"}}>Video</th>
                  <th>Place</th>
                  <th>Band</th>
                  <th>Total</th>
                  {latest.some(r => r.music_playing) && <>
                    <th>Music</th>
                    <th>GE Music</th>
                    <th>Visual</th>
                    <th>GE Visual</th>
                  </>}
                  <th>Captain</th>
                  <th>Order</th>
                </tr>
              </thead>
              <tbody>
                {latest.map(r => (
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
                              style={{width:"100%", height:"100%", objectFit:"cover",
                                position:"absolute", inset:0}}
                              onError={e => { e.target.style.display="none" }}
                            />
                          )}
                          <div style={{
                            position:"absolute", inset:0, display:"flex",
                            alignItems:"center", justifyContent:"center",
                            background: activeVideo === r.YouTube ? "rgba(0,0,0,0.5)" : "rgba(0,0,0,0.25)"
                          }}>
                            <div style={{width:"20px", height:"20px",
                              background:"rgba(200,168,75,0.85)", borderRadius:"50%",
                              display:"flex", alignItems:"center", justifyContent:"center"}}>
                              <div style={{width:0, height:0, borderStyle:"solid",
                                borderWidth:"4px 0 4px 7px",
                                borderColor:"transparent transparent transparent #0b1220",
                                marginLeft:"1px"}} />
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div style={{width:"82px", height:"46px", background:"#0f1a2b",
                          borderRight:"1px solid #1f3352"}} />
                      )}
                    </td>
                    <td>{r.Place}</td>
                    <td><Link to={`/bands/${bandSlug(r.Band)}`}>{r.Band}</Link></td>
                    <td className="sb-score">{r.total_points || "—"}</td>
                    {latest.some(r => r.music_playing) && <>
                      <td>{r.music_playing || "—"}</td>
                      <td>{r.ge_music || "—"}</td>
                      <td>{r.visual_performance || "—"}</td>
                      <td>{r.ge_visual || "—"}</td>
                    </>}
                    <td>
                      {r.Captain ? (
                        <Link to={`/captains/${captainSlug(r.Captain)}`}>{r.Captain}</Link>
                      ) : "—"}
                    </td>
                    <td>{r.march_order || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {activeVideo && (
            <div style={{background:"#111c2d", border:"1px solid #1f3352",
              borderRadius:"8px", overflow:"hidden", marginTop:"1rem"}}>
              <div style={{display:"flex", alignItems:"center",
                justifyContent:"space-between", padding:"8px 14px",
                background:"#0f1a2b", borderBottom:"1px solid #1f3352"}}>
                <span style={{fontSize:"11px", fontWeight:500, color:"#f4f8fc"}}>
                  {latest.find(r => r.YouTube === activeVideo)?.Band} — {latestYear}
                </span>
                <div style={{display:"flex", alignItems:"center", gap:"8px"}}>
                  <a href={activeVideo.replace("/embed/","/watch?v=")}
                    target="_blank" rel="noopener noreferrer"
                    style={{fontSize:"10px", color:"#9a7e35", textDecoration:"none"}}>
                    Open in YouTube ↗
                  </a>
                  <button onClick={() => setActiveVideo(null)} style={{
                    background:"none", border:"1px solid #1f3352", color:"#6e8faf",
                    borderRadius:"6px", padding:"3px 10px", cursor:"pointer",
                    fontSize:"10px", fontFamily:"inherit"}}>✕ Close</button>
                </div>
              </div>
              <iframe src={activeVideo}
                style={{width:"100%", aspectRatio:"16/9", border:"none", display:"block"}}
                title="Performance video" allowFullScreen
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" />
            </div>
          )}
          <Link to="/results" className="sb-see-all-bottom">See full {latestYear} results →</Link>
        </div>
      )}
    </Layout>
  )
}

export const query = graphql`
  query HomeQuery {
    allSbdbResult(
      filter: { Year: { eq: "2026" } }
      sort: { Place: ASC }
      limit: 14
    ) {
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
      }
    }
  }
`
