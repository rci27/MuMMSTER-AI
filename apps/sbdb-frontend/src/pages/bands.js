import React, { useState } from "react"
import { graphql, Link } from "gatsby"
import Layout from "../components/Layout"

function LogoCol({ name, slug }) {
  const [failed, setFailed] = React.useState(false)
  if (failed) {
    return (
      <div style={{
        width: "52px", height: "52px", borderRadius: "8px",
        background: "rgba(200,168,75,0.12)", border: "1px solid #9a7e35",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "22px", fontWeight: 500,
        fontFamily: "'Playfair Display', Georgia, serif",
        color: "#c8a84b",
      }}>
        {name.charAt(0).toUpperCase()}
      </div>
    )
  }
  return (
    <img
      src={`/logos/${slug}.png`}
      alt={name}
      onError={() => setFailed(true)}
      style={{ width: "56px", height: "56px", objectFit: "contain", borderRadius: "6px" }}
    />
  )
}

const CONTACT_DATA = {
  "aqua": {
    website: "www.AquaStringBand.com",
    phone: "215-831-8709",
    email: "info@AquaStringBand.com",
  },
}

export default function BandsPage({ data }) {
  const [filter, setFilter] = useState("")
  const [showAllHistorical, setShowAllHistorical] = useState(false)

  const allResults = data.allSbdbResult.nodes

  const latestYear = Math.max(...allResults.map(r => parseInt(r.Year)).filter(Boolean)).toString()

  const activeBandNames = new Set(
    allResults.filter(r => r.Year === latestYear).map(r => r.Band)
  )

  const bandMap = {}
  for (const r of allResults) {
    const key = r.Band
    if (!bandMap[key]) {
      bandMap[key] = {
        name: key,
        slug: key.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""),
        years: [],
        wins: 0,
      }
    }
    bandMap[key].years.push(parseInt(r.Year))
    if (String(r.Place) === "1") bandMap[key].wins++
  }

  const bands = Object.values(bandMap).map(b => ({
    ...b,
    firstYear: Math.min(...b.years),
    lastYear: Math.max(...b.years),
    appearances: b.years.length,
    isActive: activeBandNames.has(b.name),
  }))

  const filtered = filter.trim()
    ? bands.filter(b => b.name.toLowerCase().includes(filter.trim().toLowerCase()))
    : bands

  const activeBands = filtered
    .filter(b => b.isActive)
    .sort((a, b) => a.name.localeCompare(b.name))

  const historicalBands = filtered
    .filter(b => !b.isActive)
    .sort((a, b) => {
      if (b.lastYear !== a.lastYear) return b.lastYear - a.lastYear
      return a.name.localeCompare(b.name)
    })

  const visibleHistorical = showAllHistorical ? historicalBands : historicalBands.slice(0, 18)

  function ActiveCard({ band }) {
    const contact = CONTACT_DATA[band.slug] || {}
    return (
      <Link to={`/bands/${band.slug}`} style={{ textDecoration: "none" }}>
        <div style={{
          background: "#111c2d", border: "1px solid #1f3352",
          borderRadius: "10px", overflow: "hidden",
          transition: "border-color 0.15s, transform 0.15s",
          display: "flex", height: "100%",
        }}
          onMouseEnter={e => { e.currentTarget.style.borderColor="#9a7e35"; e.currentTarget.style.transform="translateY(-2px)" }}
          onMouseLeave={e => { e.currentTarget.style.borderColor="#1f3352"; e.currentTarget.style.transform="translateY(0)" }}
        >
          <div style={{
            width: "76px", minHeight: "100px",
            background: "transparent",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0, borderRight: "1px solid #1f3352",
          }}>
            <LogoCol name={band.name} slug={band.slug} />
          </div>
          <div style={{ padding: "10px 12px", flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: "12px", fontWeight: 500, color: "#f4f8fc",
              marginBottom: "4px", whiteSpace: "nowrap",
              overflow: "hidden", textOverflow: "ellipsis",
            }}>{band.name}</div>
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginBottom: "8px" }}>
              <span style={{ fontSize: "8px", color: "#6e8faf", background: "#0f1a2b", padding: "2px 5px", borderRadius: "99px", border: "1px solid #1f3352" }}>
                {band.firstYear}–{band.lastYear}
              </span>
              <span style={{ fontSize: "8px", color: "#6e8faf", background: "#0f1a2b", padding: "2px 5px", borderRadius: "99px", border: "1px solid #1f3352" }}>
                {band.appearances} parades
              </span>
              {band.wins > 0 && (
                <span style={{ fontSize: "8px", color: "#c8a84b", background: "rgba(200,168,75,0.08)", border: "1px solid #9a7e35", padding: "2px 5px", borderRadius: "99px" }}>
                  {band.wins} 🏆
                </span>
              )}
            </div>
            {contact.website ? (
              <div style={{ display: "flex", alignItems: "center", gap: "5px", marginBottom: "3px" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#3a5472" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                <span style={{ fontSize: "9px", color: "#9a7e35" }}>{contact.website}</span>
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: "5px", marginBottom: "3px" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1f3352" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                <span style={{ fontSize: "9px", color: "#243d60", fontStyle: "italic" }}>website not on file</span>
              </div>
            )}
            {contact.phone ? (
              <div style={{ display: "flex", alignItems: "center", gap: "5px", marginBottom: "3px" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#3a5472" strokeWidth="2" strokeLinecap="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.1 19.79 19.79 0 0 1 1.61 4.5 2 2 0 0 1 3.6 2.32h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 9.91a16 16 0 0 0 6.06 6.06l1.95-1.95a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                <span style={{ fontSize: "9px", color: "#9a7e35" }}>{contact.phone}</span>
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: "5px", marginBottom: "3px" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1f3352" strokeWidth="2" strokeLinecap="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.1 19.79 19.79 0 0 1 1.61 4.5 2 2 0 0 1 3.6 2.32h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 9.91a16 16 0 0 0 6.06 6.06l1.95-1.95a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                <span style={{ fontSize: "9px", color: "#243d60", fontStyle: "italic" }}>phone not on file</span>
              </div>
            )}
            {contact.email ? (
              <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#3a5472" strokeWidth="2" strokeLinecap="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                <span style={{ fontSize: "9px", color: "#9a7e35" }}>{contact.email}</span>
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1f3352" strokeWidth="2" strokeLinecap="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                <span style={{ fontSize: "9px", color: "#243d60", fontStyle: "italic" }}>email not on file</span>
              </div>
            )}
          </div>
        </div>
      </Link>
    )
  }

  return (
    <Layout title="String Bands" activePage="bands">

      <div style={{ display: "flex", alignItems: "center", gap: "0.9rem", marginBottom: "1.75rem", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Filter bands..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="sb-filter"
          style={{ maxWidth: "380px" }}
        />
        <span className="sb-bands-count">{activeBands.length + historicalBands.length} bands</span>
      </div>

      {activeBands.length > 0 && (
        <div style={{ marginBottom: "2.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
            <span style={{ fontSize: "0.72rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#f4f8fc" }}>
              Active Bands
            </span>
            <span style={{ fontSize: "0.68rem", color: "#2d9e5f", background: "rgba(45,158,95,0.15)", border: "1px solid rgba(45,158,95,0.3)", padding: "2px 8px", borderRadius: "99px" }}>
              {latestYear} season
            </span>
            <span style={{ fontSize: "0.72rem", color: "#3a5472" }}>{activeBands.length} bands</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "10px" }}>
            {activeBands.map(b => <ActiveCard key={b.name} band={b} />)}
          </div>
        </div>
      )}

      {historicalBands.length > 0 && (
        <div>
          <div style={{ borderTop: "1px solid #1f3352", marginBottom: "1.5rem" }} />
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
            <span style={{ fontSize: "0.72rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#f4f8fc" }}>
              Historical Bands
            </span>
            <span style={{ fontSize: "0.68rem", color: "#6e8faf", background: "#111c2d", border: "1px solid #1f3352", padding: "2px 8px", borderRadius: "99px" }}>
              no longer active
            </span>
            <span style={{ fontSize: "0.72rem", color: "#3a5472" }}>{historicalBands.length} bands · sorted by last appearance</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "8px" }}>
            {visibleHistorical.map(b => (
              <Link key={b.name} to={`/bands/${b.slug}`} style={{ textDecoration: "none" }}>
                <div style={{
                  background: "#111c2d", border: "1px solid #1f3352",
                  borderRadius: "8px", padding: "10px 12px",
                  transition: "border-color 0.15s, transform 0.15s",
                }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor="#243d60"; e.currentTarget.style.transform="translateY(-2px)" }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor="#1f3352"; e.currentTarget.style.transform="translateY(0)" }}
                >
                  <div style={{ fontSize: "11px", fontWeight: 500, color: "#d0dcea", marginBottom: "5px" }}>{b.name}</div>
                  <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                    <span style={{ fontSize: "8px", color: "#6e8faf", background: "#0f1a2b", padding: "2px 5px", borderRadius: "99px", border: "1px solid #16243a" }}>
                      Last: {b.lastYear}
                    </span>
                    {b.wins > 0 && (
                      <span style={{ fontSize: "8px", color: "#c8a84b", background: "rgba(200,168,75,0.08)", border: "1px solid #9a7e35", padding: "2px 5px", borderRadius: "99px" }}>
                        {b.wins} 🏆
                      </span>
                    )}
                    <span style={{ fontSize: "8px", color: "#3a5472", background: "#0f1a2b", padding: "2px 5px", borderRadius: "99px", border: "1px solid #16243a" }}>
                      {b.appearances} parades
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>

          {!showAllHistorical && historicalBands.length > 18 && (
            <button
              onClick={() => setShowAllHistorical(true)}
              style={{
                display: "block", width: "100%", marginTop: "1rem",
                background: "none", border: "1px dashed #1f3352",
                color: "#3a5472", borderRadius: "8px", padding: "10px",
                cursor: "pointer", fontSize: "11px", fontFamily: "inherit",
                transition: "color 0.15s, border-color 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.color="#6e8faf"; e.currentTarget.style.borderColor="#243d60" }}
              onMouseLeave={e => { e.currentTarget.style.color="#3a5472"; e.currentTarget.style.borderColor="#1f3352" }}
            >
              Show all {historicalBands.length} historical bands ↓
            </button>
          )}
          {showAllHistorical && (
            <button
              onClick={() => setShowAllHistorical(false)}
              style={{
                display: "block", width: "100%", marginTop: "1rem",
                background: "none", border: "1px dashed #1f3352",
                color: "#3a5472", borderRadius: "8px", padding: "10px",
                cursor: "pointer", fontSize: "11px", fontFamily: "inherit",
              }}
            >
              Show less ↑
            </button>
          )}
        </div>
      )}
    </Layout>
  )
}

export const query = graphql`
  query BandsQuery {
    allSbdbResult {
      nodes {
        Year
        Place
        Band
      }
    }
  }
`
