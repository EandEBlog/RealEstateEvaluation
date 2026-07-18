# GATHER playbook — data-gathering agent (run on **Sonnet**)

Goal: produce a **raw facts file** `<slug>.raw.json` for an area. No analysis,
no prose ratings — just verified listings, sales, and market facts. Opus turns
this into the final `<slug>.data.json` later.

## Inputs you'll be given
- Area(s) + ZIPs, property type, budget, must-haves, style preference.

## Tools
- `mcp__workspace__web_fetch` for listing pages, and `WebSearch` for both finding
  listings and gathering market-overview facts (schools, taxes, safety, commute).
- If a page exceeds the token cap, the result is saved to a file — `Grep` it
  (price/`Beds`/`Sq Ft`/`Built`/style/`basement` lines) and `Grep` the
  `property/...-ny/<id>/ "<address>` lines to map address↔URL by line proximity.

## Cast a WIDE net — search ALL available listing sites
Do NOT limit yourself to one site. Run a broad, extensive search and cross-reference
across every listing source you can access, so no in-budget match is missed:
- **Aggregators / portals:** Homes.com, Zillow, Redfin, Realtor.com, Trulia,
  StreetEasy, PropertyShark, Movoto, Rocket Homes, Homesnap.
- **Brokerages:** Compass, Douglas Elliman, Corcoran, Keller Williams, RE/MAX,
  Coldwell Banker, Berkshire Hathaway, Sotheby's, and strong local/independent
  brokers for the target area.
- **Also try:** county/MLS public search, FSBO sites, auction/foreclosure listings,
  and neighborhood-specific real-estate blogs/agent sold lists for comps.
- Use `WebSearch` with queries like `"<area> <style> houses for sale <budget>"`,
  `"<area> sold homes <year>"`, `site:zillow.com <area> ...`, etc., then fetch the
  most promising results.
- **De-dupe across sites** (same home is listed on many) by address; keep the source
  with the richest description + a working `url`.
- **Reliability note:** Homes.com tends to give the cleanest structured output via
  `web_fetch`; some sites are JavaScript-rendered and `web_fetch` may return a thin
  shell — if so, try another site for the same listing rather than guessing. **Never
  bypass a blocked/failed fetch with curl/wget/other HTTP methods** — just use a
  different accessible source. Breadth of sources matters more than any single site.

## Homes.com URL patterns (a reliable starting point — but also search the sites above)
- City sold:  `https://www.homes.com/<city>-ny/sold/`
- City for-sale (houses): `https://www.homes.com/<city>-ny/houses-for-sale/`
- Queens neighborhoods: `https://www.homes.com/queens-ny/<hood>-neighborhood/sold/`
- Use `--out-dir` city slugs seen in nav (e.g. `little-neck-ny`, `douglaston-ny`,
  `bayside-ny`, `east-meadow-ny`, `carle-place-ny`, `great-neck-ny`).

## What to collect
1. **Market snapshot** (from the sold-page footer "Home Price Trends" table):
   median sale price, median single-family, $/sqft, months of supply, DOM,
   active count, last-12mo sales, YoY change.
2. **Active listings** (target 8–12 best matches to must-haves + style): for each:
   address, price, beds, baths, sqft, year_built, style, lot_sqft (if shown),
   **url**, listing_agent, the raw listing description text (verbatim — Opus
   needs it to write benefits/concerns and infer basement/yard/kitchen), and
   **image_url** = the listing's `primaryphoto` image link if present in the page
   (e.g. `https://images.homes.com/listings/.../...primaryphoto.jpg`). It's right in
   the same listing block, so capturing it is ~free; omit if not shown.
   - Filter OUT condos/co-ops/units unless the buyer wants them (skip "Unit"/low $/sqft).
   - Keep within ~1.1× budget; flag any above budget.
3. **Recent sales** (15–30 detached comps): address, sold_price, vs_list_pct,
   sold_date, beds, baths, sqft, year_built, dom. Drop obvious data errors
   (e.g. "100,054% Above List", $1,300 sale).
4. **Facts for overview**: schools (district + Niche/GreatSchools), property-tax
   rate/context, safety summary, LIRR line + station→Grand Central times,
   community character, (if relevant) Flushing drive time / Asian groceries.

## Sharding across multiple agents (scale to the search)
For a multi-town search, run **one Sonnet agent per town/cluster in parallel**, plus
one "facts" agent. Each writes a shard `<slug>.<shard>.raw.json` (e.g.
`<slug>.bayside.raw.json`, `<slug>.greatneck.raw.json`, `<slug>.facts.raw.json`).
- Town agents fill only `active_raw` + `sales_raw` for their town.
- The **facts agent** fills `snapshot_raw`, `facts{}`, `station_times{}` (and may
  also gather one small/edge town's listings).
Then merge: `python3 _pipeline/merge_raw.py <slug>` → `<slug>.raw.json`
(de-dupes listings by url/address and sales by address+date).
Rule of thumb: ≤2 towns → 1 agent; 3–5 towns → 1 per town + 1 facts agent;
>5 → cluster adjacent towns. Each agent stays small and parallel.

## Output: `<slug>.raw.json` (single agent) or `<slug>.<shard>.raw.json` (sharded)
```json
{
  "snapshot_raw": { ... key:value market stats ... },
  "facts": { "schools": "...", "taxes": "...", "safety": "...",
             "commute": "...", "community": "...", "flushing": "..." },
  "active_raw": [ { "address","price","beds","baths","sqft","year_built","style",
                    "lot_sqft","url","listing_agent","description" }, ... ],
  "sales_raw":  [ { "address","sold_price","vs_list_pct","sold_date","beds",
                    "baths","sqft","year_built","dom" }, ... ],
  "station_times": { "<station>": "<min to Grand Central>", ... }
}
```
Rules: **every active listing must have a working `url`**. Quote descriptions
verbatim. Don't invent numbers — if a field isn't shown, omit it.
