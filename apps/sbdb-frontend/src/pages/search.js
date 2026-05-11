import React, { useState, useMemo } from "react"
import { graphql, Link } from "gatsby"
import Layout from "../components/Layout"

export default function SearchPage({ data }) {
  const [query, setQuery] = useState("")

  const allResults = data.allSbdbResult.nodes
  const allParade = data.allSbdbParade.nodes
  const allHof = data.allSbdbHof.nodes
  const allLifetime = data.allSbdbLifetime.nodes
  const allOfficer = data.allSbdbOfficer.nodes
  const allPresidents = data.allSbdbPresidents.nodes
  const allDistinction = data.allSbdbDistinction.nodes
  const allCustards = data.allSbdbCustards.nodes
  const allViewers = data.allSbdbViewers.nodes

  function bandSlug(name) {
    return name.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
  }

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return null

    // Band matches — unique bands matching query
    const bandMap = {}
    for (const r of allResults) {
      const key = r.Band
      if (!bandMap[key]) bandMap[key] = { name: r.Band, years: [], wins: 0, lastYear: 0 }
      bandMap[key].years.push(parseInt(r.Year))
      if (String(r.Place) === "1") bandMap[key].wins++
      if (parseInt(r.Year) > bandMap[key].lastYear) {
        bandMap[key].lastYear = parseInt(r.Year)
        bandMap[key].lastPlace = r.Place
      }
    }
    const bands = Object.values(bandMap)
      .filter(b => b.name.toLowerCase().includes(q))
      .map(b => ({ ...b, firstYear: Math.min(...b.years), lastYear: Math.max(...b.years) }))
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, 10)

    // Competition result matches — by captain, theme, or year+band
    const compMatches = allResults.filter(r =>
      (r.Captain || "").toLowerCase().includes(q) ||
      (r.theme_title || "").toLowerCase().includes(q) ||
      (r.Year || "").toString().includes(q)
    ).slice(0, 20)

    // Parade matches
    const paradeMatches = allParade.filter(r =>
      (r.Year || "").toString().includes(q) ||
      (r.Mayor || "").toLowerCase().includes(q) ||
      (r.Weather || "").toLowerCase().includes(q) ||
      (r.TV_Station || "").toLowerCase().includes(q)
    ).slice(0, 5)

    // Award matches
    const awardMatches = []
    for (const r of allHof) {
      if (r.inductees && r.inductees.toLowerCase().includes(q))
        awardMatches.push({ icon: "🏛️", type: "Hall of Fame", name: r.inductees, year: r.Year })
      if (r.old_timers && r.old_timers.toLowerCase().includes(q))
        awardMatches.push({ icon: "🏛️", type: "Old Timers HOF", name: r.old_timers, year: r.Year })
    }
    for (const r of allLifetime) {
      if ((r.Name || "").toLowerCase().includes(q))
        awardMatches.push({ icon: "🏅", type: "Lifetime Achievement", name: r.Name, year: r.Year })
    }
    for (const r of allOfficer) {
      if ((r.Name || "").toLowerCase().includes(q))
        awardMatches.push({ icon: "⭐", type: "Officer of the Year", name: r.Name, year: r.Year })
    }
    for (const r of allPresidents) {
      if ((r.Name || "").toLowerCase().includes(q))
        awardMatches.push({ icon: "🎖️", type: "President's Award", name: r.Name, year: r.Year })
    }
    for (const r of allDistinction) {
      if ((r.Name || "").toLowerCase().includes(q))
        awardMatches.push({ icon: "🌟", type: "Award of Distinction", name: r.Name, year: r.Year })
    }
    for (const r of allCustards) {
      if (
        (r.Band || "").toLowerCase().includes(q) ||
        (r.theme_title || "").toLowerCase().includes(q) ||
        (r.Captain || "").toLowerCase().includes(q)
      )
        awardMatches.push({ icon: "🍦", type: "Custard's Last Stand", name: r.Band, detail: r.theme_title, year: r.Year })
    }
    for (const r of allViewers) {
      if (
        (r.Band || "").toLowerCase().includes(q) ||
        (r.theme_title || "").toLowerCase().includes(q) ||
        (r.Captain || "").toLowerCase().includes(q)
      )
        awardMatches.push({ icon: "👁️", type: "Viewer's Choice", name: r.Band, detail: r.theme_title, year: r.Year })
    }
    awardMatches.sort((a, b) => b.year - a.year)

    return {
      bands,
      compMatches,
      paradeMatches,
      awardMatches,
      total: bands.length + compMatches.length + paradeMatches.length + awardMatches.length,
    }
  }, [query, allResults, allParade, allHof, allLifetime, allOfficer, allPresidents, allDistinction, allCustards, allViewers])

  const sectionLabelStyle = {
    fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase",
    letterSpacing: "0.12em", color: "#9a7e35", marginBottom: "0.75rem",
    display: "flex", alignItems: "center", gap: "0.4rem",
  }
  const countStyle = { color: "#3a5472" }
  const wrapStyle = { background: "#111c2d", border: "1px solid #1f3352", borderRadius: "8px", overflow: "hidden" }
  const rowStyle = { display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.85rem", borderBottom: "1px solid #0f1a2b" }
  const lastRowStyle = { display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.85rem" }

  return (
    <Layout title="Search" activePage="search">
      <div style={{ maxWidth: "680px" }}>
        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "2rem" }}>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search bands, captains, themes, years, mayors..."
            className="sb-filter"
            style={{ flex: 1, maxWidth: "100%", fontSize: "1rem", padding: "0.75rem 1rem" }}
            autoFocus
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              style={{ background: "#111c2d", border: "1px solid #1f3352", color: "#6e8faf", borderRadius: "8px", padding: "0 1rem", cursor: "pointer", fontSize: "0.9rem", whiteSpace: "nowrap" }}
            >
              Clear
            </button>
          )}
        </div>

        {query.length > 0 && query.length < 2 && (
          <p style={{ color: "#6e8faf", fontSize: "0.875rem" }}>Type at least 2 characters to search...</p>
        )}

        {results && results.total === 0 && (
          <p style={{ color: "#6e8faf", fontSize: "0.875rem" }}>No results found for "{query}"</p>
        )}

        {results && results.total > 0 && (
          <p style={{ color: "#3a5472", fontSize: "0.78rem", marginBottom: "1.5rem", textTransform: "uppercase", letterSpacing: "0.1em" }}>
            {results.total} result{results.total !== 1 ? "s" : ""} for "{query}"
          </p>
        )}

        {/* Band results */}
        {results && results.bands.length > 0 && (
          <div style={{ marginBottom: "2rem" }}>
            <div style={sectionLabelStyle}>
              Bands <span style={countStyle}>({results.bands.length})</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {results.bands.map(b => (
                <Link key={b.name} to={`/bands/${bandSlug(b.name)}`} style={{ background: "#111c2d", border: "1px solid #1f3352", borderRadius: "8px", padding: "0.85rem 1rem", display: "flex", alignItems: "center", justifyContent: "space-between", textDecoration: "none", transition: "border-color 0.15s" }}>
                  <div>
                    <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: "1rem", color: "#f4f8fc", marginBottom: "0.25rem" }}>{b.name}</div>
                    <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                      <span style={{ fontSize: "0.68rem", color: "#6e8faf", background: "#0f1a2b", padding: "2px 6px", borderRadius: "99px", border: "1px solid #1f3352" }}>{b.firstYear}–{b.lastYear}</span>
                      <span style={{ fontSize: "0.68rem", color: "#6e8faf", background: "#0f1a2b", padding: "2px 6px", borderRadius: "99px", border: "1px solid #1f3352" }}>{b.years.length} parades</span>
                      {b.wins > 0 && <span style={{ fontSize: "0.68rem", color: "#c8a84b", background: "rgba(200,168,75,0.08)", padding: "2px 6px", borderRadius: "99px", border: "1px solid #9a7e35" }}>{b.wins} 🏆</span>}
                    </div>
                  </div>
                  <span style={{ color: "#3a5472", fontSize: "0.85rem" }}>→</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Awards & Recognition */}
        {results && results.awardMatches.length > 0 && (
          <div style={{ marginBottom: "1.25rem" }}>
            <div style={sectionLabelStyle}>
              🏅 Awards & Recognition
              <span style={countStyle}>({results.awardMatches.length})</span>
            </div>
            <div style={wrapStyle}>
              {results.awardMatches.map((a, i) => (
                <div key={i} style={i === results.awardMatches.length - 1 ? lastRowStyle : rowStyle}>
                  <span style={{ fontSize: "14px", flexShrink: 0, width: "20px", textAlign: "center" }}>{a.icon}</span>
                  <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#9a7e35", minWidth: "140px", flexShrink: 0 }}>{a.type}</span>
                  <span style={{ fontSize: "0.875rem", color: "#f4f8fc", flex: 1 }}>
                    {a.name}
                    {a.detail && <span style={{ color: "#6e8faf", fontStyle: "italic", marginLeft: "0.4rem" }}>"{a.detail}"</span>}
                  </span>
                  <span style={{ fontSize: "0.78rem", color: "#3a5472", flexShrink: 0 }}>{a.year}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Competition results */}
        {results && results.compMatches.length > 0 && (
          <div style={{ marginBottom: "2rem" }}>
            <div style={sectionLabelStyle}>
              Competition Results <span style={countStyle}>({results.compMatches.length}{results.compMatches.length === 20 ? "+" : ""})</span>
            </div>
            <div className="sb-table-wrap">
              <table className="sb-table">
                <thead>
                  <tr>
                    <th>Year</th>
                    <th>Band</th>
                    <th>Place</th>
                    <th>Captain</th>
                    <th>Theme</th>
                  </tr>
                </thead>
                <tbody>
                  {results.compMatches.map((r, i) => (
                    <tr key={i} className={String(r.Place) === "1" ? "sb-winner" : ""}>
                      <td>{r.Year}</td>
                      <td><Link to={`/bands/${bandSlug(r.Band)}`}>{r.Band}</Link></td>
                      <td>{r.Place}</td>
                      <td>{r.Captain || "—"}</td>
                      <td>{r.theme_title || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Parade results */}
        {results && results.paradeMatches.length > 0 && (
          <div style={{ marginBottom: "2rem" }}>
            <div style={sectionLabelStyle}>
              Parade History <span style={countStyle}>({results.paradeMatches.length})</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {results.paradeMatches.map(p => (
                <div key={p.Year} style={{ background: "#111c2d", border: "1px solid #1f3352", borderRadius: "8px", padding: "0.85rem 1rem" }}>
                  <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: "1rem", color: "#c8a84b", marginBottom: "0.3rem" }}>{p.Year} Parade</div>
                  <div style={{ fontSize: "0.82rem", color: "#6e8faf" }}>
                    {[p.Mayor && `Mayor: ${p.Mayor}`, p.Weather, p.Temperature].filter(Boolean).join(" · ")}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!query && (
          <div style={{ color: "#3a5472", fontSize: "0.875rem", lineHeight: "1.7" }}>
            <p>Search across all 1,960 competition records, 104 bands, 125 years of parade history, and all awards.</p>
            <p style={{ marginTop: "0.5rem" }}>Try searching a band name, captain, theme, year, mayor, or award recipient.</p>
          </div>
        )}
      </div>
    </Layout>
  )
}

export const query = graphql`
  query SearchQuery {
    allSbdbResult {
      nodes {
        Year
        Place
        Band
        Captain
        theme_title
        total_points
      }
    }
    allSbdbParade {
      nodes {
        Year
        Mayor
        Weather
        Temperature
        TV_Station
      }
    }
    allSbdbHof {
      nodes { Year inductees old_timers }
    }
    allSbdbLifetime {
      nodes { Year Name }
    }
    allSbdbOfficer {
      nodes { Year Name }
    }
    allSbdbPresidents {
      nodes { Year Name }
    }
    allSbdbDistinction {
      nodes { Year Name }
    }
    allSbdbCustards {
      nodes { Year Band theme_title Captain }
    }
    allSbdbViewers {
      nodes { Year Band theme_title Captain }
    }
  }
`
