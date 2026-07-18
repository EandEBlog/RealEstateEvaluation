# Data contract — `<area>.data.json`

This is the **only** file a run has to produce. `build_report.py` validates it,
auto-computes derived fields, and emits `<area>.json` + `<area>.html`.

Naming: `slug` = lowercase, hyphenated area id, e.g. `bayside-house-2026Q2`.
**Folder per evaluation:** create a folder `<slug>/` and keep the `.data.json`,
any `.raw.json` shards, and the built `.json`/`.html` inside it. `build_report.py`
creates `<slug>/` automatically and writes the outputs there.

```jsonc
{
  "meta": {
    "report_title": "string — H1 title",
    "area": "string — areas/ZIPs covered",
    "property_type": "string",
    "buyer_criteria": {
      "budget": "string e.g. 'Up to $1.65M ($1.5M + $150k)'",
      "use": "string",
      "must_have": ["string", ...],            // rendered as badges
      "style_preference": "string (optional)", // badge
      "nice_to_have": "string (optional)"
    },
    "data_as_of": "2026-Q2 (June 2026)",
    "next_update_due": "2026-Q3 (September 2026)",
    "history_window": "string (optional)",
    "why_this_area": "string (optional) — shown under headline",
    "sources": ["string", ...],
    "disclaimer": "string"
  },

  "market_overview": {
    "headline": "string — one bold sentence",
    "at_a_glance": [                            // compact attribute scorecard
      { "attribute": "string", "rating": "strong|moderate|weak", "note": "string" }
    ],
    "snapshot": {                              // GENERIC stat cards (values pre-formatted)
      "stats": [ { "label": "Median sale price", "value": "$775K" }, ... ],
      "note": "string (optional)"
    },
    "commute": { "station": "string", "to_grand_central": "string",
                 "to_penn": "string (optional)", "notes": "string (optional)" },
    "flushing_proximity": {                    // OPTIONAL card
      "drive_distance_miles": "string", "drive_time_min": "string",
      "asian_amenities": "string", "confidence_pct": 70 },
    "schools": { "district": "string", "enrollment_k12": 1234,  // null OK
                 "student_teacher_ratio": "string (optional)",
                 "ratings": "string", "note": "string (optional)" },
    "safety": { "summary": "string",
                "violent_crime_per_1000": null, "property_crime_per_1000": null },
    "taxes": { "context": "string", "estimated_effective_rate_pct": 1.8,
               "exemptions": "string", "appeal_note": "string (optional)" },
    "community": { "character": "string", "dog_and_garden_fit": "string" },
    "overall_assessment_confidence_pct": 85,
    "buyer_fit_takeaways": ["string", ...]
  },

  // submarkets — REQUIRED in every report. Break the area into its constituent
  // sub-neighborhoods (or, for a single town, into its sections) and rate each
  // against the buyer's axes. Renders as a comparison table.
  "submarkets": [
    { "name": "Bayside", "price": "$1.1-1.5M",
      "commute": "strong", "commute_txt": "LIRR ~25-32",   // rating + short label
      "style":   "moderate", "style_txt": "Colonials; few Tudors",
      "yard": "moderate", "asian": "strong", "schools": "strong",  // rating only
      "note": "one-line differentiator" }
    // ratings ∈ strong|moderate|weak
  ],
  "submarkets_note": "footnote under the table (e.g. what's uniform across areas)",

  "price_history_annual": {                    // 5-year view (analyst-estimated)
    "description": "string", "confidence_pct": 70,
    "series": [ { "year": "2021", "median_ask": 645000, "median_sold": 640000 }, ... ]
  },

  // price_history (monthly) is OPTIONAL — if omitted, build_report.py computes it
  // from recent_sales. Supply it only to override.
  "price_history": {
    "description": "string",
    "series": [ { "month": "2025-12", "median_ask": 0, "median_sold": 0, "n": 1 }, ... ]
  },

  "active_listings": [
    {
      "id": "kebab-address-slug",             // unique
      "address": "string", "price": 1480000,
      "beds": 4, "baths": 3, "sqft": 3420, "year_built": 1930,
      "style": "string", "lot_sqft": 6000,    // lot_sqft optional
      "url": "https://...",                   // REAL listing link (required, http)
      "image_url": "https://images.homes.com/.../primaryphoto.jpg",  // optional thumbnail
      "listing_agent": "string (optional)",
      "est_annual_tax": 11500, "tax_confidence_pct": 55,
      "status_note": "string (optional) — e.g. 'may have sold, verify'",
      "features": ["string", ...],
      "commute": { "nearest_transit": "string", "to_transit": "~5 min walk",
                   "to_grand_central": "~33 min door-to-door" },
      "assessments_issues_services": "string",
      "claude_assessment": {
        "description": "string", "benefits": "string",
        "concerns": "string", "critiques": "string",
        "fit_confidence_pct": 88               // listings auto-sort by this desc
      }
    }
  ],

  "recent_sales": [                            // comps; list_price_est auto-computed
    { "address": "string", "sold_price": 1700000, "vs_list_pct": -10,  // null OK
      "sold_date": "YYYY-MM-DD", "beds": 6, "baths": 4, "sqft": 2600,
      "year_built": 2012, "dom": 11 }
  ]
}
```

## Auto-computed by `build_report.py` (don't hand-fill)
- `recent_sales[].list_price_est` ← `sold_price / (1 + vs_list_pct/100)`.
- `price_history.series` (monthly median ask/sold) ← from `recent_sales` if absent.

## Hard rules
- **Always include a `submarkets` comparison** — every report, even single-town ones
  (split the town into its sections/sub-areas). Rate each on commute, style/Tudor
  availability, yard, Asian community, and schools.
- Every `active_listings[].url` must be a real listing link (verified by gatherer).
- `at_a_glance[].rating` ∈ {strong, moderate, weak}.
- Pre-2025 annual prices are estimates → set a realistic `confidence_pct`.
- Tax figures are estimates → always note "verify with county".
