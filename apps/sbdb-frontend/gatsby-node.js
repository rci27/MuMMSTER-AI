const fetch = require("node-fetch")

const DATASETTE = process.env.DATASETTE_URL || "http://192.168.1.72:8001"

async function dsQuery(sql) {
  const PAGE = 1000
  const allRows = []
  let offset = 0
  while (true) {
    const paged = `SELECT * FROM (${sql}) _q LIMIT ${PAGE} OFFSET ${offset}`
    const url = `${DATASETTE}/datasette.json?sql=${encodeURIComponent(paged)}&_shape=array`
    const res = await fetch(url)
    if (!res.ok) throw new Error(`Datasette query failed: ${res.status}`)
    const rows = await res.json()
    allRows.push(...rows)
    if (rows.length < PAGE) break
    offset += PAGE
  }
  return allRows
}

function slug(str) {
  return str.replace(/\*/g, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
}

exports.sourceNodes = async ({ actions, createNodeId, createContentDigest }) => {
  const { createNode } = actions

  console.log("[sbdb] Fetching main_results...")
  const results = await dsQuery(
    `SELECT Year, Place, "Band", "Total Points" AS total_points,
     "Theme Title" AS theme_title, Captain,
     "Captain Place" AS captain_place,
     "Music Playing" AS music_playing,
     "General Effect - Music" AS ge_music,
     "Visual Performance" AS visual_performance,
     "General Effect - Visual" AS ge_visual,
     "Order" AS march_order, "Number of Bands" AS num_bands,
     YouTube, Note, "Point Sheet" AS point_sheet
     FROM sbdb_main_results ORDER BY Year DESC, Place ASC`
  )
  for (const row of results) {
    createNode({
      ...row,
      id: createNodeId(`result-${row.Year}-${row.Band}`),
      internal: { type: "SbdbResult", contentDigest: createContentDigest(row) },
    })
  }
  console.log(`[sbdb] ${results.length} result rows`)

  console.log("[sbdb] Fetching parade_info...")
  const parade = await dsQuery(
    `SELECT Year,
     "Parade Date (String Bands)" AS Date,
     "Weather Parade Day Conditions 12 Noon according to Weather Underground and Philadelphia Inquirer" AS Weather,
     "Weather Parade Day High Temperature Degrees Farenheit" AS Temperature,
     "Weather Parade Day MAXIMUM Winds MPH" AS Wind,
     "Mayor City of Philadelphia (Sitting Mayor on 1 Jan)" AS Mayor,
     "Media Coverage" AS TV_Station,
     "Parade Route (Official) Start, Judges Stand, Finish" AS Route,
     "Sponsor" AS Sponsors
     FROM sbdb_parade_info ORDER BY Year DESC`
  )
  for (const row of parade) {
    createNode({
      ...row,
      id: createNodeId(`parade-${row.Year}`),
      internal: { type: "SbdbParade", contentDigest: createContentDigest(row) },
    })
  }
  console.log(`[sbdb] ${parade.length} parade rows`)

  console.log("[sbdb] Fetching award tables...")

  const custards = await dsQuery(
    `SELECT Year, Band, "Theme Title" AS theme_title, Captain,
     "Total Points" AS total_points, YouTube
     FROM sbdb_custards_last_stand ORDER BY Year DESC`
  )
  for (const row of custards) {
    createNode({
      ...row,
      id: createNodeId(`custards-${row.Year}`),
      internal: { type: "SbdbCustards", contentDigest: createContentDigest(row) },
    })
  }

  const viewers = await dsQuery(
    `SELECT Year, Band, "Theme Title" AS theme_title, Captain,
     "Total Points" AS total_points, YouTube
     FROM sbdb_viewers_choice ORDER BY Year DESC`
  )
  for (const row of viewers) {
    createNode({
      ...row,
      id: createNodeId(`viewers-${row.Year}`),
      internal: { type: "SbdbViewers", contentDigest: createContentDigest(row) },
    })
  }

  const lifetime = await dsQuery(
    `SELECT Year, Name FROM sbdb_lifetime_achievement ORDER BY Year DESC`
  )
  for (const row of lifetime) {
    createNode({
      ...row,
      id: createNodeId(`lifetime-${row.Year}-${row.Name}`),
      internal: { type: "SbdbLifetime", contentDigest: createContentDigest(row) },
    })
  }

  const hof = await dsQuery(
    `SELECT Year, "Hall of Fame Inductee" AS inductees,
     "Old Timers Hall of Fame Inductee" AS old_timers
     FROM sbdb_hall_of_fame ORDER BY Year DESC`
  )
  for (const row of hof) {
    createNode({
      ...row,
      id: createNodeId(`hof-${row.Year}`),
      internal: { type: "SbdbHof", contentDigest: createContentDigest(row) },
    })
  }

  const officer = await dsQuery(
    `SELECT Year, Name FROM sbdb_officer_of_the_year ORDER BY Year DESC`
  )
  for (const row of officer) {
    createNode({
      ...row,
      id: createNodeId(`officer-${row.Year}-${row.Name}`),
      internal: { type: "SbdbOfficer", contentDigest: createContentDigest(row) },
    })
  }

  const presidents = await dsQuery(
    `SELECT Year, Name FROM sbdb_presidents_award ORDER BY Year DESC`
  )
  for (const row of presidents) {
    createNode({
      ...row,
      id: createNodeId(`presidents-${row.Year}-${row.Name}`),
      internal: { type: "SbdbPresidents", contentDigest: createContentDigest(row) },
    })
  }

  const distinction = await dsQuery(
    `SELECT Year, Name FROM sbdb_award_of_distinction ORDER BY Year DESC`
  )
  for (const row of distinction) {
    createNode({
      ...row,
      id: createNodeId(`distinction-${row.Year}-${row.Name}`),
      internal: { type: "SbdbDistinction", contentDigest: createContentDigest(row) },
    })
  }

  console.log(`[sbdb] Award tables loaded`)
}

exports.createPages = async ({ actions }) => {
  const { createPage } = actions
  const bandTemplate = require.resolve("./src/templates/band.js")
  const captainTemplate = require.resolve("./src/templates/captain.js")

  const allResults = await dsQuery(
    `SELECT Year, Place, Band,
     "Total Points" AS total_points, "Theme Title" AS theme_title,
     "Music Playing" AS music_playing, "General Effect - Music" AS ge_music,
     "Visual Performance" AS visual_performance, "General Effect - Visual" AS ge_visual,
     Captain, "Order" AS march_order, "Number of Bands" AS num_bands, YouTube
     FROM sbdb_main_results ORDER BY Year DESC`
  )

  const bands = {}
  for (const row of allResults) {
    if (!bands[row.Band]) bands[row.Band] = []
    bands[row.Band].push(row)
  }

  const bandsBySlug = {}
  for (const [band, history] of Object.entries(bands)) {
    const bandSlugStr = slug(band)
    if (!bandsBySlug[bandSlugStr]) {
      bandsBySlug[bandSlugStr] = {
        band: band.replace(/\*/g, "").trim(),
        slug: bandSlugStr,
        history: [],
        wins: 0,
        best: null,
      }
    }
    bandsBySlug[bandSlugStr].history.push(...history)
  }

  for (const [bandSlugStr, bandData] of Object.entries(bandsBySlug)) {
    bandData.wins = bandData.history.filter(r => String(r.Place) === "1").length
    const places = bandData.history.map(r => parseInt(r.Place)).filter(Boolean)
    bandData.best = places.length ? Math.min(...places) : null
    createPage({
      path: `/bands/${bandSlugStr}`,
      component: bandTemplate,
      context: {
        band: bandData.band,
        slug: bandSlugStr,
        history: bandData.history,
        wins: bandData.wins,
        best: bandData.best,
      },
    })
  }
  console.log(`[sbdb] Created ${Object.keys(bandsBySlug).length} band pages`)

  const captainsBySlug = {}
  for (const row of allResults) {
    if (!row.Captain || !row.Captain.trim()) continue
    const captainName = row.Captain.replace(/\*/g, "").trim()
    if (!captainName) continue
    const captainSlugStr = slug(captainName)
    if (!captainsBySlug[captainSlugStr]) {
      captainsBySlug[captainSlugStr] = {
        captain: captainName,
        slug: captainSlugStr,
        history: [],
      }
    }
    captainsBySlug[captainSlugStr].history.push(row)
  }

  for (const [captainSlugStr, captainData] of Object.entries(captainsBySlug)) {
    const wins = captainData.history.filter(r => String(r.Place) === "1").length
    const places = captainData.history.map(r => parseInt(r.Place)).filter(Boolean)
    const best = places.length ? Math.min(...places) : null
    createPage({
      path: `/captains/${captainSlugStr}`,
      component: captainTemplate,
      context: { captain: captainData.captain, slug: captainSlugStr, history: captainData.history, wins, best },
    })
  }
  console.log(`[sbdb] Created ${Object.keys(captainsBySlug).length} captain pages`)
}
