# Lagos Local Business Data Collector — Build Specification

**For:** Claude Code
**Client:** Nexora / Community Magazine (Anthony Village & Maryland, Lagos)
**Date:** 2026-10-06
**Status:** Specification for implementation. Nothing in `src/` exists yet; everything in `reference/` is working code lifted from the manual runs that produced the three delivered workbooks, and should be reused rather than rewritten.

---

## 0. Read this first

This document asks you to build **one configurable CLI tool** that performs two jobs that were previously done by hand across three sessions:

| Pipeline | Purpose | Previously delivered |
|---|---|---|
| `magazine` | Census of **every** business in a set of Lagos catchment areas, classified into a 29-group / 436-subcategory taxonomy, for an advertising-sales database. | `Anthony_Community_Media_MASTER_DATABASE_v3.xlsx` — 4,946 records, 7 areas |
| `delivery` | Targeted list of **restaurants, supermarkets and pharmacies** that plausibly do large deliveries, scored and ranked, for a delivery-service sales pitch. | `Lagos_Delivery_Prospects.xlsx` — 774 prospects, 5 areas |

They share ~80% of their machinery (discovery → geo-assignment → classification → enrichment → dedupe → workbook), so they are **one codebase with two config profiles**, not two programs.

### The one hard constraint

> **No paid tools. No Apify. No paid API calls. The tool must run at zero marginal cost.**

The previous runs used Apify's `compass/crawler-google-places` actor. **That is now out of scope.** Do not add an Apify client, do not add a paid-tier Google billing path, do not add SerpAPI / ScrapingBee / Bright Data / DataForSEO or similar. Where this spec refers to Apify it is only to explain *what data shape the downstream code expects*, because `reference/score.py` and `reference/merge_and_classify.py` were written against it.

A free Google Places API tier exists (see §3.1) and is **optional and off by default** — it requires the user to enable billing on a GCP project even to stay inside the free allowance, which is a decision for Josh, not a default. The tool must produce a complete result with the API disabled.

---

## 1. Outputs

Two XLSX workbooks, built with `openpyxl`, styled to match what has already been delivered (the client has seen these; keep them recognisable).

### 1.1 `magazine` workbook — 8 tabs

| Tab | Contents |
|---|---|
| `DASHBOARD` | KPI tiles (total records, contactable, by zone, by priority) as **live formulas** over `MASTER DATABASE`, not baked numbers |
| `README` | Method, date, source counts, what each column means, honest caveats |
| `MASTER DATABASE` | One row per business. Freeze panes at `A2`, autofilter, data-validation dropdowns on `Sales Status` and `Package` |
| `AREA SUMMARY` | Per-area counts, % contactable, top groups |
| `GROUP x AREA` | Matrix of 29 groups × N areas, `COUNTIFS` |
| `CATEGORY TREE` | All 436 subcategories with record counts — **including zero rows**, so gaps are visible as research targets |
| `RESEARCH MATRIX` | Subcategory × area cells flagged where coverage looks thin |
| `SOURCE LOG` | Every search executed: term, area, source, timestamp, raw count, kept count |

### 1.2 `delivery` workbook — 4 tabs

| Tab | Contents |
|---|---|
| `DASHBOARD` | Band counts (Hot / Warm / Cool / Cold), channel coverage (phone / website / email / Instagram), delivery-flag and catering counts |
| `README` | What the score is and — emphatically — what it is not |
| `TARGET LIST` | One row per prospect, sorted by score desc. Every score component in its own column |
| `SCORING METHOD` | The weights table, transcribed from `reference/score.py`, with the rationale per component |

### 1.3 Also emit

