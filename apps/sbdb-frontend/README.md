# sbdb-frontend (LXC 127)

The public-facing String Band Database website. Gatsby 5 + React 18, served as static HTML by nginx behind a Cloudflare Tunnel.

Live at **[sbdb-ai.theronlab.com](https://sbdb-ai.theronlab.com)**.

## Stack

- Gatsby 5 (static site generator)
- React 18
- Chart.js (inline stats charts)
- nginx (serves the built site, port 3000)
- Cloudflare Tunnel (public exposure)

## How it works

Gatsby fetches all data from LXC 124's Datasette JSON API **at build time**, then renders every page to static HTML. After build, there are no runtime database calls — nginx serves static files. This means:

- The public site has no database connection
- Every page is cheap to serve at scale
- Updates require a fresh build (via `update-sbdb-frontend-source` broker action)

## Pages

| Path                    | Content                                                       |
|-------------------------|---------------------------------------------------------------|
| `/`                     | Home — latest year results, hero, stats bar                   |
| `/results`              | All-years results browser with year selector                  |
| `/bands`                | Band grid with filter and search                              |
| `/bands/[slug]`         | Per-band profile with placement history chart                 |
| `/captains/[slug]`      | Per-captain profile (~311 auto-generated pages)               |
| `/parade`               | Parade-day history with four-card layout per year             |
| `/search`               | Global cross-table search                                     |
| `/ask`                  | AI query interface — calls LXC 128 via SSE                    |

## Design

- Dark navy charcoal background: `#0f1720`
- Gold accents: `#c8a84b`
- Headings: Playfair Display
- Body: Source Sans 3
- Aesthetic: archival record, not generic web app

## Key files

| File                    | Purpose                                              |
|-------------------------|------------------------------------------------------|
| `gatsby-node.js`        | Build-time data loader — fetches from Datasette, generates per-band and per-captain pages |
| `gatsby-config.js`      | Site metadata, plugin configuration                  |
| `src/pages/index.js`    | Home page                                            |
| `src/pages/results.js`  | All-years results browser                            |
| `src/pages/bands.js`    | Band grid                                            |
| `src/pages/parade.js`   | Parade-day history                                   |
| `src/pages/search.js`   | Global search                                        |
| `src/pages/ask.js`      | AI query interface                                   |
| `src/templates/band.js` | Per-band detail template                             |
| `src/templates/captain.js` | Per-captain detail template                       |
| `package.json`          | Node dependencies                                    |

## Build

```bash
npm install
npm run build
```

The build process inside the container fetches from `http://192.168.1.72:8001` (LXC 124's Datasette) and writes static HTML to `/opt/sbdb-frontend/public/`, which nginx serves.

## Editing flow

1. Edit a file in `src/pages/` or `src/templates/` locally
2. Commit and push to this repo
3. Run `update-sbdb-frontend-source` via the broker
4. Broker pulls latest, runs `npm run build`, restarts nginx
5. Change is live in ~15 seconds
