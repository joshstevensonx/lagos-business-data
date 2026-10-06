# Plan: `sources/gmaps_browser.py` (SPEC §10 step 4) — for review before building

Steps 1–3 of SPEC §10 are done (see the README's build status). This is the plan for step 4. **Nothing below has been built yet.**

## The blocker to decide first

`www.google.com` cannot be reached from the cloud container this was built in: the egress proxy refuses the connection, the same way it refuses Overpass. So the scraper **cannot be developed or verified against live Google Maps here.** There are two options:

1. **Build it against recorded fixtures here, then run it live on Josh's machine.** I write the parser against saved Maps feed HTML. Josh saves a fixture with one command (`lagosdata record-fixture --term pharmacy --area "Anthony / Anthony Village"`) and makes the first live run: a single term in a single area, to confirm the render wait. Recommended.
2. **Allow `google.com` in this environment's network policy**, then develop it live here. Note that the cloud egress IP is not Nigerian, so the results Google returns, and whether it shows a consent wall, may differ from a run made in Lagos.

## Build order (as SPEC §3.3 and §10 require)

### 4a. One term, one area, render wait proven
- Playwright async API, headless Chromium (`pip install "lagosdata[browser]"`, already an optional extra).
- URL: `https://www.google.com/maps/search/<urlencoded term>/@<lat>,<lng>,<zoom>z`.
- **Render wait in JS** (Appendix A.1, used exactly as written): poll until at least 3 `a.hfpxzc` anchors exist (22s max), then scroll `div[role="feed"]` until the count is the same for 2 checks in a row (27s cap).
- **Extraction in Python**, not by positional `txt[1]`/`txt[2]`, as Appendix A.1 recommends:
  - name from `a.hfpxzc[aria-label]`
  - lat/lng from `!3d…!4d…` in the href
  - placeId from `!1s0x…:0x…` in the href
  - rating and reviews from `span[role="img"][aria-label]`
  - category, address and phone read defensively from the card text, defaulting to `''`
- The reference sweep filter is kept: a label that looks like a rating (`^[\d.]+\(`) or an "address" starting with `₦` is blanked.
- The source string is `Google Maps (sweep, <Mon YYYY>)`.
- **Low-count alarm:** a term that previously returned more than 10 results and now returns fewer than 4 is logged as `suspect_render`, not accepted silently. This is the "1 pharmacy where 118 existed" failure.
- **Tests:** a parser test on a recorded fixture (`tests/fixtures/gmaps-feed-<date>.html`). It must find more than 0 cards and fail loudly when selectors break.

### 4b. Concurrency
- `concurrency` workers (default 3, hard cap 6, already enforced by config), one `BrowserContext` per worker, with a fresh context every 25 searches.
- Each worker waits a random 2–6s between searches (`delay_seconds`) and uses a viewport from a small realistic set. The user agent is Chromium's own, with no rotation.
- Workers send results back to the main thread. Only the main thread writes to SQLite and the JSONL files, so each search is still flushed the moment it finishes.
- `Source` gains an optional `search_many()` that `discover` uses when present. The resumability semantics stay the same.

### 4c. Backoff and stopping (no evasion)
- **CAPTCHA** (`/sorry/` URL or a reCAPTCHA frame): **abort the whole source immediately**, flush what we have, and print a plain message to the user. It is never solved or retried.
- **Consent wall, or an empty feed on a term that worked before:** exponential backoff from 60s. After 3 failures in a row, that worker stops and logs why.
- `--max-searches` and `--max-runtime` ceilings, both from config and both overridable on the CLI.
- A startup notice is printed when the source is enabled; the hook is already in `discover.py`.
- No proxy rotation, user-agent farm or CAPTCHA service, now or later.

### 4d. Wide-viewport sweeps
- The plan is every term × every `sweeps[]` centre at zoom 14. Areas are assigned afterwards from coordinates by the existing `geo` stage. That is roughly 321 × 2 searches instead of 321 × 7.
- **Top-ups:** after `geo`, any area whose count falls below a configured floor (`top_ups: {area: floor}`) gets targeted searches at its centroid at zoom 15. This runs as `lagosdata discover --top-ups`.

## What the first live run should be
```bash
lagosdata discover --config config/magazine.yaml --run-id gm-smoke --term pharmacy --area "sweep 6.56,3.37"
```
Expected: dozens of pharmacies, not 1–3. If it returns very few, check the render wait before anything else (SPEC §11).

## Open questions for Josh
1. Option 1 or option 2 above?
2. A consent wall from a non-Nigerian IP: should that count as a stop signal (my default, and the cautious reading of §3.3(b)), or is clicking "Reject all" acceptable? Clicking it only declines cookies; it doesn't bypass anything.
3. The aliases for the delivery areas in `config/areas.yaml` (e.g. Sangotedo, Osapa and Agungi for the Lekki–Ajah corridor) are my guesses at neighbourhood names. Are they right? They only matter until `derive-centroids` runs.
