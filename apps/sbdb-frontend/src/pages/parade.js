import React, { useState } from "react"
import { graphql, Link } from "gatsby"
import Layout from "../components/Layout"

export default function ParadePage({ data }) {
  const years = data.allSbdbParade.nodes
  const available = years.map(y => y.Year).sort((a, b) => b - a)
  const [selected, setSelected] = useState(available[0])

  const info = years.find(y => y.Year === selected)

  const custards = data.allSbdbCustards.nodes.find(r => r.Year === selected)
  const viewers = data.allSbdbViewers.nodes.find(r => r.Year === selected)
  const lifetime = data.allSbdbLifetime.nodes.filter(r => r.Year === selected)
  const hof = data.allSbdbHof.nodes.find(r => r.Year === selected)
  const officer = data.allSbdbOfficer.nodes.filter(r => r.Year === selected)
  const presidents = data.allSbdbPresidents.nodes.filter(r => r.Year === selected)
  const distinction = data.allSbdbDistinction.nodes.filter(r => r.Year === selected)

  const hasAwards = lifetime.length || officer.length || presidents.length || distinction.length
  const hasHof = hof?.inductees || hof?.old_timers

  const cardStyle = {
    background: "#111c2d", border: "1px solid #1f3352",
    borderRadius: "10px", overflow: "hidden",
  }
  const cardHdrStyle = {
    background: "#0f1a2b", padding: "0.45rem 0.85rem",
    borderBottom: "1px solid #1f3352",
    display: "flex", alignItems: "center", gap: "0.4rem",
  }
  const cardTitleStyle = {
    fontSize: "0.68rem", fontWeight: 600,
    textTransform: "uppercase", letterSpacing: "0.1em", color: "#c8a84b",
  }
  const cardBodyStyle = { padding: "0.75rem 0.85rem" }
  const labelStyle = {
    fontSize: "0.62rem", textTransform: "uppercase",
    letterSpacing: "0.08em", color: "#3a5472", marginBottom: "0.15rem",
  }
  const valStyle = { fontSize: "0.875rem", color: "#d0dcea", lineHeight: 1.4 }
  const subStyle = { fontSize: "0.78rem", color: "#6e8faf", fontStyle: "italic" }
  const captainStyle = { fontSize: "0.78rem", color: "#9a7e35" }
  const divStyle = { borderTop: "1px solid #0f1a2b", margin: "0.4rem 0" }
  const awardItemStyle = { display: "flex", flexDirection: "column", gap: "0.1rem" }

  return (
    <Layout title="Parade History" activePage="parade">

      {/* Year selector + action buttons */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <select
          className="sb-parade-select"
          style={{ marginBottom: 0 }}
          value={selected}
          onChange={e => setSelected(e.target.value)}
        >
          {available.map(y => <option key={y} value={y}>{y}</option>)}
        </select>

        <Link
          to={`/results?year=${selected}`}
          style={{
            display: "inline-flex", alignItems: "center", gap: "0.35rem",
            background: "#111c2d", border: "1px solid #1f3352",
            color: "#d0dcea", fontSize: "0.875rem", fontWeight: 500,
            padding: "0.5rem 1rem", borderRadius: "6px", textDecoration: "none",
            transition: "border-color 0.15s, color 0.15s",
          }}
        >
          🏆 View {selected} Results
        </Link>
      </div>

      {/* Two col: parade facts + annual awards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>

        {/* Parade day facts */}
        {info && (
          <div style={cardStyle}>
            <div style={cardHdrStyle}>
              <span style={{ fontSize: "11px" }}>📅</span>
              <span style={cardTitleStyle}>Parade Day</span>
            </div>
            <div style={{ ...cardBodyStyle, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
              {info.Date && <div><div style={labelStyle}>Date</div><div style={valStyle}>{info.Date}</div></div>}
              {info.Weather && <div><div style={labelStyle}>Weather</div><div style={valStyle}>{info.Weather}</div></div>}
              {info.Temperature && <div><div style={labelStyle}>Temperature</div><div style={valStyle}>{info.Temperature}</div></div>}
              {info.Wind && <div><div style={labelStyle}>Wind</div><div style={valStyle}>{info.Wind}</div></div>}
              {info.Mayor && <div><div style={labelStyle}>Mayor</div><div style={valStyle}>{info.Mayor}</div></div>}
              {info.TV_Station && <div><div style={labelStyle}>TV Coverage</div><div style={valStyle}>{info.TV_Station}</div></div>}
              {info.Route && <div style={{ gridColumn: "span 2" }}><div style={labelStyle}>Route</div><div style={valStyle}>{info.Route}</div></div>}
            </div>
          </div>
        )}

        {/* Annual awards */}
        {hasAwards && (
          <div style={cardStyle}>
            <div style={cardHdrStyle}>
              <span style={{ fontSize: "11px" }}>🏅</span>
              <span style={cardTitleStyle}>Annual Awards</span>
            </div>
            <div style={cardBodyStyle}>
              {lifetime.map((r, i) => (
                <div key={i} style={awardItemStyle}>
                  {i > 0 && <div style={divStyle} />}
                  <div style={labelStyle}>🏅 Lifetime Achievement</div>
                  <div style={valStyle}>{r.Name}</div>
                </div>
              ))}
              {officer.length > 0 && lifetime.length > 0 && <div style={divStyle} />}
              {officer.map((r, i) => (
                <div key={i} style={awardItemStyle}>
                  {i > 0 && <div style={divStyle} />}
                  <div style={labelStyle}>⭐ Officer of the Year</div>
                  <div style={valStyle}>{r.Name}</div>
                </div>
              ))}
              {presidents.length > 0 && (officer.length > 0 || lifetime.length > 0) && <div style={divStyle} />}
              {presidents.map((r, i) => (
                <div key={i} style={awardItemStyle}>
                  {i > 0 && <div style={divStyle} />}
                  <div style={labelStyle}>🎖️ President's Award</div>
                  <div style={valStyle}>{r.Name}</div>
                </div>
              ))}
              {distinction.length > 0 && (lifetime.length > 0 || officer.length > 0 || presidents.length > 0) && <div style={divStyle} />}
              {distinction.map((r, i) => (
                <div key={i} style={awardItemStyle}>
                  {i > 0 && <div style={divStyle} />}
                  <div style={labelStyle}>🌟 Award of Distinction</div>
                  <div style={valStyle}>{r.Name}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Hall of Fame */}
      {hasHof && (
        <div style={{ ...cardStyle, marginBottom: "0.75rem" }}>
          <div style={cardHdrStyle}>
            <span style={{ fontSize: "11px" }}>🏛️</span>
            <span style={cardTitleStyle}>Hall of Fame</span>
          </div>
          <div style={{ ...cardBodyStyle, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            {hof.inductees && (
              <div>
                <div style={labelStyle}>Inductees</div>
                <div style={{ fontSize: "0.875rem", color: "#d0dcea", lineHeight: 1.6 }}>
                  {hof.inductees.split(",").map((n, i) => <div key={i}>{n.trim()}</div>)}
                </div>
              </div>
            )}
            {hof.old_timers && (
              <div>
                <div style={labelStyle}>Old Timers Hall of Fame</div>
                <div style={{ fontSize: "0.875rem", color: "#d0dcea", lineHeight: 1.6 }}>
                  {hof.old_timers.split(",").map((n, i) => <div key={i}>{n.trim()}</div>)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Custards + Viewers */}
      {(custards || viewers) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
          {custards && (
            <div style={cardStyle}>
              <div style={cardHdrStyle}>
                <span style={{ fontSize: "11px" }}>🍦</span>
                <span style={cardTitleStyle}>Custard's Last Stand</span>
              </div>
              <div style={cardBodyStyle}>
                <div style={{ fontSize: "1rem", fontWeight: 500, color: "#f4f8fc", marginBottom: "0.15rem" }}>{custards.Band}</div>
                {custards.theme_title && <div style={subStyle}>"{custards.theme_title}"</div>}
                {custards.Captain && <div style={captainStyle}>Capt. {custards.Captain}</div>}
                {custards.total_points && <div style={{ fontSize: "0.78rem", color: "#3a5472", marginTop: "0.15rem" }}>{custards.total_points} pts</div>}
                {custards.YouTube && (
                  <a href={custards.YouTube.replace("/embed/", "/watch?v=")} target="_blank" rel="noopener noreferrer"
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.78rem", color: "#c8a84b", marginTop: "0.35rem", textDecoration: "none" }}>
                    ▶ Watch performance
                  </a>
                )}
              </div>
            </div>
          )}
          {viewers && (
            <div style={cardStyle}>
              <div style={cardHdrStyle}>
                <span style={{ fontSize: "11px" }}>👁️</span>
                <span style={cardTitleStyle}>Viewer's Choice</span>
              </div>
              <div style={cardBodyStyle}>
                <div style={{ fontSize: "1rem", fontWeight: 500, color: "#f4f8fc", marginBottom: "0.15rem" }}>{viewers.Band}</div>
                {viewers.theme_title && <div style={subStyle}>"{viewers.theme_title}"</div>}
                {viewers.Captain && <div style={captainStyle}>Capt. {viewers.Captain}</div>}
                {viewers.total_points && <div style={{ fontSize: "0.78rem", color: "#3a5472", marginTop: "0.15rem" }}>{viewers.total_points} pts</div>}
                {viewers.YouTube && (
                  <a href={viewers.YouTube.replace("/embed/", "/watch?v=")} target="_blank" rel="noopener noreferrer"
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.78rem", color: "#c8a84b", marginTop: "0.35rem", textDecoration: "none" }}>
                    ▶ Watch performance
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      )}

    </Layout>
  )
}

export const query = graphql`
  query ParadeQuery {
    allSbdbParade(sort: { Year: DESC }) {
      nodes {
        Year
        Date
        Weather
        Temperature
        Wind
        Mayor
        TV_Station
        Route
        Sponsors
      }
    }
    allSbdbCustards(sort: { Year: DESC }) {
      nodes { Year Band theme_title Captain total_points YouTube }
    }
    allSbdbViewers(sort: { Year: DESC }) {
      nodes { Year Band theme_title Captain total_points YouTube }
    }
    allSbdbLifetime(sort: { Year: DESC }) {
      nodes { Year Name }
    }
    allSbdbHof(sort: { Year: DESC }) {
      nodes { Year inductees old_timers }
    }
    allSbdbOfficer(sort: { Year: DESC }) {
      nodes { Year Name }
    }
    allSbdbPresidents(sort: { Year: DESC }) {
      nodes { Year Name }
    }
    allSbdbDistinction(sort: { Year: DESC }) {
      nodes { Year Name }
    }
  }
`
