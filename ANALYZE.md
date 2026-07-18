# ANALYZE playbook — analysis step (run on **Opus**, in the main thread)

Input: one or more `<slug>.raw.json` from the gather step + the buyer criteria.
Output: a schema-valid `<slug>.data.json` (see `schema.md`).

You are doing the **judgement** work — turn raw facts into scored, written analysis.

## Steps
1. **Market overview**: write `headline`, `why_this_area` (if it's a widened/related
   search), and `buyer_fit_takeaways` (5–7 bullets). Fill `schools/taxes/safety/
   community/commute` from `facts`. Add `flushing_proximity` only if relevant.
2. **snapshot.stats**: choose 6–8 stat cards; **pre-format values** as strings
   ("$775K", "+3%", "1.4", "$521"). Keep labels short.
3. **at_a_glance**: one row per buyer attribute (budget, yard+shed, basement/gym,
   open kitchen, master, driveway, commute, schools, + style/Flushing if relevant).
   rating ∈ strong|moderate|weak with a one-line note. Be honest about weak spots.
4. **Per active listing** (from `active_raw` + its verbatim `description`):
   - Infer `features` (basement, yard, driveway, kitchen, etc.) from the description.
   - Estimate `est_annual_tax` = price × effective-rate (note it's an estimate);
     set `tax_confidence_pct` (~50–65).
   - Build `commute` per listing: nearest station, time to it (walk/drive from the
     address), and total door-to-door to Grand Central (station→GCT from
     `station_times` + access time + a small buffer).
   - Write `description / benefits / concerns / critiques` and a calibrated
     `fit_confidence_pct` (listings sort by this). Reward must-have + style matches;
     penalize misses honestly.
   - Carry through `url`, `image_url` (if gathered), `address`, `price`,
     beds/baths/sqft/year_built/style, `lot_sqft`.
   - Add `status_note` if the comp feed suggests it may have sold.
4b. **submarkets (ALWAYS include)**: break the area into its sub-neighborhoods
   (or, for a single town, its sections — e.g. Mineola: Mott / Williston-border /
   downtown). Rate each on commute, style/Tudor availability, yard, Asian community,
   and schools (strong|moderate|weak) with a short price range + one-line note. This
   renders as the Submarket Comparison table and is required in every report.
5. **price_history_annual**: 5-year annual median ask/sold. Anchor on the current
   snapshot + known trajectory; set a realistic `confidence_pct` (~65–75) and say
   pre-2025 are estimates. **Do NOT hand-build monthly** `price_history` — the build
   script computes it from `recent_sales`.
6. **recent_sales**: carry `sales_raw` straight through (build script computes
   `list_price_est` and the monthly chart).

## Folder convention (required)
Create a folder `<slug>/` for the evaluation and keep the `.data.json`, `.raw.json`
shards, and built files inside it. Nothing new goes loose in the project root.

## Then build (no hand-written HTML)
```
python3 _pipeline/build_report.py <slug>/<slug>.data.json
```
It validates, computes derived fields, creates `<slug>/`, and writes
`<slug>/<slug>.json` + `<slug>/<slug>.html`.

## Verify (cheap, scripted)
```
python3 _pipeline/verify_report.py <slug>
```
Confirms: embedded JSON == json file, render() doesn't throw, charts instantiate,
every listing has a url + commute, monthly medians match recent_sales.
Then present `<slug>.html` to the user.
