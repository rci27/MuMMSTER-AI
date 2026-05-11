import React from "react"

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Inter:wght@400;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html, body, #___gatsby, #gatsby-focus-wrapper {
    background: #0b1220 !important;
    color: #d0dcea;
    font-family: 'Inter', system-ui, sans-serif;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  a { color: #c8a84b; text-decoration: none; }
  a:hover { color: #e2c06a; }
  h1,h2,h3,h4 { font-family: 'Playfair Display', Georgia, serif; color: #f4f8fc; line-height: 1.2; }
  table { border-collapse: collapse; width: 100%; }
  ::selection { background: #c8a84b; color: #0b1220; }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: #111c2d; }
  ::-webkit-scrollbar-thumb { background: #243d60; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #9a7e35; }

  /* ── MOBILE HAMBURGER MENU STATE ── */
  .sb-nav-mobile-open { display: flex; flex-direction: column; }
  .sb-nav-mobile-closed { display: none; }
  .sb-hamburger { display: none; flex-direction: column; gap: 5px; padding: 8px; cursor: pointer; background: none; border: none; }
  .sb-hamburger span { display: block; width: 22px; height: 2px; background: #6e8faf; border-radius: 1px; transition: background 0.15s; }
  .sb-hamburger:hover span { background: #c8a84b; }
  .sb-mobile-menu { display: none; background: #0f1a2b; border-bottom: 1px solid #1f3352; flex-direction: column; }
  .sb-mobile-menu a { color: #6e8faf; font-size: 0.9rem; font-weight: 500; padding: 0.75rem 1.5rem; border-bottom: 1px solid #1a2d47; display: block; transition: color 0.15s, background 0.15s; }
  .sb-mobile-menu a:hover { color: #f4f8fc; background: #16243a; }
  .sb-mobile-menu a.sb-ask { color: #c8a84b; font-weight: 600; }
  .sb-mobile-menu a.sb-active { color: #f4f8fc; }
  .sb-mobile-menu.sb-open { display: flex; }
  .sb-search-icon { display: inline-flex; align-items: center; justify-content: center; color: #6e8faf; padding: 0.4rem 0.6rem; border-radius: 4px; transition: color 0.15s, background 0.15s; }
  .sb-search-icon:hover { color: #f4f8fc; background: #16243a; }
  .sb-search-icon.sb-active { color: #c8a84b; background: #16243a; }

  /* ── TABLET (max 900px) ── */
  @media (max-width: 900px) {
    .sb-header-inner { padding: 0 1.25rem; }
    .sb-main { padding: 2rem 1.25rem 3rem; }
    .sb-feat-grid { grid-template-columns: repeat(2, 1fr); }
    .sb-feat-card:nth-child(2) { border-right: none; }
    .sb-feat-card:nth-child(3) { border-right: 1px solid #1f3352; border-top: 1px solid #1f3352; }
    .sb-feat-card:nth-child(4) { border-right: none; border-top: 1px solid #1f3352; }
    .sb-feat-card:nth-child(3), .sb-feat-card:nth-child(4) { border-bottom: none; }
  }

  /* ── MOBILE (max 640px) ── */
  @media (max-width: 640px) {

    /* Header — hamburger replaces nav */
    .sb-header-inner { padding: 0 1rem; height: 52px; }
    .sb-nav { display: none !important; }
    .sb-hamburger { display: flex !important; }

    /* Main padding */
    .sb-main { padding: 1.5rem 1rem 3rem; }

    /* Page title */
    .sb-page-title { font-size: 1.5rem; margin-bottom: 1.5rem; }

    /* Hero */
    .sb-hero { padding: 2.5rem 0.5rem 2rem; }
    .sb-hero h1 { font-size: 1.9rem; }
    .sb-hero-sub { font-size: 0.9rem; }
    .sb-hero-cta { flex-direction: column; gap: 0.6rem; }
    .sb-btn-gold, .sb-btn-ghost { width: 100%; text-align: center; justify-content: center; padding: 0.85rem 1rem; }

    /* Stats bar — 2x2 grid */
    .sb-stats-bar { display: grid !important; grid-template-columns: 1fr 1fr !important; }
    .sb-stat-item { border-right: 1px solid #1f3352; border-bottom: 1px solid #1f3352; padding: 1rem 0.5rem; }
    .sb-stat-item:nth-child(2n) { border-right: none; }
    .sb-stat-item:nth-child(3), .sb-stat-item:nth-child(4) { border-bottom: none; }
    .sb-stat-num { font-size: 1.6rem; }

    /* Feature grid — 2x2 */
    .sb-feat-grid { grid-template-columns: 1fr 1fr !important; }
    .sb-feat-card { padding: 1rem 0.75rem; }
    .sb-feat-card:nth-child(1) { border-right: 1px solid #1f3352; border-bottom: 1px solid #1f3352; }
    .sb-feat-card:nth-child(2) { border-right: none; border-bottom: 1px solid #1f3352; }
    .sb-feat-card:nth-child(3) { border-right: 1px solid #1f3352; border-bottom: none; border-top: none; }
    .sb-feat-card:nth-child(4) { border-right: none; border-bottom: none; border-top: none; }
    .sb-feat-icon { font-size: 1.2rem; }
    .sb-feat-title { font-size: 0.825rem; }
    .sb-feat-desc { font-size: 0.72rem; }

    /* Latest results table */
    .sb-latest-header { flex-wrap: wrap; gap: 0.4rem; }
    .sb-latest-header h2 { font-size: 1rem; }
    .sb-see-all { margin-left: auto; }
    .sb-latest-table th, .sb-latest-table td { padding: 0.5rem 0.6rem; font-size: 0.82rem; }

    /* Results page controls */
    .sb-controls { gap: 0.6rem; }
    .sb-ctrl-select { font-size: 0.85rem; padding: 0.45rem 1.75rem 0.45rem 0.75rem; }

    /* All tables — reduce padding on mobile */
    .sb-table th { padding: 0.55rem 0.6rem; font-size: 0.62rem; }
    .sb-table td { padding: 0.55rem 0.6rem; font-size: 0.82rem; }

    /* Band profile — stats 2x2 */
    .sb-band-stats-row { grid-template-columns: 1fr 1fr; }
    .sb-bstat { border-right: 1px solid #1f3352; border-bottom: 1px solid #1f3352; padding: 0.85rem 0.5rem; }
    .sb-bstat:nth-child(2n) { border-right: none; }
    .sb-bstat:nth-child(3), .sb-bstat:nth-child(4) { border-bottom: none; }
    .sb-bstat-num { font-size: 1.5rem; }
    .sb-band-title { font-size: 1.9rem; }

    /* Ask panel — stack form vertically */
    .sb-ask-form { flex-direction: column; }
    .sb-ask-btn { width: 100%; padding: 0.85rem; }
    .sb-ask-input { width: 100%; }

    /* Parade */
    .sb-parade-card { padding: 1.25rem; }
    .sb-facts { grid-template-columns: 7rem 1fr; }
    .sb-facts dt, .sb-facts dd { font-size: 0.82rem; padding: 0.5rem 0; }
    .sb-facts dd { padding-left: 0.75rem; }

    /* Bands grid stays 2-col, just tighter */
    .sb-bands-grid { grid-template-columns: 1fr 1fr; gap: 0.6rem; }
    .sb-band-name { font-size: 0.875rem; }

    /* Chart panel */
    .sb-chart-panel { padding: 1rem; }
  }

  /* ── LAYOUT ── */
  .sb-shell { display: flex; flex-direction: column; min-height: 100vh; background: #0b1220; }

  .sb-header {
    position: sticky; top: 0; z-index: 200;
    background: rgba(11,18,32,0.97);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 2px solid #9a7e35;
  }
  .sb-header-inner {
    max-width: 1160px; margin: 0 auto;
    padding: 0 2rem; height: 58px;
    display: flex; align-items: center; justify-content: space-between; gap: 2rem;
  }
  .sb-brand { display: flex; flex-direction: column; gap: 1px; text-decoration: none; }
  .sb-brand-main { font-family: 'Playfair Display', Georgia, serif; font-size: 1.35rem; font-weight: 700; color: #c8a84b; letter-spacing: 0.01em; }
  .sb-brand-sub { font-size: 0.6rem; font-weight: 600; color: #3a5472; text-transform: uppercase; letter-spacing: 0.18em; }
  .sb-brand:hover .sb-brand-main { color: #e2c06a; }

  .sb-nav { display: flex; align-items: center; gap: 0.15rem; }
  .sb-nav a { color: #6e8faf; font-size: 0.875rem; font-weight: 500; padding: 0.4rem 0.85rem; border-radius: 4px; transition: color 0.15s, background 0.15s; white-space: nowrap; }
  .sb-nav a:hover { color: #f4f8fc; background: #16243a; }
  .sb-nav a.sb-active { color: #f4f8fc; background: #16243a; }
  .sb-nav a.sb-ask { color: #c8a84b !important; border: 1px solid #9a7e35; margin-left: 0.4rem; padding: 0.4rem 0.85rem; border-radius: 4px; }
  .sb-nav a.sb-ask:hover, .sb-nav a.sb-ask.sb-active { background: #c8a84b !important; color: #0b1220 !important; }

  .sb-main { flex: 1; max-width: 1160px; width: 100%; margin: 0 auto; padding: 2.5rem 2rem 4rem; }

  .sb-page-title {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 2rem; font-weight: 700; color: #f4f8fc; margin-bottom: 2rem;
    padding-bottom: 1rem; border-bottom: 1px solid #1f3352;
    display: flex; align-items: center; gap: 0.75rem;
  }
  .sb-page-title::before {
    content: ''; display: block; width: 4px; height: 1.75rem;
    background: #c8a84b; border-radius: 2px; flex-shrink: 0;
  }

  .sb-footer { background: #111c2d; border-top: 1px solid #1f3352; padding: 1.75rem 2rem; text-align: center; }
  .sb-footer p { color: #3a5472; font-size: 0.8rem; margin: 0; }
  .sb-footer p + p { margin-top: 0.3rem; }
  .sb-footer strong { color: #9a7e35; }

  /* ── HOME ── */
  .sb-hero {
    text-align: center; padding: 4.5rem 1rem 3.5rem;
    border-bottom: 1px solid #1f3352; position: relative;
  }
  .sb-hero::before {
    content: ''; position: absolute; inset: 0;
    background: radial-gradient(ellipse 80% 55% at 50% 0%, rgba(200,168,75,0.07) 0%, transparent 70%);
    pointer-events: none;
  }
  .sb-hero-badge {
    display: inline-block; background: rgba(200,168,75,0.08);
    border: 1px solid #9a7e35; color: #c8a84b;
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.14em;
    text-transform: uppercase; padding: 0.3rem 1rem;
    border-radius: 99px; margin-bottom: 1.5rem;
  }
  .sb-hero h1 {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: clamp(2.2rem, 5vw, 3.6rem);
    font-weight: 900; color: #f4f8fc;
    margin-bottom: 1.1rem; letter-spacing: -0.02em; line-height: 1.1;
  }
  .sb-hero h1 em { color: #c8a84b; font-style: normal; }
  .sb-hero-sub { font-size: 1.05rem; color: #6e8faf; max-width: 500px; margin: 0 auto 2.25rem; line-height: 1.7; }
  .sb-hero-cta { display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }

  .sb-btn-gold {
    display: inline-flex; align-items: center; gap: 0.4rem;
    background: #c8a84b; color: #0b1220;
    font-family: 'Inter', system-ui, sans-serif;
    font-weight: 700; font-size: 0.9rem;
    padding: 0.7rem 1.6rem; border-radius: 8px;
    transition: background 0.15s, transform 0.15s, box-shadow 0.15s;
    text-decoration: none;
  }
  .sb-btn-gold:hover { background: #e2c06a; color: #0b1220; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(200,168,75,0.25); }

  .sb-btn-ghost {
    display: inline-flex; align-items: center; gap: 0.4rem;
    background: transparent; color: #d0dcea;
    font-family: 'Inter', system-ui, sans-serif;
    font-weight: 500; font-size: 0.9rem;
    padding: 0.7rem 1.6rem; border-radius: 8px;
    border: 1px solid #1f3352;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    text-decoration: none;
  }
  .sb-btn-ghost:hover { border-color: #9a7e35; color: #c8a84b; background: rgba(200,168,75,0.08); }

  .sb-stats-bar { display: flex; border-bottom: 1px solid #1f3352; }
  .sb-stat-item { flex: 1; text-align: center; padding: 1.25rem 0.5rem; border-right: 1px solid #1f3352; }
  .sb-stat-item:last-child { border-right: none; }
  .sb-stat-num { font-family: 'Playfair Display', Georgia, serif; font-size: 1.9rem; font-weight: 700; color: #c8a84b; display: block; line-height: 1; }
  .sb-stat-label { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em; color: #3a5472; margin-top: 0.35rem; display: block; }

  .sb-feat-grid { display: grid; grid-template-columns: repeat(4,1fr); border-bottom: 1px solid #1f3352; }
  .sb-feat-card { padding: 1.5rem 1.25rem; border-right: 1px solid #1f3352; display: block; text-decoration: none; transition: background 0.15s; position: relative; overflow: hidden; }
  .sb-feat-card:last-child { border-right: none; }
  .sb-feat-card:hover { background: #111c2d; }
  .sb-feat-card::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 2px; background: #c8a84b; transform: scaleX(0); transition: transform 0.15s; transform-origin: left; }
  .sb-feat-card:hover::after { transform: scaleX(1); }
  .sb-feat-icon { font-size: 1.5rem; margin-bottom: 0.6rem; display: block; }
  .sb-feat-title { font-size: 0.925rem; font-weight: 600; color: #f4f8fc; margin-bottom: 0.3rem; }
  .sb-feat-desc { font-size: 0.8rem; color: #6e8faf; line-height: 1.5; }

  .sb-latest { padding: 1.75rem 0 0; }
  .sb-latest-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.1rem; }
  .sb-latest-header h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 1.1rem; color: #f4f8fc; }
  .sb-year-pill { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #c8a84b; background: rgba(200,168,75,0.08); border: 1px solid #9a7e35; padding: 0.18rem 0.65rem; border-radius: 99px; }
  .sb-see-all { margin-left: auto; font-size: 0.8rem; color: #6e8faf; transition: color 0.15s; }
  .sb-see-all:hover { color: #c8a84b; }
  .sb-see-all-bottom { display: inline-block; margin-top: 1rem; font-size: 0.8rem; color: #6e8faf; }
  .sb-see-all-bottom:hover { color: #c8a84b; }

  /* ── TABLES (shared) ── */
  .sb-table-wrap { border-radius: 12px; border: 1px solid #1f3352; overflow: hidden; overflow-x: auto; }
  .sb-table th { background: #0f1a2b; padding: 0.7rem 1rem; text-align: left; font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #3a5472; border-bottom: 2px solid #1f3352; white-space: nowrap; }
  .sb-table td { padding: 0.65rem 1rem; font-size: 0.9rem; border-bottom: 1px solid #111c2d; background: #111c2d; white-space: nowrap; }
  .sb-table tbody tr:nth-child(even) td { background: rgba(15,26,43,0.7); }
  .sb-table tbody tr:hover td { background: #16243a; }
  .sb-table tbody tr.sb-winner td { background: rgba(200,168,75,0.04) !important; border-left: 3px solid #c8a84b; }
  .sb-table tbody tr.sb-winner td:first-child { color: #c8a84b; font-weight: 700; }
  .sb-score { color: #e8d49a; font-variant-numeric: tabular-nums; }
  .sb-yt { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; background: rgba(200,168,75,0.1); border-radius: 4px; color: #c8a84b; font-size: 0.7rem; transition: background 0.15s; }
  .sb-yt:hover { background: rgba(200,168,75,0.25); color: #e2c06a; }

  /* ── LATEST TABLE (home) ── */
  .sb-latest-table th { background: #0f1a2b; padding: 0.55rem 0.9rem; text-align: left; font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #3a5472; border-bottom: 1px solid #1f3352; }
  .sb-latest-table td { padding: 0.65rem 0.9rem; font-size: 0.9rem; border-bottom: 1px solid #111c2d; background: #111c2d; }
  .sb-latest-table tbody tr:nth-child(even) td { background: rgba(15,26,43,0.6); }
  .sb-latest-table tbody tr:hover td { background: #16243a; }
  .sb-latest-table tbody tr:first-child td { color: #c8a84b; font-weight: 600; border-left: 3px solid #c8a84b; background: rgba(200,168,75,0.04); }

  /* ── RESULTS PAGE ── */
  .sb-controls { display: flex; align-items: center; gap: 0.9rem; margin-bottom: 1.75rem; flex-wrap: wrap; }
  .sb-ctrl-label { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #3a5472; }
  .sb-ctrl-select {
    background: #111c2d; color: #f4f8fc; border: 1px solid #1f3352;
    border-radius: 8px; padding: 0.5rem 2.25rem 0.5rem 0.9rem;
    font-family: 'Inter', system-ui, sans-serif; font-size: 0.9rem;
    cursor: pointer; transition: border-color 0.15s; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236e8faf' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 0.7rem center;
  }
  .sb-ctrl-select:hover, .sb-ctrl-select:focus { border-color: #9a7e35; outline: none; }
  .sb-band-count { margin-left: auto; font-size: 0.78rem; color: #6e8faf; background: #111c2d; border: 1px solid #1f3352; padding: 0.25rem 0.75rem; border-radius: 99px; }
  .sb-era-note { margin-top: 1rem; font-size: 0.78rem; color: #6e8faf; }

  /* ── ERA BADGES ── */
  .sb-era { display: inline-block; font-size: 0.67rem; font-weight: 600; padding: 0.18rem 0.55rem; border-radius: 99px; text-transform: capitalize; }
  .sb-era-contemporary { background: rgba(45,158,95,0.15); color: #5ecf8a; }
  .sb-era-modern { background: rgba(45,114,200,0.15); color: #6db3f2; }
  .sb-era-premodern { background: rgba(74,74,90,0.3); color: #a0a0b8; }

  /* ── BANDS PAGE ── */
  .sb-bands-controls { display: flex; align-items: center; gap: 0.9rem; margin-bottom: 1.75rem; flex-wrap: wrap; }
  .sb-filter {
    flex: 1; max-width: 380px; background: #111c2d; color: #f4f8fc;
    border: 1px solid #1f3352; border-radius: 8px; padding: 0.6rem 1rem;
    font-family: 'Inter', system-ui, sans-serif; font-size: 0.9rem;
    transition: border-color 0.15s;
  }
  .sb-filter::placeholder { color: #6e8faf; }
  .sb-filter:focus { outline: none; border-color: #9a7e35; box-shadow: 0 0 0 3px rgba(200,168,75,0.1); }
  .sb-bands-count { margin-left: auto; font-size: 0.78rem; color: #6e8faf; background: #111c2d; border: 1px solid #1f3352; padding: 0.25rem 0.75rem; border-radius: 99px; }

  .sb-bands-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(205px,1fr)); gap: 1rem; }
  .sb-band-card { background: #111c2d; border: 1px solid #1f3352; border-radius: 12px; padding: 1.25rem 1.35rem 1.1rem; display: block; text-decoration: none; transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s; position: relative; overflow: hidden; }
  .sb-band-card::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 2px; background: #c8a84b; transform: scaleX(0); transition: transform 0.15s; transform-origin: left; }
  .sb-band-card:hover { border-color: #243d60; transform: translateY(-2px); box-shadow: 0 2px 10px rgba(0,0,0,0.35); }
  .sb-band-card:hover::after { transform: scaleX(1); }
  .sb-band-name { font-family: 'Playfair Display', Georgia, serif; font-size: 1rem; color: #f4f8fc; margin-bottom: 0.6rem; line-height: 1.3; transition: color 0.15s; }
  .sb-band-card:hover .sb-band-name { color: #c8a84b; }
  .sb-band-stats { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .sb-stat-pill { font-size: 0.67rem; font-weight: 500; color: #6e8faf; background: #0f1a2b; padding: 0.18rem 0.55rem; border-radius: 99px; border: 1px solid #1f3352; }
  .sb-win-pill { font-size: 0.67rem; font-weight: 600; color: #c8a84b; background: rgba(200,168,75,0.08); border: 1px solid #9a7e35; padding: 0.18rem 0.55rem; border-radius: 99px; }

  /* ── BAND PROFILE ── */
  .sb-band-back { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.8rem; color: #6e8faf; margin-bottom: 1.5rem; transition: color 0.15s; }
  .sb-band-back:hover { color: #c8a84b; }
  .sb-band-hdr { background: linear-gradient(180deg, #111c2d 0%, #0b1220 100%); padding-bottom: 1.75rem; border-bottom: 1px solid #1f3352; margin-bottom: 0; }
  .sb-band-title { font-family: 'Playfair Display', Georgia, serif; font-size: 2.5rem; font-weight: 900; color: #f4f8fc; margin-bottom: 0.5rem; letter-spacing: -0.01em; }
  .sb-band-eras { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.5rem; }

  .sb-band-stats-row { display: grid; grid-template-columns: repeat(4,1fr); border-bottom: 1px solid #1f3352; }
  .sb-bstat { padding: 1.1rem; text-align: center; border-right: 1px solid #1f3352; }
  .sb-bstat:last-child { border-right: none; }
  .sb-bstat-num { font-family: 'Playfair Display', Georgia, serif; font-size: 1.9rem; font-weight: 700; color: #c8a84b; display: block; line-height: 1; }
  .sb-bstat-label { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #3a5472; margin-top: 0.35rem; display: block; }

  .sb-chart-panel { background: #111c2d; border: 1px solid #1f3352; border-radius: 12px; padding: 1.35rem 1.5rem; margin-bottom: 2rem; }
  .sb-chart-title { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #3a5472; margin-bottom: 1rem; }
  .sb-chart-svg { width: 100%; max-width: 700px; display: block; }
  .sb-chart-labels { display: flex; justify-content: space-between; font-size: 0.67rem; color: #3a5472; margin-top: 0.3rem; max-width: 700px; }
  .sb-chart-note { font-size: 0.67rem; color: #3a5472; margin-top: 0.4rem; }
  .sb-history-title { font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #6e8faf; margin-bottom: 0.9rem; margin-top: 2rem; }

  /* ── PARADE PAGE ── */
  .sb-parade-select {
    background: #111c2d; color: #f4f8fc; border: 1px solid #1f3352;
    border-radius: 8px; padding: 0.6rem 2.25rem 0.6rem 0.9rem;
    font-family: 'Inter', system-ui, sans-serif; font-size: 1rem;
    cursor: pointer; min-width: 130px; margin-bottom: 2rem; display: block;
    transition: border-color 0.15s; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236e8faf' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 0.7rem center;
  }
  .sb-parade-select:hover, .sb-parade-select:focus { border-color: #9a7e35; outline: none; }
  .sb-parade-card { background: #111c2d; border: 1px solid #1f3352; border-radius: 12px; padding: 1.75rem 2rem; max-width: 640px; }
  .sb-parade-year { font-family: 'Playfair Display', Georgia, serif; font-size: 1.8rem; font-weight: 700; color: #c8a84b; margin-bottom: 1.35rem; padding-bottom: 1rem; border-bottom: 1px solid #1f3352; }
  .sb-facts { display: grid; grid-template-columns: 9rem 1fr; }
  .sb-facts dt { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #3a5472; padding: 0.65rem 0; border-bottom: 1px solid #0f1a2b; display: flex; align-items: center; }
  .sb-facts dd { font-size: 0.9rem; color: #d0dcea; padding: 0.65rem 0 0.65rem 1rem; border-bottom: 1px solid #0f1a2b; }

  /* ── ASK PAGE ── */
  .sb-ask-intro { color: #6e8faf; font-size: 0.9rem; max-width: 640px; margin-bottom: 2rem; line-height: 1.7; }
  .sb-ask-panel { max-width: 900px; }
  .sb-ask-form { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; }
  .sb-ask-input {
    flex: 1; background: #0f1a2b; color: #f4f8fc;
    border: 1px solid #243d60; border-radius: 8px;
    padding: 0.75rem 1.1rem;
    font-family: 'Inter', system-ui, sans-serif; font-size: 0.95rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .sb-ask-input::placeholder { color: #6e8faf; }
  .sb-ask-input:focus { outline: none; border-color: #9a7e35; box-shadow: 0 0 0 3px rgba(200,168,75,0.1); }
  .sb-ask-btn {
    background: #c8a84b; color: #0b1220; border: none; border-radius: 6px;
    padding: 0.75rem 1.75rem; font-family: 'Inter', system-ui, sans-serif;
    font-weight: 700; font-size: 0.95rem; cursor: pointer; white-space: nowrap;
    transition: background 0.15s, transform 0.15s, box-shadow 0.15s;
  }
  .sb-ask-btn:hover:not(:disabled) { background: #e2c06a; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(200,168,75,0.3); }
  .sb-ask-btn:disabled { opacity: 0.45; cursor: not-allowed; }

  .sb-ask-status { font-size: 0.82rem; color: #9a7e35; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; font-style: italic; }
  .sb-ask-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #c8a84b; animation: sbpulse 1s ease-in-out infinite; flex-shrink: 0; }
  @keyframes sbpulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.3;transform:scale(0.75)} }
  .sb-ask-error { font-size: 0.875rem; color: #f08080; margin-bottom: 1rem; background: rgba(208,80,80,0.1); padding: 0.75rem 1rem; border-radius: 8px; border-left: 3px solid #d05050; }

  .sb-sql-block { margin-bottom: 1.25rem; }
  .sb-sql-toggle { background: none; border: 1px solid #1f3352; color: #6e8faf; border-radius: 4px; padding: 0.28rem 0.75rem; font-family: 'Inter', system-ui, sans-serif; font-size: 0.75rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
  .sb-sql-toggle:hover { color: #c8a84b; border-color: #9a7e35; }
  .sb-sql-code { margin-top: 0.75rem; background: #0f1a2b; border: 1px solid #1f3352; border-radius: 8px; padding: 1rem 1.25rem; font-size: 0.78rem; color: #e8d49a; overflow-x: auto; white-space: pre; line-height: 1.55; font-family: monospace; }

  .sb-interp { background: #13223a; border: 1px solid #1f3352; border-left: 3px solid #c8a84b; border-radius: 0 8px 8px 0; padding: 1.25rem 1.5rem; margin-bottom: 1.5rem; font-size: 0.9rem; line-height: 1.75; color: #d0dcea; box-shadow: inset 0 0 0 1px #1f3352; }
  .sb-interp h1, .sb-interp h2 { font-family: 'Playfair Display', Georgia, serif; color: #f4f8fc; margin: 1.25rem 0 0.6rem; font-size: 1.15rem; }
  .sb-interp h3 { font-family: 'Playfair Display', Georgia, serif; color: #e8d49a; margin: 1rem 0 0.5rem; font-size: 1rem; }
  .sb-interp strong { color: #f4f8fc; }
  .sb-interp em { color: #e8d49a; font-style: italic; }
  .sb-interp hr { border: none; border-top: 1px solid #1f3352; margin: 1rem 0; }
  .sb-interp table { margin: 1rem 0; border-radius: 8px; overflow: hidden; border: 1px solid #1f3352; }
  .sb-interp th { background: #0f1a2b; padding: 0.5rem 0.85rem; text-align: left; font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #3a5472; border-bottom: 1px solid #1f3352; }
  .sb-interp td { padding: 0.5rem 0.85rem; font-size: 0.875rem; border-bottom: 1px solid #111c2d; }
  .sb-interp tr:nth-child(even) td { background: rgba(15,26,43,0.5); }
  .sb-interp li { margin: 0.3rem 0 0.3rem 1.25rem; }

  .sb-result-wrap { overflow-x: auto; border-radius: 12px; border: 1px solid #1f3352; margin-bottom: 1.5rem; overflow: hidden; }
  .sb-chart-wrap { background: #111c2d; border: 1px solid #1f3352; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .sb-trunc { font-size: 0.75rem; color: #6e8faf; padding: 0.5rem 0.9rem; background: #0f1a2b; }

  .sb-followup { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; font-size: 0.8rem; color: #6e8faf; padding: 1rem 0; border-top: 1px solid #1f3352; }
  .sb-followup-btn { background: none; border: 1px solid #1f3352; color: #9a7e35; border-radius: 8px; padding: 0.3rem 0.85rem; font-family: 'Inter', system-ui, sans-serif; font-size: 0.8rem; cursor: pointer; font-style: italic; transition: color 0.15s, border-color 0.15s, background 0.15s; }
  .sb-followup-btn:hover { color: #c8a84b; border-color: #9a7e35; background: rgba(200,168,75,0.08); }

  .sb-examples { margin-top: 3rem; padding-top: 2rem; border-top: 1px solid #1f3352; }
  .sb-examples-label { font-size: 0.67rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em; color: #3a5472; margin-bottom: 0.85rem; }
  .sb-examples ul { list-style: none; display: flex; flex-direction: column; gap: 0.4rem; }
  .sb-examples li { font-size: 0.875rem; color: #6e8faf; padding-left: 1.1rem; position: relative; }
  .sb-examples li::before { content: "→"; position: absolute; left: 0; color: #9a7e35; }
`

export function onRenderBody({ setHeadComponents, setBodyAttributes }) {
  setBodyAttributes({
    style: {
      background: "#0b1220",
      color: "#d0dcea",
      fontFamily: "'Inter', system-ui, sans-serif",
    }
  })
  setHeadComponents([
    <style key="sbdb-styles" dangerouslySetInnerHTML={{ __html: CSS }} />,
    <link key="favicon" rel="icon" type="image/png" href="/favicon.png" />,
    <link key="favicon-apple" rel="apple-touch-icon" href="/favicon.png" />,
  ])
}
