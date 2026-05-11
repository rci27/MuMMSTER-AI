# MuMMSTER-AI

**Mummers Ultimate Metrics Machine for Scoring, Trends, Evaluation & Reporting Analytics Interface**

A prototype add-on and a proposal to enhance the [String Band Database](https://mummers.github.io/stringbands/) (source: [mummers/stringbands](https://github.com/mummers/stringbands)).

---

## About this project

This is an experimental, in-progress prototype that proposes to extend the existing String Band Database with a natural-language query layer over decades of String Band Division scoring data, and a curation pipeline for ingesting and validating historical records that have not yet been digitized.

It is not a replacement for, nor a fork of, the String Band Database. It is an additive tool that depends on the years of community work that have already gone into the existing database. The goal is to put it in front of the maintainers of that project as a proposal: here is a way the database might be extended with a query interface, additional historical scoring data, and a structured curation process for the years that pre-date the current digital era.

---

## Acknowledgements

The String Band Database created and maintained by **TJ Ferry** ([@tjferr14](https://github.com/tjferr14)) and **Brian Hamburg** ([@bhamburg](https://github.com/bhamburg)) is the foundation that everything in this prototype rests on. Their effort over many years to gather, organize, and present this material in a useful and accessible way is without measure. Anything useful in this prototype is downstream of their work.

A special thanks to the following contributors to the String Band Database project, whose contributions of source material, expertise, and feedback have made the underlying dataset possible:

- Brian Maher
- John Gilbert
- Joe "Bagel" Strine
- Russ Coleman
- Joe Fink

---

## What this prototype contains

The MuMMSTER-AI prototype is organized into several components, each designed to complement rather than duplicate the String Band Database.

### Natural-language query interface

A FastAPI-based service that lets a user ask a plain-English question about String Band Division scoring data and returns a structured answer. The pipeline is: natural-language input → SQL generation → DuckDB validation → execution → plain-English interpretation → optional chart and follow-up suggestions. Each step is visible in a "thinking panel" so the user can audit how the answer was derived.

### Master dataset (2008-2026)

A 17-year, judge-level scoring dataset compiled from the official Mummers Parade String Band Division point sheets. This is more granular than the Year/Band/Theme/Score-level data in the String Band Database — it captures each judge's score in each scoring category (Music Playing, General Effect, Visual Performance, etc.) for both bands and captains, where the source PDFs include that detail.

The full audit trail describing how every value was transcribed and validated is included as a separate document.

### Curation pipeline (in development)

A separate tool for ingesting older years from scanned PDFs and other archival sources, including human review and correction before the data is merged into the master dataset. This is the planned mechanism for adding pre-2008 data without compromising the integrity of the existing record.

---

## Status

Active prototype. The core query interface and the 2008-2026 master dataset are working. Pre-2008 ingestion via the curation pipeline is in progress. Nothing in this repository is intended to replace or compete with the String Band Database — it is a sketch of one possible direction for enhancement, offered in the spirit of contribution to a community resource that has been built over many years by people who care about it.

---

## Contact

If you maintain the String Band Database or are involved with the Mummers community and would like to discuss this prototype, please open an issue on this repository.
