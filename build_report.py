#!/usr/bin/env python3
"""
build_report.py — single source of truth for Real Estate Evaluation reports.

Usage:
    python3 build_report.py <area>.data.json [--out-dir DIR]

What it does (so no HTML is ever hand-written again):
  1. Loads the data JSON (the only thing an analyst/agent has to produce).
  2. Validates it against the expected schema (light, dependency-free).
  3. Auto-computes derived fields:
        - recent_sales[].list_price_est   from sold_price + vs_list_pct
        - price_history.series            monthly median ask/sold from recent_sales
          (only if price_history is missing/empty)
  4. Writes the normalized <area>.json  (data the page reads).
  5. Writes <area>.html  (shared template + embedded copy of the JSON as
     an offline fallback so it renders on file:// double-click).

The HTML template is universal: every area uses the same render code.
Only the data JSON changes between areas.
"""
import json, sys, os, statistics, re
from pathlib import Path

# --------------------------------------------------------------------------
# Validation (dependency-free; checks shape, not exhaustive types)
# --------------------------------------------------------------------------
REQUIRED_META = ["report_title", "area", "property_type", "buyer_criteria",
                 "data_as_of", "next_update_due", "sources", "disclaimer"]
REQUIRED_OVERVIEW = ["headline", "at_a_glance", "snapshot", "commute",
                     "schools", "taxes", "community",
                     "overall_assessment_confidence_pct", "buyer_fit_takeaways"]
REQUIRED_LISTING = ["id", "address", "price", "beds", "baths", "sqft",
                    "style", "url", "est_annual_tax",
                    "features", "assessments_issues_services", "claude_assessment"]
# year_built, lot_sqft, listing_agent, status_note, commute, tax_confidence_pct are optional
REQUIRED_ASSESS = ["description", "benefits", "concerns", "critiques", "fit_confidence_pct"]
RATINGS = {"strong", "moderate", "weak"}


def fail(msg):
    print("VALIDATION ERROR:", msg)
    sys.exit(1)


def validate(d):
    if "meta" not in d: fail("missing 'meta'")
    for k in REQUIRED_META:
        if k not in d["meta"]: fail(f"meta.{k} missing")
    mo = d.get("market_overview")
    if not mo: fail("missing 'market_overview'")
    for k in REQUIRED_OVERVIEW:
        if k not in mo: fail(f"market_overview.{k} missing")
    if "stats" not in mo["snapshot"]:
        fail("market_overview.snapshot.stats missing (array of {label,value})")
    for g in mo["at_a_glance"]:
        if g.get("rating") not in RATINGS:
            fail(f"at_a_glance rating must be one of {RATINGS}: got {g.get('rating')!r}")
    if "price_history_annual" not in d:
        fail("missing 'price_history_annual'")
    if "active_listings" not in d or not d["active_listings"]:
        fail("missing/empty 'active_listings'")
    ids = set()
    for p in d["active_listings"]:
        for k in REQUIRED_LISTING:
            if k not in p: fail(f"listing {p.get('id','?')}: {k} missing")
        if p["id"] in ids: fail(f"duplicate listing id {p['id']}")
        ids.add(p["id"])
        for k in REQUIRED_ASSESS:
            if k not in p["claude_assessment"]:
                fail(f"listing {p['id']}: claude_assessment.{k} missing")
        if not str(p["url"]).startswith("http"):
            fail(f"listing {p['id']}: url must be a real http(s) link")
        c = p.get("commute")
        if c and not all(x in c for x in ("nearest_transit", "to_transit", "to_grand_central")):
            fail(f"listing {p['id']}: commute needs nearest_transit/to_transit/to_grand_central")
    if "recent_sales" not in d:
        d["recent_sales"] = []
    print(f"  validation OK — {len(d['active_listings'])} listings, "
          f"{len(d['recent_sales'])} sales")


# --------------------------------------------------------------------------
# Derived fields
# --------------------------------------------------------------------------
def med(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2)


