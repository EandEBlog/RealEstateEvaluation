#!/usr/bin/env python3
"""
verify_report.py — scripted QA for a generated report (no manual node harness).

Usage:  python3 verify_report.py <slug>     # expects <slug>.json and <slug>.html

Checks:
  - embedded EMBEDDED_DATA == the .json file
  - render() executes without throwing (DOM + Chart + fetch stubbed via node)
  - 2 charts instantiate; listings render with url + commute; sales rows render
  - monthly price_history medians match recent_sales
Exits non-zero on any failure.
"""
import json, subprocess, sys, tempfile, os
from pathlib import Path

NODE_HARNESS = r"""
const fs=require('fs');
const base=process.argv[2];
const html=fs.readFileSync(base+'.html','utf8');
const json=JSON.parse(fs.readFileSync(base+'.json','utf8'));
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const renderScript=scripts.find(s=>s.includes('function render'));
const dataScript=scripts.find(s=>s.includes('window.EMBEDDED_DATA =') && !s.includes('function render'));
const store={};
global.document={getElementById:id=>{store[id]=store[id]||{set innerHTML(v){this.__h=v},get innerHTML(){return this.__h||''},textContent:''};return store[id];}};
let charts=0; global.Chart=function(){charts++;return{}};
global.window={}; global.fetch=()=>Promise.reject(new Error('x'));
const out={};
try{ eval(dataScript); eval(renderScript.replace(/fetch\([\s\S]*?\}\);/,'')); render(window.EMBEDDED_DATA); out.threw=null; }
catch(e){ out.threw=e.name+': '+e.message; }
// embedded == json
const st=html.indexOf('window.EMBEDDED_DATA =')+'window.EMBEDDED_DATA ='.length;
const en=html.indexOf('</script>',st);
let embOk=false; try{ embOk=JSON.stringify(JSON.parse(html.slice(st,en).trim().replace(/;+$/,'')))===JSON.stringify(json);}catch(e){}
const L=(store['listings']&&store['listings'].__h)||'', S=(store['sales']&&store['sales'].__h)||'';
out.embOk=embOk; out.charts=charts;
out.listings=json.active_listings.length;
out.links=(L.match(/View listing/g)||[]).length;
out.commutes=(L.match(/Door-to-door to Grand Central/g)||[]).length;
out.saleRows=(S.match(/<tr>/g)||[]).length;
// monthly median check
const med=a=>{a=[...a].sort((x,y)=>x-y);const n=a.length;return n%2?a[(n-1)/2]:Math.round((a[n/2-1]+a[n/2])/2);};
const bym={}; for(const r of json.recent_sales){(bym[r.sold_date.slice(0,7)]=bym[r.sold_date.slice(0,7)]||[]).push(r.sold_price);}
let flags=0; if(json.price_history) for(const p of json.price_history.series){const c=med(bym[p.month]||[p.median_sold]);if(Math.abs(c-p.median_sold)>1)flags++;}
out.medianFlags=flags;
console.log(JSON.stringify(out));
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    slug = sys.argv[1]
    base = Path(slug)
    if base.suffix:  # allow passing slug.json or slug.html
        base = base.with_suffix("")
    for ext in (".json", ".html"):
        if not Path(str(base) + ext).exists():
            print(f"FAIL: missing {base}{ext}"); sys.exit(1)

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(NODE_HARNESS); harness = f.name
    try:
        r = subprocess.run(["node", harness, base.name],
                           capture_output=True, text=True, cwd=str(base.parent) or ".")
    finally:
        os.unlink(harness)
    if r.returncode != 0:
        print("FAIL: node error\n", r.stderr); sys.exit(1)
    o = json.loads(r.stdout.strip().splitlines()[-1])

    ok = True
    def chk(cond, label, detail=""):
        nonlocal ok
        print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  [{detail}]"))
        ok = ok and cond

    print(f"Verifying {base.name}")
    chk(o["threw"] is None, "render() executes", o["threw"])
    chk(o["embOk"], "embedded JSON == .json file")
    chk(o["charts"] == 2, "2 charts instantiate", f"got {o['charts']}")
    chk(o["links"] == o["listings"], "every listing has a View-listing link",
        f"{o['links']}/{o['listings']}")
    chk(o["commutes"] == o["listings"], "every listing has commute info",
        f"{o['commutes']}/{o['listings']}")
    chk(o["saleRows"] == len(json.loads(Path(str(base) + ".json").read_text())["recent_sales"]),
        "all sales rows render")
    chk(o["medianFlags"] == 0, "monthly medians match recent_sales",
        f"{o['medianFlags']} mismatches")
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
