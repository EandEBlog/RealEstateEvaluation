# Real Estate Evaluation — pipeline

Turn an area request into an interactive HTML report at minimal token cost.
The HTML/CSS/JS is fixed (one template); **only the data JSON changes per area**.

```
request ──▶ GATHER (Sonnet) ──▶ ANALYZE (Opus) ──▶ build_report.py ──▶ verify_report.py ──▶ present
            <slug>.raw.json      <slug>.data.json   <slug>.json+.html   PASS/FAIL
```

## Files
- `schema.md` — the `<slug>.data.json` contract (the only thing analysis produces).
- `build_report.py` — validates, auto-computes `list_price_est` + monthly
  `price_history`, and emits `<slug>.json` + `<slug>.html` from the universal template.
- `verify_report.py` — scripted QA (render doesn't throw, embedded==json, charts,
  links, commute, median consistency).
- `GATHER.md` — Sonnet data-gathering instructions → `<slug>.raw.json`.
- `ANALYZE.md` — Opus analysis instructions → `<slug>.data.json`.
- `example.data.json` — a tiny valid example (build it to see the format render).

## Run it (model routing)
1. **Gather (Sonnet subagents — fan out by town).** Spawn **multiple Sonnet agents
   in parallel**, one per town/cluster, plus one facts agent. Each writes a shard
   `<slug>.<shard>.raw.json`; bulky page text stays out of the Opus context.
   Scale the agent count to the search (≤2 towns → 1; 3–5 → 1/town + facts; >5 → cluster).
   ```
   # one call per town, in a single batch:
   Agent(subagent_type="general-purpose", model="sonnet",
         prompt="Follow _pipeline/GATHER.md for <TOWN> only. Write <slug>.<town>.raw.json.")
   # + a facts agent for snapshot_raw/facts/station_times
   ```
   Then merge: `python3 _pipeline/merge_raw.py <slug>`  →  `<slug>.raw.json`.
2. **Analyze (Opus, main thread).** Read `<slug>.raw.json`, follow `ANALYZE.md`,
   write `<slug>.data.json`. This is the judgement step — keep it on Opus.
3. **Build + verify (scripted — ~0 tokens of reasoning).**
   ```
   python3 _pipeline/build_report.py <slug>.data.json
   python3 _pipeline/verify_report.py <slug>
   ```
4. **Display (Sonnet).** If any bespoke template tweak is needed, do it on Sonnet;
   otherwise the script already produced the page. Present `<slug>.html`.

## Why this saves tokens
- No hand-written HTML per area (was ~1.5k lines/area) — the template lives once.
- No manual median math or list-price arithmetic — `build_report.py` does it.
- No manual node QA harness — `verify_report.py` does it.
- Bulky listing-page scraping happens in cheap Sonnet subagents, not Opus context.

## Conventions
- slug: `<area>-<type>-<YYYYqQ>` e.g. `bayside-house-2026Q2`.
- **Folder per evaluation (required):** every new evaluation prompt gets its OWN
  folder named after the slug. Put the `.data.json`, any `.raw.json` shards, and the
  generated `.json` + `.html` inside `<slug>/`. `build_report.py` auto-creates
  `<slug>/` and writes the outputs there, so just place `<slug>.data.json` in it
  (or alongside) and run the build. Nothing new should land loose in the project root.
- One HTML + one JSON per area/attribute-set (matches the project rule).
- Refresh quarterly: re-run gather → analyze → build for the same slug folder.
- **Property images (optional):** listings may include `image_url` (the Homes.com
  `primaryphoto`); the template renders a lazy-loaded thumbnail and hides it if the
  image fails to load. Capturing the URL during gather is ~free; back-filling old
  reports would require re-fetching, so only new reports get images by default.