def compute_derived(d):
    # list_price_est from sold + vs_list_pct
    for s in d["recent_sales"]:
        if "list_price_est" not in s or s["list_price_est"] is None:
            vs = s.get("vs_list_pct")
            s["list_price_est"] = (round(s["sold_price"] / (1 + vs / 100))
                                   if vs not in (None, "") else s["sold_price"])
    # monthly price_history from recent_sales (only if not supplied)
    ph = d.get("price_history")
    if not ph or not ph.get("series"):
        bym = {}
        for s in d["recent_sales"]:
            bym.setdefault(s["sold_date"][:7], []).append(s)
        series = [{"month": m,
                   "median_ask": med([r["list_price_est"] for r in bym[m]]),
                   "median_sold": med([r["sold_price"] for r in bym[m]]),
                   "n": len(bym[m])}
                  for m in sorted(bym)]
        d["price_history"] = {
            "description": ("Median monthly LIST (ask) vs SOLD (closed) price, "
                            "auto-computed from the recent-sales feed. List prices "
                            "derived from sold price and the MLS percent-vs-list field. "
                            "Small monthly counts (n) make this noisy — read with the 5-year view."),
            "series": series}
        print(f"  computed price_history: {len(series)} monthly points")
    return d


# --------------------------------------------------------------------------
# HTML template (universal). Markers: __BASENAME__ and __EMBEDDED_DATA__
# --------------------------------------------------------------------------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Real Estate Evaluation</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{--bg:#0f1720;--panel:#162230;--panel2:#1d2c3d;--line:#2a3b4f;--ink:#e8eef5;--muted:#9fb2c6;
    --accent:#4ea1ff;--accent2:#56d6a0;--warn:#ffb454;--bad:#ff7a7a;--good:#56d6a0;--chip:#23344a;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;line-height:1.5}
  header{padding:32px 24px 20px;background:linear-gradient(160deg,#163b34,#0f1720);border-bottom:1px solid var(--line)}
  .wrap{max-width:1080px;margin:0 auto;padding:0 20px}
  h1{margin:0 0 6px;font-size:26px;letter-spacing:.2px}
  .sub{color:var(--muted);font-size:14px}
  .badge{display:inline-block;background:var(--chip);border:1px solid var(--line);color:var(--muted);border-radius:999px;padding:3px 11px;font-size:12px;margin:4px 6px 0 0}
  section{margin:26px 0}
  h2{font-size:19px;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
  h3{font-size:15px;margin:0 0 4px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
  .grid{display:grid;gap:14px}
  .stats{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
  .stat{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .stat .n{font-size:21px;font-weight:700}
  .stat .l{font-size:12px;color:var(--muted)}
  .cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media(max-width:780px){.cols{grid-template-columns:1fr}}
  .muted{color:var(--muted)}
  .conf{display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
  .bar{height:7px;width:90px;background:var(--chip);border-radius:6px;overflow:hidden;display:inline-block;vertical-align:middle}
  .bar > i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2))}
  .chartbox{position:relative;height:360px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-weight:600;position:sticky;top:0}
  tbody tr:hover{background:var(--panel2)}
  .pos{color:var(--good)} .neg{color:var(--bad)}
  details{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;overflow:hidden}
  details > summary{cursor:pointer;padding:14px 18px;list-style:none;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
  details > summary::-webkit-details-marker{display:none}
  summary .addr{font-weight:600;font-size:15px}
  summary .price{font-weight:700;color:var(--accent2);font-size:16px;white-space:nowrap}
  .pills span{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:2px 9px;font-size:11px;color:var(--muted);margin:3px 5px 0 0}
  .body{padding:0 18px 18px;border-top:1px solid var(--line)}
  .feat span{display:inline-block;background:#16304a;border:1px solid #244a6e;color:#bcd9f5;border-radius:8px;padding:3px 9px;font-size:12px;margin:4px 6px 0 0}
  .assess{margin-top:12px} .assess .row{margin:9px 0}
  .tag{font-size:11px;text-transform:uppercase;letter-spacing:.6px;font-weight:700}
  .tag.b{color:var(--good)} .tag.c{color:var(--warn)} .tag.k{color:var(--bad)} .tag.d{color:var(--accent)}
  .taxbox{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;margin-top:8px}
  footer{color:var(--muted);font-size:12px;padding:24px 0 50px;border-top:1px solid var(--line);margin-top:30px}
  .note{background:#2a2113;border:1px solid #5c4a1f;color:#ffd98a;border-radius:10px;padding:10px 14px;font-size:13px}
  ul.clean{margin:6px 0 0;padding-left:18px} ul.clean li{margin:5px 0}
  .glance{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin-top:4px}
  .gitem{display:flex;gap:10px;align-items:flex-start;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:9px 11px}
  .dot{flex:none;display:inline-block;width:10px;height:10px;border-radius:50%;margin-top:5px}
  .dot.strong{background:var(--good)} .dot.moderate{background:var(--warn)} .dot.weak{background:var(--bad)}
  .gitem .a{font-weight:600;font-size:13px} .gitem .nt{font-size:11.5px;color:var(--muted)}
  .rk{font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:700}
  .rk.strong{color:var(--good)} .rk.moderate{color:var(--warn)} .rk.weak{color:var(--bad)}
  .listing-link{display:inline-block;margin-top:12px;color:var(--accent);font-size:13px;font-weight:600;text-decoration:none;border:1px solid #244a6e;background:#16304a;border-radius:8px;padding:7px 12px}
  .listing-link:hover{background:#1c3c5c}
  .listing-img{display:block;width:100%;max-height:300px;object-fit:cover;border-radius:10px;margin-top:12px;border:1px solid var(--line)}
  .err{color:var(--bad)}
</style>
</head>
<body>
<header><div class="wrap"><h1 id="title">Real Estate Evaluation</h1><div class="sub" id="subtitle"></div><div id="badges"></div></div></header>
<div class="wrap" id="app"><p class="muted">Loading evaluation data…</p></div>
<script>
const fmt = n => n==null ? "—" : "$" + Number(n).toLocaleString();
const pct = p => (p==null?"":(p>0?"+":"")+p+"%");
function confBar(p){ return `<span class="conf"><span class="bar"><i style="width:${p}%"></i></span>${p}% confidence</span>`; }
function card(title, html){ return `<div class="panel" style="background:var(--panel2)"><h3>${title}</h3>${html}</div>`; }

function render(data){
  const m=data.meta, mo=data.market_overview, bc=m.buyer_criteria;
  document.getElementById('title').textContent=m.report_title;
  document.getElementById('subtitle').textContent=m.area+" · "+m.property_type+" · Budget "+bc.budget;
  let badges=`<span class="badge">Data as of ${m.data_as_of}</span><span class="badge">Next update: ${m.next_update_due}</span>`;
  if(m.history_window) badges+=`<span class="badge">History: ${m.history_window}</span>`;
  badges+=(bc.must_have||[]).map(x=>`<span class="badge">${x}</span>`).join("");
  if(bc.style_preference) badges+=`<span class="badge">Style: ${bc.style_preference}</span>`;
  document.getElementById('badges').innerHTML=badges;

  const s=mo.snapshot, fp=mo.flushing_proximity;
  // overview cards (all optional except commute/schools/taxes/community)
  let cards="";
  if(mo.commute) cards+=card("🚆 Commute to Manhattan",
    `<p style="margin:4px 0"><strong>${mo.commute.station||""}</strong></p>`+
    (mo.commute.to_grand_central?`<p style="margin:4px 0 0">Grand Central: ${mo.commute.to_grand_central}</p>`:"")+
    (mo.commute.to_penn?`<p style="margin:4px 0 0">Penn: ${mo.commute.to_penn}</p>`:"")+
    (mo.commute.notes?`<p class="muted" style="margin:6px 0 0">${mo.commute.notes}</p>`:""));
  if(fp) cards+=card("🥢 Flushing proximity &amp; familiarity "+confBar(fp.confidence_pct||0),
    `<p style="margin:4px 0"><strong>~${fp.drive_distance_miles} mi · ${fp.drive_time_min} min drive</strong></p>`+
    `<p class="muted" style="margin:4px 0 0">${fp.asian_amenities||""}</p>`);
  if(mo.schools) cards+=card("🎓 Schools",
    `<p class="muted" style="margin:4px 0">${mo.schools.ratings||""}</p>`+
    `<p style="margin:6px 0 0">${mo.schools.district||""}${mo.schools.enrollment_k12?" · "+mo.schools.enrollment_k12.toLocaleString()+" students":""}</p>`+
    (mo.schools.note?`<p class="muted" style="margin:6px 0 0">${mo.schools.note}</p>`:""));
  if(mo.taxes) cards+=card("💰 Property Taxes",
    `<p class="muted" style="margin:4px 0">${mo.taxes.context||""}</p>`+
    `<p style="margin:6px 0 0">Est. effective rate ≈ ${mo.taxes.estimated_effective_rate_pct}% · ${mo.taxes.exemptions||""}</p>`);
  if(mo.safety) cards+=card("🛡️ Safety",`<p class="muted" style="margin:4px 0">${mo.safety.summary||""}</p>`);
  if(mo.community) cards+=card("🏡 Community &amp; fit for dogs + gardening",
    `<p class="muted" style="margin:4px 0">${mo.community.character||""}</p>`+
    (mo.community.dog_and_garden_fit?`<p style="margin:6px 0 0"><strong>Yard/dog note:</strong> ${mo.community.dog_and_garden_fit}</p>`:""));

  const app=document.getElementById('app');
  app.innerHTML=`
  <section><h2>At a Glance — Attribute Fit</h2><div class="panel"><div class="glance">
    ${mo.at_a_glance.map(g=>`<div class="gitem"><span class="dot ${g.rating}"></span><span><span class="a">${g.attribute}</span> <span class="rk ${g.rating}">${g.rating}</span><br><span class="nt">${g.note}</span></span></div>`).join("")}
  </div></div></section>

  <section><h2>Market Overview &amp; Area Assessment ${confBar(mo.overall_assessment_confidence_pct)}</h2>
    <div class="panel">
      <p style="margin-top:0"><strong>${mo.headline}</strong></p>
      ${m.why_this_area?`<p class="muted" style="margin:6px 0 0">${m.why_this_area}</p>`:""}
      <div class="grid stats" style="margin-top:14px">
        ${s.stats.map(st=>`<div class="stat"><div class="n">${st.value}</div><div class="l">${st.label}</div></div>`).join("")}
      </div>
      ${s.note?`<p class="muted" style="margin:6px 0 0;font-size:12px">${s.note}</p>`:""}
      <div class="cols" style="margin-top:16px">${cards}</div>
      <div style="margin-top:14px"><h3>Key takeaways for your criteria</h3>
        <ul class="clean">${mo.buyer_fit_takeaways.map(t=>`<li>${t}</li>`).join("")}</ul></div>
    </div>
  </section>

  ${Array.isArray(data.submarkets)&&data.submarkets.length?`<section><h2>Submarket Comparison (${data.submarkets.length} areas)</h2>
    <div class="panel" style="overflow-x:auto"><table>
      <thead><tr><th>Sub-market</th><th>Price (detached)</th><th>→ Grand Central</th><th>Tudor/Colonial ≤budget</th><th>Yard</th><th>Asian comm.</th><th>Schools</th></tr></thead>
      <tbody>${data.submarkets.map(x=>`<tr>
        <td><strong>${x.name}</strong>${x.note?`<br><span class="muted" style="font-size:11px">${x.note}</span>`:''}</td>
        <td style="white-space:nowrap">${x.price||'—'}</td>
        <td><span class="dot ${x.commute}"></span> <span style="font-size:12px">${x.commute_txt||''}</span></td>
        <td><span class="dot ${x.style}"></span> <span style="font-size:12px">${x.style_txt||''}</span></td>
        <td><span class="dot ${x.yard}"></span></td>
        <td><span class="dot ${x.asian}"></span></td>
        <td><span class="dot ${x.schools}"></span></td></tr>`).join("")}</tbody></table>
      <p class="muted" style="font-size:12px;margin-top:8px">● <span style="color:var(--good)">strong</span> · <span style="color:var(--warn)">moderate</span> · <span style="color:var(--bad)">weak</span>. ${data.submarkets_note||''}</p>
    </div></section>`:""}

  ${data.price_history_annual?`<section><h2>Historic Ask vs. Closed Price — 5-Year View (annual)</h2><div class="panel">
    <p class="muted" style="margin-top:0">${data.price_history_annual.description} ${data.price_history_annual.confidence_pct?confBar(data.price_history_annual.confidence_pct):""}</p>
    <div class="chartbox"><canvas id="annualChart"></canvas></div></div></section>`:""}

  ${data.price_history?`<section><h2>Historic Ask vs. Closed Price — Recent Detail (monthly)</h2><div class="panel">
    <p class="muted" style="margin-top:0">${data.price_history.description}</p>
    <div class="chartbox"><canvas id="priceChart"></canvas></div></div></section>`:""}

  <section><h2>Active Listings — Detailed Assessment (${data.active_listings.length})</h2>
    <p class="muted">Click any property to expand. Ranked by fit to your criteria. Tax figures are estimates — verify with the county.</p>
    <div id="listings"></div></section>

  <section><h2>Recent Sales (comps) — Addresses &amp; Prices (${data.recent_sales.length})</h2>
    <div class="panel" style="overflow-x:auto"><table>
      <thead><tr><th>Address</th><th>Sold</th><th>Sold $</th><th>Est. List $</th><th>vs List</th><th>Bed/Bath</th><th>Sqft</th><th>Built</th><th>DOM</th></tr></thead>
      <tbody id="sales"></tbody></table></div></section>

  <footer class="wrap"><p class="note">${m.disclaimer}</p>
    <p><strong>Sources:</strong> ${(m.sources||[]).join(" · ")}</p>
    <p>Generated for ${m.area}. Snapshot: ${m.data_as_of}. Refresh quarterly.</p></footer>`;

  const rank=[...data.active_listings].sort((a,b)=>b.claude_assessment.fit_confidence_pct-a.claude_assessment.fit_confidence_pct);
  document.getElementById('listings').innerHTML=rank.map((p,i)=>{
    const ca=p.claude_assessment;
    return `<details ${i===0?'open':''}><summary><span>
      <span class="addr">${i+1}. ${p.address}</span><br><span class="pills">
        <span>${p.beds} bd</span><span>${p.baths} ba</span>${p.sqft?`<span>${p.sqft.toLocaleString()} sqft</span>`:''}
        <span>${p.style}</span>${p.year_built?`<span>Built ${p.year_built}</span>`:''}
        ${p.lot_sqft?`<span>Lot ${p.lot_sqft.toLocaleString()} sqft</span>`:''}<span>Fit ${ca.fit_confidence_pct}%</span>
      </span></span><span class="price">${fmt(p.price)}</span></summary>
      <div class="body">
        ${p.image_url?`<img class="listing-img" src="${p.image_url}" loading="lazy" alt="${p.address}" onerror="this.style.display='none'">`:''}
        ${p.status_note?`<p class="note" style="margin-top:14px">⚠ ${p.status_note}</p>`:''}
        <div class="feat" style="margin-top:12px">${p.features.map(f=>`<span>${f}</span>`).join("")}</div>
        ${p.commute?`<div class="taxbox" style="display:block;margin-bottom:8px">🚆 Nearest transit: <strong>${p.commute.nearest_transit}</strong> (${p.commute.to_transit}) &nbsp;·&nbsp; Door-to-door to Grand Central: <strong>${p.commute.to_grand_central}</strong></div>`:''}
        <div class="taxbox">Est. annual property tax: <strong>${fmt(p.est_annual_tax)}</strong> &nbsp; ${p.tax_confidence_pct?confBar(p.tax_confidence_pct):""}</div>
        <div class="assess">
          <div class="row"><span class="tag d">Assessments / issues / services</span><br>${p.assessments_issues_services}</div>
          <div class="row"><span class="tag d">Description</span><br>${ca.description}</div>
          <div class="row"><span class="tag b">Benefits</span><br>${ca.benefits}</div>
          <div class="row"><span class="tag c">Concerns</span><br>${ca.concerns}</div>
          <div class="row"><span class="tag k">Critiques</span><br>${ca.critiques}</div>
          <div class="row">${confBar(ca.fit_confidence_pct)} — overall fit to your criteria</div>
        </div>
        ${p.url?`<a class="listing-link" href="${p.url}" target="_blank" rel="noopener">View listing ↗</a>`:''}
        ${p.listing_agent?`<p class="muted" style="font-size:12px">Listing: ${p.listing_agent}</p>`:''}
      </div></details>`;}).join("");

  document.getElementById('sales').innerHTML=data.recent_sales.map(r=>{
    const v=r.vs_list_pct, cls=v==null?"":(v>=0?"pos":"neg");
    return `<tr><td>${r.address}</td><td>${r.sold_date}</td><td>${fmt(r.sold_price)}</td>
      <td class="muted">${fmt(r.list_price_est)}</td><td class="${cls}">${v==null?"—":pct(v)}</td>
      <td>${r.beds}/${r.baths}</td><td>${(r.sqft||0).toLocaleString()}</td><td>${r.year_built||"—"}</td><td>${r.dom??"—"}</td></tr>`;}).join("");

  const mkLine=(id,labels,ask,sold,radius)=>{ const el=document.getElementById(id); if(!el) return;
    new Chart(el,{type:'line',data:{labels,datasets:[
      {label:'Median Ask (list)',data:ask,borderColor:'#ffb454',backgroundColor:'rgba(255,180,84,.08)',tension:.3,borderWidth:2,pointRadius:radius,fill:true},
      {label:'Median Sold (closed)',data:sold,borderColor:'#4ea1ff',backgroundColor:'rgba(78,161,255,.10)',tension:.3,borderWidth:2,pointRadius:radius,fill:true}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#e8eef5'}},
        tooltip:{callbacks:{label:c=>c.dataset.label+': '+fmt(c.parsed.y)}}},
        scales:{x:{ticks:{color:'#9fb2c6'},grid:{color:'#22303f'}},y:{ticks:{color:'#9fb2c6',callback:v=>'$'+(v/1000)+'K'},grid:{color:'#22303f'}}}}});};
  if(data.price_history_annual){const pa=data.price_history_annual.series;mkLine('annualChart',pa.map(x=>x.year),pa.map(x=>x.median_ask),pa.map(x=>x.median_sold),4);}
  if(data.price_history){const ph=data.price_history.series;mkLine('priceChart',ph.map(x=>x.month),ph.map(x=>x.median_ask),ph.map(x=>x.median_sold),3);}
}

fetch('./__BASENAME__.json').then(r=>{if(!r.ok)throw new Error('http');return r.json();}).then(render)
  .catch(()=>{ if(window.EMBEDDED_DATA){render(window.EMBEDDED_DATA);}
    else{document.getElementById('app').innerHTML='<p class="err">Could not load __BASENAME__.json. Keep it in the same folder as this HTML file.</p>';}});
</script>
<script>
/* Offline fallback copy of the JSON so the page renders on file:// double-click. Keep in sync with the .json file. */
window.EMBEDDED_DATA = __EMBEDDED_DATA__;
</script>
</body>
</html>
"""


def build(data_path, out_dir=None):
    data_path = Path(data_path)
    raw = json.loads(data_path.read_text())
    print(f"Building report from {data_path.name}")
    validate(raw)
    raw = compute_derived(raw)

    # basename: strip a trailing .data from the stem if present
    stem = data_path.stem
    base = stem[:-5] if stem.endswith(".data") else stem
    # Folder convention: every evaluation gets its own folder named after the slug.
    # If --out-dir isn't given, write into <data-file-dir>/<base>/ (created if needed).
    if out_dir:
        out_dir = Path(out_dir)
    elif data_path.parent.name == base:
        out_dir = data_path.parent          # data file already lives in the slug folder
    else:
        out_dir = data_path.parent / base
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{base}.json"
    html_path = out_dir / f"{base}.html"

    normalized = json.dumps(raw, indent=2, ensure_ascii=False)
    json_path.write_text(normalized)
    html = TEMPLATE.replace("__BASENAME__", base).replace("__EMBEDDED_DATA__", normalized)
    html_path.write_text(html)
    print(f"  wrote {out_dir.name}/{json_path.name}")
    print(f"  wrote {out_dir.name}/{html_path.name}")
    print(f"Done. Verify with:  python3 _pipeline/verify_report.py {out_dir}/{base}")
    return json_path, html_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = None
    if "--out-dir" in sys.argv:
        out = sys.argv[sys.argv.index("--out-dir") + 1]
    build(args[0], out)