- `out/<run-id>/raw/*.jsonl` — every record as discovered, per source, untouched. Append-only.
- `out/<run-id>/master.json` — the merged, classified, scored record set (the workbook's input).
- `out/<run-id>/run.log` — structured JSONL log of every search and every HTTP/browser call.
- `out/<run-id>/manifest.json` — config snapshot, source counts, timings, tool versions.

Raw must be kept separate from derived so a classifier or scorer change can be re-run without re-collecting. **Re-collection is the expensive step; make it unnecessary.**

---

## 2. Architecture

```
lagos-data/
  pyproject.toml
  config/
    magazine.yaml          # 29-group census, 7 areas
    delivery.yaml          # 3-category targeted, 5 areas
    areas.yaml             # shared area registry (centroids + radii)
  src/lagosdata/
    cli.py                 # typer/argparse entrypoint
    config.py              # pydantic models, validation, defaults
    state.py               # resumable run state (sqlite)
    areas.py               # centroids, radii, point-in-area, centroid derivation
    tree.py                # <- reference/tree.py verbatim
    classify.py            # <- reference/classify.py verbatim
    taxonomy.py            # <- reference/taxonomy.py verbatim (legacy 18)
    score.py               # <- reference/score.py, adapted (see §6.4)
    normalise.py           # <- phone/name/address cleaners from reference/merge_and_classify.py
    merge.py               # <- dedupe from reference/merge_and_classify.py
    sources/
      base.py              # Source ABC
      osm.py               # Overpass API
      gmaps_browser.py     # Playwright on Google Maps
      directories.py       # Finelib, NGEX, Cybo, VConnect, BusinessList
      places_api.py        # OPTIONAL, free tier only, off by default
      site_contacts.py     # crawl a business's own website for email/socials
    stages/
      discover.py
      geo.py
      enrich.py
      scoreing.py
      dedupe.py
      report.py
      verify.py
    workbook/
      magazine.py          # <- reference/build_magazine_workbook.py
      delivery.py          # <- reference/build_delivery_workbook.py
      style.py             # shared fills/fonts/borders
  reference/               # the files shipped with this spec; read, then port
  tests/
```

### 2.1 Stages

Each stage reads the previous stage's artifact on disk and writes its own. Every stage is independently re-runnable.

```
discover → geo → classify → enrich → score → dedupe → report → verify
```

```bash
lagosdata run      --config config/magazine.yaml
lagosdata run      --config config/magazine.yaml --stages enrich,score,dedupe,report
lagosdata resume   --run-id 2026-10-07-magazine
lagosdata discover --config config/delivery.yaml --area "Lekki Phase 1" --term pharmacy
lagosdata report   --run-id 2026-10-07-magazine        # rebuild workbook only
lagosdata verify   --run-id 2026-10-07-magazine
```

### 2.2 Resumability is a requirement, not a nicety

The manual runs were interrupted repeatedly — quota exhaustion, browser timeouts, context limits. A 321-term × 7-area sweep is hours of wall clock. Therefore:

- **SQLite state table** `searches(source, term, area, status, raw_count, kept_count, started_at, finished_at, error)`. A search is attempted only if not `done`.
- Raw records append to JSONL immediately after each search returns. Never buffer a whole sweep in memory.
- `Ctrl-C` is a clean shutdown: finish the in-flight search, flush, exit 0.
- Re-running the same command is a no-op for completed work.
- `--force-term` / `--force-area` to redo specific cells.

---

## 3. Data sources — free tier strategy

Run them in this order. Later sources fill gaps left by earlier ones; the merge step cross-verifies.

### 3.1 Tier 0 (optional, off by default) — Google Places API free allowance

Google Places API (New) has **per-SKU monthly free call allowances**, not a shared pool:

| SKU | Free calls / month | Triggered by |
|---|---|---|
| Essentials | 10,000 | minimal field mask (id, name, formattedAddress, location) |
| Pro | 5,000 | adds displayName details, types, photos, viewport |
| Enterprise | 1,000 | adds rating, userRatingCount, regularOpeningHours, phone, website |

*(Confirmed October 2026. Treat as volatile — re-check before relying on it.)*

Critical implementation notes:

- **The field mask determines the SKU.** A single careless `*` mask bills every call at Enterprise and burns the 1,000 in one sweep. The mask must be explicit, per-call, and asserted in code.
- **Billing must be enabled on the GCP project even to use the free tier.** This is why it is off by default: Josh must opt in knowingly.
- Implement a **local call counter persisted across runs** (`~/.lagosdata/places_usage.json`, keyed by `YYYY-MM` and SKU). Refuse to exceed the configured ceiling — default the ceiling to 80% of the allowance so a miscount cannot cost money. Log remaining budget at every call.
- Gate behind `sources.places_api.enabled: false` and an env var `GOOGLE_PLACES_API_KEY`. **Never read a key from config YAML; never log it; never ask the user to paste it into a chat.** Env var or a gitignored `.env` only.
- If enabled, use it for the **Enterprise-tier fields on the highest-value records only** (top N by review count in the `delivery` pipeline), not for discovery. Discovery is cheap elsewhere; phone numbers are not.

### 3.2 Tier 1 — OpenStreetMap / Overpass API (free, unlimited, polite)

Endpoint: `https://overpass-api.de/api/interpreter` (fall back to `https://overpass.kumi.systems/api/interpreter`).

```
[out:json][timeout:60];
(
  node["shop"](6.52,3.33,6.60,3.41);
  way["shop"](6.52,3.33,6.60,3.41);
  node["amenity"~"restaurant|cafe|fast_food|pharmacy|bank|school|place_of_worship"](6.52,3.33,6.60,3.41);
  node["office"](6.52,3.33,6.60,3.41);
  node["healthcare"](6.52,3.33,6.60,3.41);
);
out center tags;
```

**Known limitation, measured:** OSM coverage in these Lagos areas is *thin*. The entire Maryland bounding box returned **38 POIs**. Do not expect OSM to carry the census — it is a cheap cross-verification layer and a source of `phone`, `website`, `opening_hours` tags for businesses found elsewhere. Budget it at <2% of final records.

**Known blocker:** Overpass was unreachable from both the cloud container and the device shell via the HTTPS proxy during the manual runs; it worked when `fetch()`-ed from inside a browser page context. Implement `osm.py` with a configurable transport: `requests` first, and a `--osm-via-browser` fallback that executes the query from a Playwright page. Handle the failure gracefully — never let an OSM timeout abort a run.

Map OSM tags → taxonomy by feeding `shop`/`amenity`/`office`/`healthcare` value plus `name` into `classify()` exactly as a Google category label would be.

Attribution: ODbL. The README tab must credit "© OpenStreetMap contributors" for OSM-sourced rows.

### 3.3 Tier 2 — Google Maps via Playwright (the workhorse)

This produced the bulk of the 4,946 records. It is a browser reading a public page; it is not an API call.

**Mechanics that were learned the hard way — implement all of them.**

URL form:
```
https://www.google.com/maps/search/<urlencoded term>/@<lat>,<lng>,<zoom>z
```

Result anchors are `a.hfpxzc` inside `div[role="feed"]`. Extract per card:

| Field | How |
|---|---|
| name | `a.hfpxzc[aria-label]` |
| category, address, phone | sibling text nodes in the card; positionally fragile — write defensively, expect `''` |
| rating, reviews | `span[role="img"][aria-label]` → `/([\d.]+) stars? ([\d,]+) review/` |
| lat, lng | from the anchor `href`: `/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/` |
| placeId | from the anchor `href`: `/!1s(0x[0-9a-f]+:0x[0-9a-f]+)/` |
| maps url | the anchor `href` itself |

**(a) Never scrape before the feed renders.** A naive "navigate then read" returned **1 result for `pharmacy` where 118 existed.** Required sequence:

```js
// poll until at least 3 anchors exist (max 22s)
while (Date.now() - t0 < 22000 && document.querySelectorAll('a.hfpxzc').length < 3)
    await sleep(500);
// then scroll the feed until the count is stable across 2 consecutive checks
let prev = count(), stale = 0;
while (Date.now() - t0 < 27000) {
    feed.scrollTop = feed.scrollHeight;
    await sleep(1300);
    const cur = count();
    if (cur === prev) { if (++stale >= 2) break; } else { stale = 0; prev = cur; }
}
```

The working extractor is reproduced in `reference/` context and in §A.1 below. Port it as a JS string injected via `page.evaluate`.

**(b) Concurrency: this is where standalone Playwright beats the manual approach.** In the manual runs the browser was a *shared, visible* browser where only the foreground tab rendered the Maps feed — 4 tabs and then 2 tabs both starved, forcing strictly sequential searching. **Standalone headless Playwright does not have this constraint**: separate `BrowserContext`s render independently. So:

- Default `concurrency: 3`, configurable, hard cap 6.
- One `BrowserContext` per worker, fresh context per N searches to shed state.
- Randomised 2–6s delay between searches per worker. Randomised viewport. A realistic UA.
- **Back off hard on any sign of rate limiting** (consent walls, CAPTCHA, empty feed on a term that previously worked): exponential backoff from 60s, and after 3 consecutive failures stop that worker and log it. **Never attempt to solve a CAPTCHA.** If CAPTCHAs appear, abort the source, write what you have, and tell the user plainly.
- Respect a `--max-searches` ceiling and a `--max-runtime` wall-clock ceiling.

**(c) The wide-viewport trick — ~7× efficiency, use it.** One search at `@<lat>,<lng>,14z` positioned between areas returns results spanning several adjacent areas at once. Assign each result to an area **afterwards, from its coordinates** (§4). This turned 7 areas × 321 terms into roughly 321 wide searches plus targeted top-ups, instead of 2,247.

Config: `sweeps: [{ center: [6.5600, 3.3700], zoom: 14, covers: [Anthony, Maryland, Ilupeju, Obanikoro, Palmgrove] }, ...]`
Then `top_ups:` for areas whose post-assignment counts fall below an expected floor.

**(d) ToS and conduct.** Google's terms discourage automated access to Maps. The tool is for a small local business database, runs at low volume, scrapes only publicly displayed listing data, solves no CAPTCHAs, bypasses no authentication and respects backoff. Put this in the README tab and in `run.log`. Make `rate_limit`, `concurrency` and `max_searches` prominent config so volume stays modest. Log a one-line notice at startup when the Google Maps source is enabled, stating that it reads public listing pages and that the user should keep volumes low. Do not add proxy rotation, user-agent farms, or CAPTCHA-solving integrations — if the tool needs those to work, the answer is to run it slower, not to evade.

### 3.4 Tier 3 — Nigerian business directories (free HTML)

These were the original seed for v1/v2 and remain good for businesses Google Maps misses (especially professional services, which often have a directory listing and no Maps pin).

| Site | Shape | Notes |
|---|---|---|
| `finelib.com` | `/.../<area>/<category>` paginated lists | Josh supplied two URLs originally; richest Nigerian coverage |
| `ngex.com` | business directory by state/category | often has email addresses |
| `cybo.com` | `/NG/lagos/...` | has phone + coordinates |
| `vconnect.com` | category/location search | heavy JS; may need Playwright rather than requests |
| `businesslist.com.ng` | category/city | plain HTML, easy |
| `nigeriagalleria.com`, `connectnigeria.com` | sparser, optional |

Implementation:

- **Honour `robots.txt`** for each domain via `urllib.robotparser` before any fetch. If a path is disallowed, skip it and log the skip — do not work around it. Record in the manifest which sites were skipped for this reason.
- One shared `requests.Session`, 1 req/sec per domain, descriptive User-Agent with a contact email from config.
- Parse with `selectolax` (fast) or `BeautifulSoup`. Each directory gets its own small parser module with a declared selector set at the top of the file, because these sites change their markup — keep the breakage surface one screen tall.
- **Each parser must have a recorded fixture test** (`tests/fixtures/<site>-<date>.html`) so a selector break is a failing test, not a silently empty run.
- If a parser yields 0 records for a page that fixture-tests say should yield many, raise — a silent zero is the worst failure mode here.
- Directory data is lower-trust: no coordinates, stale phones, duplicate listings. Tag `source` precisely (`"Finelib (Oct 2026)"`) so the merge can prefer Google data on conflict (§6.3).

### 3.5 Tier 4 — the business's own website (replaces Apify `scrapeContacts`)

For records with a `website`, fetch the homepage plus up to 3 of `/contact`, `/contact-us`, `/about`, `/order`, `/delivery`, and extract:

- emails — `mailto:` links first, then a regex over text; drop `noreply@`, `example.com`, image-filename false positives
- Instagram / Facebook / Twitter-X / LinkedIn / TikTok handles — from `href` patterns, normalised to a bare handle plus canonical URL
- additional phone numbers → through `clean_phone()` (§6.1)
- WhatsApp links (`wa.me/<number>`, `api.whatsapp.com/send?phone=`) — **high value for Nigerian SMB sales**, give this its own column
- delivery signals in text: `/\b(deliver(y|ies)?|dispatch|bulk order|corporate order|catering|wholesale|we deliver|free delivery)\b/i` → feeds `score.py` (§6.4)

Rules: `robots.txt` respected per host; 10s timeout; 2MB response cap; concurrency 5 with per-host serialisation; cache by URL so a re-run costs nothing; never POST, never submit a form, never follow off-domain links beyond depth 1.

This is the only enrichment path left now that Apify's `scrapeContacts` is out, and in the `delivery` pipeline it is what turns a "floor" score into a real one. In the delivered workbook only 72 of 774 records had an email — this stage is how that number improves.

### 3.6 Tier 5 — manual top-up hooks (no code, just affordances)

- `--import-csv <file>` merges a hand-collected CSV through the same normalise/classify/dedupe path. Josh walks these areas; he will have records no scraper finds.
- The `RESEARCH MATRIX` tab exists to tell him *where* to look.

---

## 4. Areas and geo-assignment

### 4.1 Derive centroids empirically — do not hardcode guesses

The single most expensive mistake in the manual runs: searching `"Maryland, Ikeja"` returned **996 places scattered across Ilupeju, Oshodi and Gbagada**, of which only **4–5** were actually within 1.3 km of Maryland. Google's geocoding of informal Lagos area names is unreliable.

The fix, which the tool must implement as a first-class command:

```bash
lagosdata derive-centroids --config config/magazine.yaml
```

For each area name, take every record whose Google-formatted address **explicitly contains that area name**, then take the **median** lat and median lng (median, not mean — it is robust to the outliers that caused the problem). Write the result to `config/areas.yaml` with a `derived_from: N records` note and the date. Flag any area where N < 15 as low-confidence and require human review.

Centroids derived this way for the seven magazine areas, which are **known-good and should ship as the defaults**:

```yaml
areas:
  "Anthony / Anthony Village": { lat: 6.55982, lng: 3.36915, radius_km: 1.30 }
  "Maryland / Mende":          { lat: 6.57229, lng: 3.36717, radius_km: 1.30 }
  "Ilupeju":                   { lat: 6.54548, lng: 3.35989, radius_km: 1.40 }
  "Gbagada":                   { lat: 6.55144, lng: 3.38653, radius_km: 1.60 }
  "Obanikoro":                 { lat: 6.54773, lng: 3.36824, radius_km: 1.00 }
  "Palmgrove":                 { lat: 6.53952, lng: 3.36767, radius_km: 1.00 }
  "Ojota":                     { lat: 6.58282, lng: 3.38447, radius_km: 1.40 }
```

Delivery-pipeline areas (Lekki Phase 1, Lekki-Epe corridor to Ajah, Victoria Island, Ikoyi, Yaba, Surulere) need centroids derived on first run — they were handled by name in the manual run. Note that the Lekki-Epe corridor is a **strip, not a disc**: support an optional `polygon:` or `corridor: {from: [lat,lng], to: [lat,lng], width_km: N}` geometry alongside `radius_km`, because a circle either misses Ajah or swallows the lagoon.

### 4.2 Assignment

```python
def nearest_area(lat, lng, areas):
    # local flat-earth approximation is fine at this scale
    best, bd = None, 1e9
    for name, a in areas.items():
        d = math.hypot((lat - a.lat) * 110.57,
                       (lng - a.lng) * 110.32 * math.cos(math.radians(a.lat)))
        if d < bd: bd, best = d, name
    return best, bd
```

- Within `radius_km` → assign.
- Outside every radius → `area = "Outside catchment"`, **keep the record**, exclude from headline counts. These are future expansion leads and the client paid for the search that found them.
- No coordinates (directory sources) → fall back to string-matching the area name in the address; if that fails, `area = "Unassigned"`.
- `zone` = `"Core catchment"` for the configured core areas, else `"Ring area"`.

---

## 5. Taxonomy and classification

Use `reference/tree.py` and `reference/classify.py` **as they are**. Together they are ~440 lines encoding Josh's 29-group / 436-subcategory structure and 321 deduplicated search terms, plus an ordered keyword rule list. Re-deriving them is wasted effort and will not match the workbook the client has already approved.

- `tree.TREE` — 29 groups → `{subs: [...], terms: [...]}`. Exports `ALL_TERMS` (321), `GROUPS` (29), `ALL_SUBS` (436).
- `classify.classify(label, name) -> (group, subcategory)` — ordered `RULES`, **first match wins**, so rule order is semantic. Lowercases `label + " " + name`, replaces `/` with space. Falls back to `("Other Local Services", "Unclassified (needs review)")`.
- `taxonomy.py` — the legacy 18-category normaliser. Keep it: the workbook has a `Legacy 18 Category` column the client's earlier material depends on.

**Guardrail that must be a test:** the catch-all bucket bloated to 242 records in the manual run and needed ~17 extra rules to get down to 113. Add `tests/test_classify.py` asserting that on a recorded sample of real labels, `"Unclassified (needs review)"` holds **< 5%** of records. Fail the build above that, and print the 20 most common unclassified `label` values so the fix is obvious.

Keep the `blob`-level pre-checks in `taxonomy.py` (`if "barb" in blob: return "Barbers"`) — they exist because Google labels barbershops inconsistently.

---

## 6. Normalisation, merge, scoring

### 6.1 Nigerian phone numbers — use the shipped function, do not rewrite it

`clean_phone()` in `reference/merge_and_classify.py` went through three corrections. Port it verbatim. The output is always `+234XXXXXXXXXX` or `''`.

Two bugs it now guards against, both of which reached a delivered workbook:

1. The capture group was `[789]\d` + 3 + 4 = **9 digits**. Nigerian mobile subscriber numbers are **10** after the `+234`. Fix was `[789]\d{2}`. A number one digit short looks plausible and is useless.
2. Garbage like `+23412454213789` passed an earlier looser version. The function now validates length and prefix per number type (mobile `7/8/9` + 10 digits; Lagos landline `1` + 8–9 digits).

```python
def clean_phone(p):
    if not p: return ''
    raw = str(p)
    for m in re.finditer(r'(?:\+?234|0)[\s\-]?([789]\d{2}[\s\-]?\d{3}[\s\-]?\d{4})', raw):
        d = re.sub(r'\D', '', m.group(1))
        if len(d) == 10: return '+234' + d
    d = re.sub(r'\D', '', raw)
    if d.startswith('0') and len(d) >= 11 and d[1] in '789': return '+234' + d[1:11]
    if d.startswith('234'):
        rest = d[3:]
        if rest[:1] in ('7','8','9') and len(rest) >= 10: return '+234' + rest[:10]
        if rest[:1] == '1' and 8 <= len(rest) <= 9:       return '+234' + rest
    if d.startswith('01') and 9 <= len(d) <= 10: return '+234' + d[1:]
    return ''
```

`tests/test_phone.py` must cover: `0803 123 4567`, `+234 803 123 4567`, `234 1 234 5678`, `08031234567`, `01 2345678`, `+23412454213789` (→ `''`), `0803-123-456` (9 digits → `''`), `0803 123 4567 / 0805 987 6543` (first valid wins), `WhatsApp: 0803 123 4567`.

Also port `norm_name()` (strips `ltd|limited|nig|nigeria|plc|enterprises|ventures|international|global|...`) and `norm_addr()` (strips street-type words and unit prefixes).

### 6.2 Non-business POI filter

Google Maps returns bus stops, roundabouts and bare street names as results. `"Iyana Oworo (Car Wash) Bus Stop"` was counted as a business. Port `NOT_A_BUSINESS` and `is_poi()` from `reference/merge_and_classify.py`: drop when the name matches `bus ?stop|busstop|bus-stop|roundabout|flyover|under ?bridge` **and** `label` is empty, or when `label` is empty and the name ends in `street|crescent|close|avenue|road`. The `label`-empty condition matters: "Bus Stop Pharmacy" with `label="Pharmacy"` is a real business.

Log every drop to `run.log` with its reason, and report the count. Do not delete silently.

### 6.3 Deduplication

Port the key cascade exactly. Order is load-bearing — phone is the strongest identity signal, name+address next, name alone last and most likely to over-merge.

```
1. ('p',  phone)                               # if phone present
2. ('na', norm_name + '|' + norm_addr[:40])
3. ('n',  norm_name)
```

On a hit: **fill empty fields from the duplicate** (`phone, website, maps, rating, reviews, lat, lng, addr, street, label, legacy18`), and if the sources differ set `source = "Multiple sources (cross-verified)"`. That flag is a selling point in the workbook — a cross-verified record is worth more to a salesperson.

Add, beyond the manual version:

- **`placeId` as key 0** when present. It is Google's own identity and beats everything.
- **Conflict preference**, which the manual run did not need but the multi-source tool does: on conflicting non-empty values, prefer by source trust — `Places API > Google Maps > OSM > directory > manual CSV` — and record the loser in a `conflicts` list on the record. Surface conflict counts in the README tab.
- A `--dedupe-report` flag writing every merge decision to CSV, so an over-merge is auditable. Name-only merging will occasionally fuse two genuine branches of one chain; it is better to see that than to wonder.

### 6.4 Delivery scoring — one bug to understand before you touch it

Port `reference/score.py`. The weights (Google Delivery flag 25, Catering 15, review-volume proxy up to 25, Chain 10, Category weight 10/6/4, Website 8, Online ordering 7, No-contact 5, Takeout 5, Delivery hours 5, Rating 4.0+ 5; bands Hot ≥60 / Warm 40–59 / Cool 25–39 / Cold <25) are the client's approved scheme — do not retune them without asking.

**The bug worth knowing about.** Apify returned the structured attributes nested:

```json
{"additionalInfo": {"Service options": [{"Delivery": true}, {"Takeout": true}]}}
```

so a dot-path lookup for `additionalInfo.Service options.Delivery` silently returned nothing and **every delivery signal scored zero across the whole dataset**. It was found only by eyeballing a raw record. `_flag()` now handles both the flattened and the nested shape and must keep doing so.

**What changes now that Apify is gone.** Those `additionalInfo` attributes came from Apify's place-detail scrape. The free sources supply them differently:

| Signal | Free source |
|---|---|
| Delivery / Takeout / No-contact | Google Maps place page — the attribute chips under the title. Requires a **second Playwright visit to the place page**, not just the search feed. Make this a separate, budgeted `enrich` step: `enrich.max_place_visits: 400`, highest review counts first. |
| Catering | same chips, plus the website-text regex from §3.5 |
| Delivery hours | place page "Delivery" hours section |
| Online ordering | presence of an "Order online" button on the place page, or a `/order` route on the business's own site |
| Reviews / rating | already in the search feed |
| Website | search feed |
| Chain | name frequency within the dataset + `CHAIN_HINTS` list in `score.py` |

So: keep `_flag()`'s dual-shape handling, and have the Playwright place-page scraper emit the **nested** shape, so the existing code path and its test stay exercised.

**Score basis honesty — keep this.** 542 of 774 delivered prospects had a "full basis"; the rest were scored without enrichment. The workbook carries a `Score basis` column (`Full` / `Floor — not enriched`) and the README explains that an unenriched score is a **floor, not a verdict**. This matters commercially: Josh will cold-call from this list, and a 30 that is really a 70 is a missed sale, while a 70 that is really a 30 is a wasted call. Do not drop the column, and never present a floor score as a measurement.

---

## 7. Record schema

One canonical dict/dataclass through every stage. JSON on disk, `null` never — use `''` for absent strings so the workbook writes blanks rather than `None`.

```python
@dataclass
class Business:
    # identity
    name: str
    place_id: str = ''
    # location
    area: str = ''                  # assigned catchment, or 'Outside catchment' / 'Unassigned'
    zone: str = ''                  # 'Core catchment' | 'Ring area'
    street: str = ''
    addr: str = ''
    lat: float | str = ''
    lng: float | str = ''
    # classification
    group: str = ''                 # 1 of 29
    sub: str = ''                   # 1 of 436
    legacy18: str = ''              # legacy 18-category column
    label: str = ''                 # raw source category string, kept for re-classification
    # contact
    phone: str = ''                 # +234XXXXXXXXXX
    phones_all: str = ''            # '; '-joined
    whatsapp: str = ''
    website: str = ''
    email: str = ''
    instagram: str = ''
    facebook: str = ''
    twitter: str = ''
    linkedin: str = ''
    tiktok: str = ''
    contact_channels: int = 0
    # signals
    rating: float | str = ''
    reviews: int | str = ''
    additional_info: dict = field(default_factory=dict)   # NESTED shape, see §6.4
    delivery_text_signals: list = field(default_factory=list)
    # magazine pipeline
    priority: str = ''              # 'A - High commercial relevance' ... 'D - Listing only'
    package: str = ''               # Premium | Standard | Listing
    contactable: str = ''           # Yes | No
    verification: str = ''          # 'Google-verified' | 'Directory listing only'
    sales_status: str = 'Not Contacted'
    notes: str = ''
    # delivery pipeline
    score: float | str = ''
    band: str = ''
    score_components: dict = field(default_factory=dict)
    score_basis: str = ''           # 'Full' | 'Floor - not enriched'
    delivery_category: str = ''     # Restaurant / Food | Supermarket / Grocery | Pharmacy | Other
    # provenance
    source: str = ''
    sources_all: list = field(default_factory=list)
    maps: str = ''
    added: str = ''                 # ISO date
    conflicts: list = field(default_factory=list)
```

---

## 8. Config

`config/magazine.yaml`:

```yaml
pipeline: magazine
run_id_prefix: magazine
areas: [Anthony / Anthony Village, Maryland / Mende, Ilupeju, Gbagada, Obanikoro, Palmgrove, Ojota]
core_areas: [Anthony / Anthony Village, Maryland / Mende]

taxonomy:
  mode: full_tree          # all 29 groups, 321 terms
  terms: null              # or an explicit subset

sources:
  places_api:   { enabled: false, monthly_ceiling_pct: 80, skus: [essentials] }
  osm:          { enabled: true, via_browser: false, bbox_pad_km: 2.0 }
  gmaps_browser:
    enabled: true
    concurrency: 3
    zoom: 14
    sweeps:
      - { center: [6.5600, 3.3700], zoom: 14 }
      - { center: [6.5750, 3.3800], zoom: 14 }
    delay_seconds: [2, 6]
    max_searches: 400
    max_runtime_minutes: 240
  directories:
    enabled: true
    sites: [finelib, ngex, cybo, businesslist]
    rate_per_second: 1.0
    contact_email: "ops@nexora.example"     # sent as User-Agent contact
  site_contacts: { enabled: true, max_sites: 1500, concurrency: 5 }

enrich:
  place_pages: { enabled: false }           # magazine does not need attribute chips

output:
  dir: out/
  workbook: Anthony_Community_Media_MASTER_DATABASE_v4.xlsx
```

`config/delivery.yaml`:

```yaml
pipeline: delivery
run_id_prefix: delivery
areas: [Lekki Phase 1, Lekki-Epe Corridor to Ajah, Victoria Island, Ikoyi, Yaba, Surulere]
core_areas: []

taxonomy:
  mode: subset
  terms: [restaurant, fast food, supermarket, grocery store, pharmacy, chemist,
          bakery, catering, mini mart, provision store, hypermarket, food store]

delivery_scoring:
  enabled: true
  bands: { hot: 60, warm: 40, cool: 25 }
  keep_all: true            # score everything, keep every record

sources:
  gmaps_browser: { enabled: true, concurrency: 3, max_searches: 250 }
  osm:           { enabled: true }
  directories:   { enabled: true, sites: [finelib, cybo] }
  site_contacts: { enabled: true, max_sites: 800 }

enrich:
  place_pages: { enabled: true, max_place_visits: 500, order_by: reviews_desc }

output:
  dir: out/
  workbook: Lagos_Delivery_Prospects_v2.xlsx
```

Validate with pydantic. Unknown keys are an error, not a warning — a typo'd `concurency` that silently defaults is a four-hour mistake.

---

## 9. Verification stage — non-negotiable

Every delivered workbook in the manual runs had at least one bug caught only by a deliberate cross-check. One was a DASHBOARD KPI pointing at column `L` ("Has Website") where it should have been `M` ("Has Phone") — it read **0** against a true value of **631**. Formula references break silently when columns move; only an independent recount catches it.

`lagosdata verify --run-id <id>` must:

1. **Recount every DASHBOARD KPI in Python, directly from `master.json`, and assert equality with the workbook formula's computed value.** Fail loudly on mismatch and print both numbers plus the formula text.
2. Run the xlsx-skill `recalc.py` (LibreOffice headless) and assert `errors_found == 0`.
3. Assert schema: no `None` in string columns; every `phone` matches `^\+234\d{10}$` or is `''`; every `group` ∈ `GROUPS`; every `(group, sub)` ∈ the tree; every `area` ∈ configured areas ∪ `{Outside catchment, Unassigned}`.
4. Assert `< 5%` unclassified (§5).
5. Assert dedupe sanity: no two kept records share a non-empty `phone`; no two share a non-empty `place_id`.
6. Assert row counts match across `MASTER DATABASE`, `AREA SUMMARY` totals and `GROUP x AREA` totals.
7. Spot-check 10 random records against their `maps` URL — write them to `verify_sample.csv` for human eyeballing. Do not claim verification of what was not checked.
8. Print a summary table: records by source, by area, by group; contactability; enrichment coverage; score-basis split.

Exit non-zero on any failure. This command runs as the last stage of `run` by default.

---

## 10. Implementation order

1. Scaffold, config models, `state.py`, record dataclass, logging. Port `tree.py`, `classify.py`, `taxonomy.py`, `normalise.py`, `merge.py`, `score.py` **unchanged** and get their tests green **before writing a single scraper**. This is the part that is already known-correct; lock it in.
2. `sources/osm.py` — smallest real source, exercises the whole pipeline end to end on ~38 records. Prove `discover → geo → classify → dedupe → report` works.
3. Workbook builders ported from `reference/` + `verify.py`. Now a bad record set is visible.
4. `sources/gmaps_browser.py` — the big one. Build it against a single term in a single area, confirm the render-wait logic, then add concurrency, then the wide-viewport sweeps.
5. `sources/directories.py` — one site at a time, each with a fixture test.
6. `sources/site_contacts.py`.
7. `enrich/place_pages.py` for the delivery attribute chips.
8. `sources/places_api.py` last, off by default, behind the usage counter.
9. `derive-centroids`, `--import-csv`, `--dedupe-report`.

Run the `magazine` config end to end against a two-area subset before attempting all seven.

---

## 11. Things that will go wrong, and what to do

| Symptom | Cause | Response |
|---|---|---|
| A term returns 1–3 results where dozens exist | Scraped before the feed rendered | The §3.3(a) poll-then-scroll sequence. Re-verify it first on any low count. |
| A whole area's results land in the wrong place | Google geocoded an informal area name badly | Never trust name geocoding. `derive-centroids`, then coordinate assignment. |
| Counts collapse mid-run; empty feeds | Rate limiting | Back off, reduce concurrency, accept a longer run. Never add CAPTCHA solving or proxy rotation. |
| A directory parser returns 0 | Markup changed | The fixture test fails and tells you which selector. Fix the selector block at the top of that module. |
| Delivery scores all suspiciously low | `additionalInfo` nesting, or `enrich.place_pages` disabled | §6.4. Check a raw record by hand before touching the weights. |
| Phone column has 9-digit or 14-digit values | A rewritten `clean_phone` | Use the shipped one. Run `tests/test_phone.py`. |
| DASHBOARD tile reads 0 | Formula points at the wrong column | `verify` catches it. Never hand over a workbook that has not passed `verify`. |
| Catch-all group is huge | Missing classifier rules | The <5% test fails and prints the top unclassified labels. Add rules in order. |
| Overpass unreachable | Proxy blocks it | `--osm-via-browser`, or skip OSM. Never fatal. |
| Run dies at hour 3 | Anything | `resume` must make this cost nothing. Test it by killing a run deliberately. |

---

## 12. Boundaries

- **No paid services.** No Apify, no paid Google tier, no scraping-as-a-service, no proxy providers.
- **No CAPTCHA solving, no authentication bypass, no scraping behind a login.** Public listing pages only.
- **`robots.txt` is honoured** for every directory and business site. Skips are logged, not routed around.
- **Secrets never in config files, logs, or chat.** `GOOGLE_PLACES_API_KEY` from env or a gitignored `.env` only. If a key is ever needed, it goes in the file — never pasted into a conversation.
- **Personal data:** these are business listings — business names, business phones, business addresses. Do not collect named individuals, personal emails or personal social accounts beyond a business's own published contact details. Nigeria's NDPA applies to the client's later use of this data; note in the README that the list is for B2B contact and that opt-outs must be honoured.
- **Honesty in the output.** Scores are ranking aids with a stated basis. Coverage gaps are shown as zero rows, not hidden. Unverified records say so. The client makes sales calls off this file; an overstated number costs him real time.

---

## Appendix A.1 — the working Google Maps extractor

Injected via `page.evaluate`. This is the version that produced the delivered data, after the render-timing fix.

```js
window.__go = async function (key) {
  const t0 = Date.now();
  const cnt = () => document.querySelectorAll('a.hfpxzc').length;
  // 1. wait for the feed to render at all
  while (Date.now() - t0 < 22000 && cnt() < 3) {
    await new Promise(s => setTimeout(s, 500));
  }
  // 2. scroll until the result count stops growing
  let prev = cnt(), stale = 0;
  while (Date.now() - t0 < 27000) {
    const feed = document.querySelector('div[role="feed"]');
    if (feed) feed.scrollTop = feed.scrollHeight;
    await new Promise(s => setTimeout(s, 1300));
    const cur = cnt();
    if (cur === prev) { if (++stale >= 2) break; } else { stale = 0; prev = cur; }
  }
  // 3. extract
  const out = [];
  for (const a of document.querySelectorAll('a.hfpxzc')) {
    const href = a.getAttribute('href') || '';
    const card = a.closest('div[jsaction]') || a.parentElement;
    const txt  = card ? [...card.querySelectorAll('span, div')]
                          .map(e => e.textContent.trim()).filter(Boolean) : [];
    const coord = href.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
    const pid   = href.match(/!1s(0x[0-9a-f]+:0x[0-9a-f]+)/);
    const stars = (card && card.querySelector('span[role="img"][aria-label]')
                   ? card.querySelector('span[role="img"][aria-label]').getAttribute('aria-label') : '')
                  .match(/([\d.]+)\s*stars?\s*([\d,]+)?/);
    out.push({
      name:    a.getAttribute('aria-label') || '',
      label:   txt[1] || '',
      addr:    txt[2] || '',
      phone:   (txt.find(t => /^\+?\d[\d\s\-()]{7,}$/.test(t)) || ''),
      rating:  stars ? parseFloat(stars[1]) : '',
      reviews: stars && stars[2] ? parseInt(stars[2].replace(/,/g, '')) : '',
      lat:     coord ? parseFloat(coord[1]) : '',
      lng:     coord ? parseFloat(coord[2]) : '',
      placeId: pid ? pid[1] : '',
      maps:    href,
    });
  }
  return out;
};
```

Port the field extraction to Python-side parsing where you can (`page.locator` + structured reads), keeping the JS only for the scroll/render loop — it is easier to test and less brittle than positional `txt[1]`/`txt[2]` indexing. The indices above are what worked in September 2026; treat them as a starting point, not a contract, and default every field to `''`.

## Appendix A.2 — what is in `reference/`

| File | Lines | Port as |
|---|---|---|
| `tree.py` | 79 | `src/lagosdata/tree.py`, verbatim |
| `classify.py` | 361 | `src/lagosdata/classify.py`, verbatim |
| `taxonomy.py` | 60 | `src/lagosdata/taxonomy.py`, verbatim |
| `score.py` | 114 | `src/lagosdata/score.py` — keep `_flag()` dual-shape handling |
| `merge_and_classify.py` | 158 | split into `normalise.py` (`clean_phone`, `norm_name`, `norm_addr`, `street_of`, `is_poi`) and `merge.py` (dedupe cascade, priority/package assignment) |
| `build_magazine_workbook.py` | 353 | `workbook/magazine.py` — Arial, NAVY `1F3864`, BLUE `2F5597`, live COUNTIFS, freeze panes, autofilter, validation dropdowns |
| `build_delivery_workbook.py` | 278 | `workbook/delivery.py` |

1,403 lines of already-debugged logic. The scrapers are the new work; this part is not.
