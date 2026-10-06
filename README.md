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
