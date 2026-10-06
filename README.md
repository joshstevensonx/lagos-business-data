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
| 4 | `sources/gmaps_browser.py`: render wait, concurrent contexts, backoff, CAPTCHA abort, `--max-searches`/`--max-runtime`, wide-viewport sweeps, `--top-ups`, splitting at the 120-result feed cap | **Done**, live |
| 5 | `sources/directories.py`: Finelib (area → category tree) and BusinessList (all-Lagos list with coordinates), robots.txt, ≤1 req/s per domain, fixture tests | **Done**, live. Cybo returns 403 to automated requests, VConnect timed out, NGEX has no area pages; all three are logged as skipped |
| 6 | `enrichers/site_contacts.py`: emails, WhatsApp, socials, extra phones and delivery signals from each business's own site; robots.txt, cache, 2MB cap, per-host serial | **Done** |
| 7 | `enrichers/place_pages.py`: Google place page for delivery signals, ordering link, phone, website and full address | **Done**, live |
| 8 | `enrichers/places_api.py`: free tier only, **off by default**, explicit field masks, persisted usage counter capped at 80% | **Done**, not run (needs Josh's key and billing opt-in) |
| 9 | `derive-centroids`, `--import-csv`, `--dedupe-report` | **Done** |

Sources and enrichers that are enabled in config but not built yet are **skipped with a logged notice**, and the workbook README tab says so.

### Run it

A full run, as it was done for the October 2026 deliverables:
```bash
export LAGOSDATA_CHROMIUM=/opt/pw-browsers/chromium   # only if Playwright's own browser build is missing
lagosdata discover --config config/magazine.yaml --run-id 2026-10-06-magazine           # Maps + OSM
lagosdata discover --config config/magazine.yaml --run-id 2026-10-06-magazine --source directories
lagosdata run --config config/magazine.yaml --run-id 2026-10-06-magazine --stages geo,classify,dedupe,enrich,score,report,verify
# delivery: discover first, derive the area centres from the results, then build
lagosdata discover --config config/delivery.yaml --run-id 2026-10-06-delivery
lagosdata run --config config/delivery.yaml --run-id 2026-10-06-delivery --stages geo
lagosdata derive-centroids --config config/delivery.yaml --run-id 2026-10-06-delivery --write
lagosdata run --config config/delivery.yaml --run-id 2026-10-06-delivery --stages geo,classify,dedupe,enrich,score,report,verify
```

```bash
pip install -e ".[dev,browser]"    # browser = Playwright, for Google Maps and --osm-via-browser
pytest                              # the verify tests need LibreOffice; the gmaps tests need Playwright
# if Playwright's bundled browser build is missing, point it at an installed Chromium:
export LAGOSDATA_CHROMIUM=/path/to/chromium
lagosdata run --config config/smoke-2area.yaml        # small live check: 2 areas, 6 terms
lagosdata run --config config/magazine.yaml            # all stages, verify last; exit 1 if verify fails
lagosdata run --config config/magazine.yaml --stages report,verify --run-id <id>
lagosdata resume --run-id <id>
lagosdata report --run-id <id>
lagosdata verify --run-id <id>
lagosdata run --config config/magazine.yaml --import-csv walked.csv   # Josh's hand-collected records
lagosdata derive-centroids --config config/delivery.yaml --run-id <id> --write
```

Output goes to `out/<run-id>/`: `raw/*.jsonl` (untouched, append-only), `stages/*.json`, `master.json`, `state.sqlite`, `run.log`, `manifest.json`, the workbook, `verify_report.json` and `verify_sample.csv`.

### Deliberate deviations from SPEC, for review
- **Stage order is `discover → geo → classify → dedupe → enrich → score → report → verify`.** In SPEC §2.1, dedupe comes after score. Moving it earlier means enrichment budgets are spent once per business rather than once per duplicate, and `score.py`'s chain detection, which counts how often a name appears, isn't fooled by the same shop listed in two sources.
- **`Verification` is `Google-verified` only for records with Google provenance.** OSM records now also have coordinates, so the reference's "has lat ⇒ Google-verified" rule would overstate them. They show `Mapped location (OSM)` instead.
- **Workbook formulas find columns by header name, never by a typed letter.** Records outside every catchment, and records with no location, stay in `MASTER DATABASE`. They get their own rows in `AREA SUMMARY` and `GROUP x AREA` (so the row counts reconcile) and are excluded from the headline core and ring counts.
- **The magazine `MASTER DATABASE` gains columns *after* the delivered v3 layout:** WhatsApp, Email, Instagram, Facebook, Contact Channels and All Sources. The original columns don't move.
- **Delivery `TARGET LIST` gives every score component its own column** (SPEC §1.2). The reference had only three.
- **Delivery bands are pinned to 60/40/25 in config validation**, so they can't be retuned by a YAML edit (SPEC §6.4: "do not retune without asking").

### Findings from the first live runs (Oct 2026)
- **The Maps feed stops at 120 results.** Every busy term in the 2-area smoke run returned exactly 120. So a wide zoom-14 sweep silently loses everything past the first 120 (SPEC §3.3(c) assumed it doesn't). The fix is built in: a search that hits the cap is split into 4 quadrant searches one zoom level closer, recursively up to zoom 17. The splits are rebuilt from state, so they survive a resume, and they all count against `max_searches`.
- **Review counts appear on only some cards.** In the smoke run, 68% of in-catchment businesses had one; cards show "(26)" or "No reviews". Records without a count lose the review-based priority paths (magazine) and the order-volume proxy (delivery) until place-page enrichment fills them.
- **Name-only dedupe was fusing chain branches.** Two Nett Pharmacy branches, for example, have different Google place IDs. A name match no longer merges two records that both have place IDs and the IDs differ. Phone matches still merge (SPEC §6.3: the strongest signal).
- **Live 2-area smoke run** (`config/smoke-2area.yaml`, 6 terms, one zoom-15 viewport): 720 cards became 713 unique businesses, 314 of them inside Anthony and Maryland. 0% unclassified, `verify` passed every check.
