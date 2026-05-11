import React, { useState } from "react"
import { Link } from "gatsby"

export default function Layout({ children, title, activePage }) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="sb-shell">
      <header className="sb-header">
        <div className="sb-header-inner">
          <Link to="/" className="sb-brand">
            <span className="sb-brand-main">String Band Database</span>
            <span className="sb-brand-sub">Philadelphia Mummers · Est. 1901</span>
          </Link>
          <nav className="sb-nav">
            <Link to="/results" className={activePage === "results" ? "sb-active" : ""}>Results</Link>
            <Link to="/bands" className={activePage === "bands" ? "sb-active" : ""}>Bands</Link>
            <Link to="/parade" className={activePage === "parade" ? "sb-active" : ""}>Parade History</Link>
            <Link to="/search" className={`sb-search-icon${activePage === "search" ? " sb-active" : ""}`} title="Search" aria-label="Search">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ display: "block" }}>
                <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5"/>
                <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </Link>
            <Link to="/ask" className={`sb-ask${activePage === "ask" ? " sb-active" : ""}`}>Ask MummSTER AI</Link>
          </nav>
          <button
            className="sb-hamburger"
            onClick={() => setMenuOpen(o => !o)}
            aria-label="Toggle menu"
          >
            <span></span><span></span><span></span>
          </button>
        </div>
        <div className={`sb-mobile-menu${menuOpen ? " sb-open" : ""}`}>
          <Link to="/results" className={activePage === "results" ? "sb-active" : ""} onClick={() => setMenuOpen(false)}>Results</Link>
          <Link to="/bands" className={activePage === "bands" ? "sb-active" : ""} onClick={() => setMenuOpen(false)}>Bands</Link>
          <Link to="/parade" className={activePage === "parade" ? "sb-active" : ""} onClick={() => setMenuOpen(false)}>Parade History</Link>
          <Link to="/search" className={activePage === "search" ? "sb-active" : ""} onClick={() => setMenuOpen(false)}>Search</Link>
          <Link to="/ask" className={`sb-ask${activePage === "ask" ? " sb-active" : ""}`} onClick={() => setMenuOpen(false)}>Ask MummSTER AI</Link>
        </div>
      </header>
      <main className="sb-main">
        {title && <h1 className="sb-page-title">{title}</h1>}
        {children}
      </main>
      <footer className="sb-footer">
        <p>String Band Database · Philadelphia Mummers String Band Competition History</p>
        <p>Powered by <strong>MummSTER AI</strong> · Built on ARTEMIS</p>
      </footer>
    </div>
  )
}
