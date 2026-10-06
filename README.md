# Lagos Business Data Collector — handoff package

Give this whole folder to Claude Code.

- **`SPEC.md`** — the build specification. Start here. It describes one CLI tool with two
  config profiles (`magazine` census, `delivery` prospecting), built on free data sources only.
- **`reference/`** — 1,403 lines of working, already-debugged Python from the manual runs that
  produced the three delivered workbooks. Port these rather than rewriting them; the taxonomy,
  classifier rules, Nigerian phone normaliser, dedupe cascade, delivery scorer and both workbook
  builders are all known-correct and already approved by the client.

## Suggested first prompt for Claude Code

> Read SPEC.md and reference/. Build the tool it describes. Follow the implementation order in
> §10 — port the reference modules and get their tests green before writing any scraper. Do not
> add Apify or any paid service. Stop and show me the plan before you start on the Google Maps
> source.

## The one constraint to repeat

No Apify, no paid APIs, no scraping-as-a-service. Free collection only. The Google Places API
free tier is supported but **off by default** and must stay that way unless Josh opts in.

---

## Build status (SPEC §10)

| Step | What | Status |
|---|---|---|
| 1 | Scaffold, pydantic config (unknown keys are errors), SQLite run state, record schema, JSONL log; `tree`, `classify` and `taxonomy` ported verbatim; `score` verbatim plus a record adapter; `normalise` and `merge` from `merge_and_classify.py` | **Done**, tests green |
| 2 | `sources/osm.py` (`requests` transport, plus `--osm-via-browser`); never fatal | **Done**. Overpass is blocked from the cloud build container, so it is tested against a *synthetic* Overpass-shaped fixture |
| 3 | Both workbook builders ported, plus `verify` (LibreOffice recalc, Python recount of every DASHBOARD KPI, schema, <5% unclassified, dedupe sanity, cross-tab row counts, spot-check CSV) | **Done**, tests green |
| 4 | `sources/gmaps_browser.py` | **Not started.** Plan for review: [`docs/PLAN-gmaps-browser.md`](docs/PLAN-gmaps-browser.md) |
| 5–9 | directories, site_contacts, place_pages, places_api, `derive-centroids`, `--import-csv` | Not started. `--dedupe-report` is done |

Sources and enrichers that are enabled in config but not built yet are **skipped with a logged notice**, and the workbook README tab says so.

### Run it

```bash
pip install -e ".[dev]"            # add ",browser" for --osm-via-browser
pytest                              # 62 tests; the verify tests need LibreOffice (soffice)
lagosdata run --config config/magazine.yaml            # all stages, verify last; exit 1 if verify fails
lagosdata run --config config/magazine.yaml --stages report,verify --run-id <id>
lagosdata resume --run-id <id>
lagosdata report --run-id <id>
lagosdata verify --run-id <id>
```

Output goes to `out/<run-id>/`: `raw/*.jsonl` (untouched, append-only), `stages/*.json`, `master.json`, `state.sqlite`, `run.log`, `manifest.json`, the workbook, `verify_report.json` and `verify_sample.csv`.

### Deliberate deviations from SPEC, for review
- **Stage order is `discover → geo → classify → dedupe → enrich → score → report → verify`.** In SPEC §2.1, dedupe comes after score. Moving it earlier means enrichment budgets are spent once per business rather than once per duplicate, and `score.py`'s chain detection, which counts how often a name appears, isn't fooled by the same shop listed in two sources.
- **`Verification` is `Google-verified` only for records with Google provenance.** OSM records now also have coordinates, so the reference's "has lat ⇒ Google-verified" rule would overstate them. They show `Mapped location (OSM)` instead.
- **Workbook formulas find columns by header name, never by a typed letter.** Records outside every catchment, and records with no location, stay in `MASTER DATABASE`. They get their own rows in `AREA SUMMARY` and `GROUP x AREA` (so the row counts reconcile) and are excluded from the headline core and ring counts.
- **The magazine `MASTER DATABASE` gains columns *after* the delivered v3 layout:** WhatsApp, Email, Instagram, Facebook, Contact Channels and All Sources. The original columns don't move.
- **Delivery `TARGET LIST` gives every score component its own column** (SPEC §1.2). The reference had only three.
- **Delivery bands are pinned to 60/40/25 in config validation**, so they can't be retuned by a YAML edit (SPEC §6.4: "do not retune without asking").
