#!/usr/bin/env python3
"""
Orchestrator: score -> filter -> tailor -> dashboard, with daily dedup.

Reads data/jobs_raw.json (produced by scrape.py), scores every job against
profile.json, keeps those with fit_score >= min and passing hard filters,
generates application bundles, updates data/seen.json (so already-seen jobs are
not resurfaced unless the posting changed), and writes:
  - data/matches.json      (all current matches, with status preserved)
  - dashboard/index.html   (clean sortable table)
  - data/new_today.json    (matches new or updated since last run)

Status values: New | Saved | Applied | Interview | Rejected | Offer
Existing statuses are preserved across runs (keyed by job url).
"""
import json
import hashlib
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import score_job
import tailor

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "pipeline" / "profile.json").read_text())
ENRICHED = ROOT / "data" / "jobs_enriched.json"
RAW = ENRICHED if ENRICHED.exists() else (ROOT / "data" / "jobs_raw.json")
SEEN = ROOT / "data" / "seen.json"
MATCHES = ROOT / "data" / "matches.json"
NEW_TODAY = ROOT / "data" / "new_today.json"
DASH = ROOT / "dashboard" / "index.html"
DOCS_SEG = ROOT / "pipeline" / "dashboard_path.txt"


def publish_dashboard():
    """Copy dashboard to docs/<secret>/ for GitHub Pages."""
    seg = DOCS_SEG.read_text().strip() if DOCS_SEG.exists() else ""
    if not seg or not DASH.exists():
        return None
    dest_dir = ROOT / "docs" / seg
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "index.html"
    dest.write_text(DASH.read_text())
    return dest


def job_fingerprint(job):
    h = hashlib.sha1()
    h.update((job.get("title", "") + "|" + (job.get("description", "")[:500])).encode())
    return h.hexdigest()[:12]


def load_json(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def main(make_apps=True):
    raw = load_json(RAW, [])
    seen = load_json(SEEN, {})          # url -> {fingerprint, first_seen, status}
    prev_matches = {m["url"]: m for m in load_json(MATCHES, [])}
    today = date.today().isoformat()

    matches, new_today = [], []
    for job in raw:
        scored = score_job(job, PROFILE)
        if not scored["passes_filters"]:
            continue
        url = job["url"]
        fp = job_fingerprint(job)
        prev = seen.get(url)
        is_new = prev is None
        is_updated = (prev is not None) and (prev.get("fingerprint") != fp)

        # preserve user-set status across runs
        status = prev_matches.get(url, {}).get("status") or (prev.get("status") if prev else None) or "New"
        if is_updated and status == "New":
            status = "New"

        fl = scored["flags"]
        benefits = []
        if fl.get("benefits_401k"):
            benefits.append("401(k)")
        if fl.get("pension"):
            benefits.append("Pension")
        rec = {
            "title": job.get("title"), "employer": job.get("employer"),
            "location": job.get("location") or job.get("employer_state"),
            "state": fl.get("state") or "",
            "no_tax_state": fl.get("no_tax_state", False),
            "salary": (f"${fl['salary_usd_max']:,}"
                       if fl["salary_usd_max"] else "Salary Not Disclosed"),
            "work_mode": fl["remote_type"],
            "date_posted": job.get("date_posted") or "",
            "days_old": fl.get("days_since_posted"),
            "fit_score": scored["fit_score"],
            "priority": scored["priority"],
            "role_type": fl.get("role_type") or "Mixed",
            "technical": fl.get("technical", False),
            "min_years": fl.get("min_years_required"),
            "benefits": benefits,
            "big_employer": fl.get("big_employer", False),
            "visa_flag": "⚑ Visa mentioned" if fl["visa_sponsorship_mentioned"] else "",
            "onsite_flag": "On-site" if fl["onsite"] else "",
            "url": url,
            "source_platform": job.get("source_platform"),
            "status": status,
            "first_seen": (prev.get("first_seen") if prev else today),
            "last_seen": today,
            "updated": is_updated,
            "reasons": scored["reasons"],
            "app_folder": None,
        }
        if make_apps:
            rec["app_folder"] = tailor.save_application(job, scored)

        matches.append(rec)
        seen[url] = {"fingerprint": fp, "first_seen": rec["first_seen"],
                     "status": status, "last_seen": today}
        if is_new or is_updated:
            new_today.append(rec)

    matches.sort(key=lambda r: (r.get("priority", r["fit_score"]), r["fit_score"]),
                 reverse=True)
    MATCHES.write_text(json.dumps(matches, indent=2))
    NEW_TODAY.write_text(json.dumps(new_today, indent=2))
    SEEN.write_text(json.dumps(seen, indent=2))
    write_dashboard(matches, new_today)
    published = publish_dashboard()

    print(f"Scored {len(raw)} raw jobs")
    print(f"Matches (score>={PROFILE['filters']['min_fit_score']}, filters pass): {len(matches)}")
    print(f"New or updated this run: {len(new_today)}")
    print(f"Dashboard: {DASH}")
    if published:
        print(f"Published: {published}")
    return matches, new_today


DASH_CSS = """
:root{
  --bg:#eef2f6; --surface:#fff; --surface-2:#f8fafc;
  --ink:#0f172a; --text:#1e293b; --muted:#475569;
  --line:#dbe3ec; --line-soft:#eef2f6;
  --primary:#0e7490; --primary-ink:#155e75; --primary-soft:#cffafe;
  --accent:#0369a1; --accent-soft:#e0f2fe;
  --amber:#b45309; --amber-soft:#fef3c7;
  --hi:#047857; --hi-soft:#d1fae5;
  --mid:#b45309; --mid-soft:#fef3c7;
  --lo:#64748b;
  --sidebar-w:248px;
  --ease:cubic-bezier(0.16,1,0.3,1);
  --z-sidebar:30; --z-toolbar:25; --z-thead:20;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:'Fira Sans',system-ui,sans-serif;
  font-size:13.5px; line-height:1.45;
  -webkit-font-smoothing:antialiased;
}
.mono{font-family:'Fira Code',ui-monospace,monospace;
  font-variant-numeric:tabular-nums; letter-spacing:-0.02em; font-size:12px}

/* ---- app shell ---- */
.app{display:grid; grid-template-columns:var(--sidebar-w) 1fr; min-height:100vh; align-items:stretch}
.sidebar{
  position:sticky; top:0; align-self:start; height:100vh; max-height:100vh; z-index:var(--z-sidebar);
  background:var(--surface); border-right:1px solid var(--line);
  display:flex; flex-direction:column; overflow:hidden;
}
.sidebar-head{
  padding:18px 16px 12px; border-bottom:1px solid var(--line-soft);
  font-size:11px; font-weight:600; letter-spacing:0.08em;
  text-transform:uppercase; color:var(--muted);
}
.sidebar-body{padding:12px 14px 20px; overflow-y:auto; flex:1;
  display:flex; flex-direction:column; gap:10px}
.filter-label{font-size:11px; font-weight:600; color:var(--muted);
  letter-spacing:0.04em; text-transform:uppercase; margin:4px 0 2px}
.presets{display:flex; flex-wrap:wrap; gap:6px; margin-bottom:4px}
.preset{
  font:inherit; font-size:12px; font-weight:500; color:var(--text);
  background:var(--surface-2); border:1px solid var(--line);
  border-radius:999px; padding:5px 11px; cursor:pointer;
  transition:background 140ms var(--ease),border-color 140ms var(--ease),color 140ms var(--ease);
}
.preset:hover{background:var(--primary-soft); border-color:#a5f3fc; color:var(--primary-ink)}
.preset.on{background:var(--primary-soft); border-color:var(--primary); color:var(--primary-ink)}
.main{min-width:0; min-height:100vh; display:flex; flex-direction:column; overflow:visible}

/* ---- topbar ---- */
.topbar{
  background:var(--ink); color:#e2e8f0;
  padding:16px 22px 14px; border-bottom:1px solid #1e293b;
}
.brandrow{display:flex; align-items:flex-end; justify-content:space-between;
  gap:12px; flex-wrap:wrap; margin-bottom:14px}
.brand{display:flex; flex-direction:column; gap:3px}
.topbar h1{margin:0; font-size:20px; font-weight:600; letter-spacing:-0.03em;
  color:#f8fafc; text-wrap:balance}
.topbar h1 .mark{color:#67e8f9}
.meta{font-size:12px; color:#94a3b8}
.updated{font-size:11px; color:#64748b; font-family:'Fira Code',monospace}
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(108px,1fr)); gap:8px}
.kpi{
  padding:10px 12px; background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08); border-radius:10px;
  border-left:3px solid #334155;
}
.kpi.accent{border-left-color:#22d3ee}
.kpi b{display:block; font-size:22px; font-weight:600; color:#f8fafc;
  letter-spacing:-0.03em; line-height:1.1}
.kpi span{font-size:10.5px; color:#94a3b8; letter-spacing:0.02em}

/* ---- toolbar ---- */
.toolbar{
  position:sticky; top:0; z-index:var(--z-toolbar);
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:10px 22px; background:rgba(238,242,246,.94);
  backdrop-filter:blur(10px) saturate(1.1); border-bottom:1px solid var(--line);
}
.search{flex:1 1 260px; position:relative; min-width:200px}
.search input{
  width:100%; padding:9px 12px 9px 34px; font:inherit; font-size:13.5px;
  color:var(--ink); background:var(--surface); border:1px solid var(--line);
  border-radius:8px; transition:border-color 140ms var(--ease),box-shadow 140ms var(--ease);
}
.search input::placeholder{color:#94a3b8}
.search input:focus{outline:none; border-color:var(--primary);
  box-shadow:0 0 0 3px var(--primary-soft)}
.search svg{position:absolute; left:11px; top:50%; transform:translateY(-50%);
  width:15px; height:15px; color:#94a3b8; pointer-events:none}
.search kbd{
  position:absolute; right:10px; top:50%; transform:translateY(-50%);
  font-family:'Fira Code',monospace; font-size:10px; color:#94a3b8;
  background:var(--surface-2); border:1px solid var(--line); border-radius:4px;
  padding:1px 5px; pointer-events:none;
}
.chips{display:flex; gap:6px; flex-wrap:wrap; width:100%}
.chip{
  display:none; font-size:11px; font-weight:500; color:var(--primary-ink);
  background:var(--primary-soft); border:1px solid #a5f3fc;
  border-radius:999px; padding:3px 10px; cursor:pointer;
}
.chip.show{display:inline-flex; align-items:center; gap:4px}
.chip:hover{background:#a5f3fc}
.count{margin-left:auto; font-size:12px; color:var(--muted); white-space:nowrap}
.count b{color:var(--ink); font-weight:600}
.filter-toggle{display:none}
.backdrop{display:none; position:fixed; inset:0; z-index:29; background:rgba(15,23,42,.4)}
.backdrop.show{display:block}

/* ---- form controls ---- */
.sel{position:relative; width:100%}
.sel select{
  appearance:none; width:100%; font:inherit; font-size:13px; color:var(--ink);
  background:var(--surface-2); border:1px solid var(--line); border-radius:8px;
  padding:8px 30px 8px 10px; cursor:pointer;
  transition:border-color 140ms var(--ease),box-shadow 140ms var(--ease);
}
.sel::after{content:""; position:absolute; right:11px; top:50%; width:7px; height:7px;
  border-right:1.6px solid #94a3b8; border-bottom:1.6px solid #94a3b8;
  transform:translateY(-65%) rotate(45deg); pointer-events:none}
.sel select:focus{outline:none; border-color:var(--primary); box-shadow:0 0 0 3px var(--primary-soft)}
.toggle{display:flex; align-items:center; gap:8px; font-size:13px; color:var(--text);
  padding:8px 10px; background:var(--surface-2); border:1px solid var(--line);
  border-radius:8px; cursor:pointer; user-select:none; width:100%;
  transition:border-color 140ms var(--ease),background 140ms var(--ease)}
.toggle input{accent-color:var(--primary); width:15px; height:15px; cursor:pointer; flex-shrink:0}
.toggle.on{border-color:var(--primary); background:var(--primary-soft); color:var(--primary-ink)}

.table-note{
  padding:8px 14px; font-size:12.5px; color:var(--muted);
  background:var(--surface); border:1px solid var(--line); border-radius:10px;
  margin-bottom:10px;
}
.table-note b{color:var(--ink)}
/* ---- table ---- */
.table-panel{padding:12px 14px 48px; flex:1; min-height:0; display:flex; flex-direction:column}
.table-scroll{
  overflow:auto; -webkit-overflow-scrolling:touch;
  border:1px solid var(--line); border-radius:12px;
  background:var(--surface); box-shadow:0 1px 2px rgba(15,23,42,.04);
  min-height:min(70vh,720px); max-height:calc(100vh - 220px);
}
table{width:100%; border-collapse:collapse; min-width:1100px}
thead th{
  position:sticky; top:0; z-index:var(--z-thead);
  background:var(--surface-2); color:var(--muted); font-weight:600; font-size:10.5px;
  letter-spacing:0.06em; text-transform:uppercase; text-align:left;
  padding:10px 12px; border-bottom:1px solid var(--line); cursor:pointer;
  white-space:nowrap; transition:color 120ms var(--ease); user-select:none;
}
thead th:hover{color:var(--ink)}
thead th .arw{opacity:0; margin-left:3px; font-size:8px}
thead th[data-dir] .arw{opacity:1}
thead th:first-child{position:sticky; left:0; z-index:calc(var(--z-thead)+1);
  background:var(--surface-2); box-shadow:1px 0 0 var(--line)}
tbody td{padding:9px 12px; border-bottom:1px solid var(--line-soft); vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr{transition:background-color 120ms var(--ease)}
tbody tr.row-out{display:none}
tbody tr:nth-child(even){background:#f8fafc}
tbody tr:nth-child(even) td:first-child{background:#f8fafc}
tbody tr:nth-child(odd) td:first-child{background:var(--surface)}
@media (hover:hover){tbody tr:hover{background:#f0f9ff}}
@media (hover:hover){tbody tr:hover td:first-child{background:#f0f9ff}}
tbody td:first-child{position:sticky; left:0; z-index:1;
  box-shadow:1px 0 0 var(--line-soft)}
tr.is-new td:first-child{box-shadow:inset 3px 0 0 var(--primary),1px 0 0 var(--line-soft)}
.c-title{max-width:280px}
.c-title a{color:var(--ink); font-weight:550; text-decoration:none; letter-spacing:-0.01em;
  cursor:pointer}
.c-title a:hover{color:var(--primary-ink); text-decoration:underline; text-underline-offset:2px}
.c-title a:focus-visible{outline:2px solid var(--primary); outline-offset:2px; border-radius:2px}
.c-title .src{display:block; font-size:10.5px; color:var(--muted); margin-top:2px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.new-tag{display:inline-block; margin-left:6px; font-size:9.5px; font-weight:600;
  color:var(--primary-ink); background:var(--primary-soft); padding:1px 6px;
  border-radius:999px; vertical-align:middle}
.c-emp{font-weight:500; color:var(--text); max-width:160px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.c-loc{color:var(--muted); font-size:12.5px; max-width:140px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.sal{color:var(--ink); font-weight:550}
.sal-none{color:#94a3b8; font-weight:400}
.mode{font-size:11px; font-weight:600; padding:2px 8px; border-radius:6px; white-space:nowrap}
.mode-Remote{color:var(--hi); background:var(--hi-soft)}
.mode-Hybrid{color:var(--mid); background:var(--mid-soft)}
.mode-On-site{color:var(--muted); background:var(--line-soft)}
.fit{display:inline-flex; align-items:center; gap:6px; min-width:72px}
.fit b{font-size:12.5px; font-weight:600; font-family:'Fira Code',monospace; min-width:24px}
.fit-bar{flex:1; height:4px; background:var(--line-soft); border-radius:2px; overflow:hidden; min-width:32px}
.fit-bar i{display:block; height:100%; border-radius:2px; background:currentColor}
.fit-hi{color:var(--hi)} .fit-mid{color:var(--mid)} .fit-lo{color:var(--lo)}
.pill-visa{font-size:10.5px; font-weight:600; color:var(--amber);
  background:var(--amber-soft); padding:2px 7px; border-radius:6px}
.pill-big{color:#ca8a04; font-size:12px; cursor:help}
.st-chip{display:inline-block; font-family:'Fira Code',monospace; font-size:11px;
  font-weight:500; color:var(--muted); background:var(--line-soft);
  padding:2px 7px; border-radius:5px}
.st-chip.st-notax{color:var(--hi); background:var(--hi-soft)}
.role{font-size:11px; font-weight:600; padding:2px 8px; border-radius:6px; white-space:nowrap}
.role-non-technical,.role-non{color:var(--hi); background:var(--hi-soft)}
.role-technical{color:var(--muted); background:var(--line-soft)}
.role-mixed{color:var(--mid); background:var(--mid-soft)}
select.status{appearance:none; font:inherit; font-size:12px; font-weight:550;
  padding:4px 22px 4px 8px; border-radius:6px; border:1px solid transparent;
  cursor:pointer; background-position:right 6px center; background-repeat:no-repeat;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 8 8'%3E%3Cpath d='M1 2l3 3 3-3' stroke='%2364748b' stroke-width='1.4' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
  transition:border-color 130ms var(--ease),box-shadow 130ms var(--ease)}
select.status:focus{outline:none; box-shadow:0 0 0 3px var(--primary-soft)}
.st-New{color:var(--hi); background:var(--hi-soft)}
.st-Saved{color:#1d4ed8; background:#dbeafe}
.st-Applied{color:#6d28d9; background:#ede9fe}
.st-Interview{color:var(--amber); background:var(--amber-soft)}
.st-Rejected{color:#be123c; background:#ffe4e6}
.st-Offer{color:var(--hi); background:var(--hi-soft)}
input.notes{width:100%; min-width:120px; font:inherit; font-size:12px; color:var(--ink);
  background:transparent; border:1px solid transparent; border-radius:6px; padding:4px 7px;
  transition:border-color 130ms var(--ease),background 130ms var(--ease)}
input.notes::placeholder{color:#94a3b8}
input.notes:hover{background:var(--surface-2)}
input.notes:focus{outline:none; background:var(--surface); border-color:var(--primary);
  box-shadow:0 0 0 3px var(--primary-soft)}
.c-app a{font-size:12px; font-weight:550; color:var(--primary-ink); text-decoration:none;
  cursor:pointer; white-space:nowrap}
.c-app a:hover{text-decoration:underline; text-underline-offset:2px}
.c-app a:focus-visible{outline:2px solid var(--primary); outline-offset:2px; border-radius:2px}
.empty{display:none; padding:48px 20px; text-align:center; color:var(--muted)}
.empty.show{display:block}
.empty b{display:block; font-size:15px; color:var(--ink); margin-bottom:6px}
@media (prefers-reduced-motion:reduce){*{transition:none!important; animation:none!important}}
@media (max-width:960px){
  .app{display:block}
  .sidebar{
    position:fixed; left:0; top:0; width:min(300px,88vw); height:100vh;
    transform:translateX(-100%); transition:transform 200ms var(--ease);
    box-shadow:8px 0 32px rgba(15,23,42,.12); z-index:var(--z-sidebar);
  }
  .main{min-height:100vh}
  .sidebar.open{transform:translateX(0)}
  .filter-toggle{
    display:inline-flex; align-items:center; gap:6px; font:inherit; font-size:13px;
    font-weight:500; padding:8px 12px; background:var(--surface); border:1px solid var(--line);
    border-radius:8px; cursor:pointer;
  }
  .topbar,.toolbar{padding-left:14px; padding-right:14px}
  .count{margin-left:0; width:100%}
}
"""

DASH_JS = """
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const tb=$('#tb'), rows=$$('#tb tr');
const ST_KEY='jobsearch_status', NT_KEY='jobsearch_notes';
let stStore={}, ntStore={};
try{stStore=JSON.parse(localStorage.getItem(ST_KEY)||'{}');}catch(e){stStore={};}
try{ntStore=JSON.parse(localStorage.getItem(NT_KEY)||'{}');}catch(e){ntStore={};}

// restore + persist status
$$('select.status').forEach(s=>{
  const u=s.dataset.url;
  if(stStore[u]) s.value=stStore[u];
  s.dataset.cur=s.value; s.className='status st-'+s.value;
  s.closest('tr').dataset.status=s.value;
  s.addEventListener('change',()=>{
    stStore[u]=s.value; localStorage.setItem(ST_KEY,JSON.stringify(stStore));
    s.className='status st-'+s.value; s.closest('tr').dataset.status=s.value; filter();
  });
});
// restore + persist notes (debounced)
$$('input.notes').forEach(n=>{
  const u=n.dataset.url; if(ntStore[u]) n.value=ntStore[u];
  let t; n.addEventListener('input',()=>{clearTimeout(t); t=setTimeout(()=>{
    ntStore[u]=n.value; localStorage.setItem(NT_KEY,JSON.stringify(ntStore));},250);});
});

// ---- filtering ----
const q=$('#q'), fState=$('#fState'), fRole=$('#fRole'), fPosted=$('#fPosted'),
      fMode=$('#fMode'), fStatus=$('#fStatus'), fFit=$('#fFit'),
      tNew=$('#tNew'), tBig=$('#tBig'), count=$('#count');
const chips=$('#chips');

function setPreset(btn, apply){
  if(!btn) return;
  btn.classList.toggle('on', apply);
}
function updateChips(){
  const active=[];
  if(fState.value==='__notax') active.push(['No-tax states',()=>{fState.value='';filter();}]);
  else if(fState.value) active.push([fState.value,()=>{fState.value='';filter();}]);
  if(fRole.value) active.push([fRole.value,()=>{fRole.value='';filter();}]);
  if(fPosted.value!=='9999') active.push(['≤ '+fPosted.value+'d',()=>{fPosted.value='9999';filter();}]);
  if(fMode.value) active.push([fMode.value,()=>{fMode.value='';filter();}]);
  if(fStatus.value) active.push([fStatus.value,()=>{fStatus.value='';filter();}]);
  if(parseFloat(fFit.value)>0) active.push([fFit.value+'+ fit',()=>{fFit.value='0';filter();}]);
  if(tNew.checked) active.push(['New only',()=>{tNew.checked=false;filter();}]);
  if(tBig.checked) active.push(['Large employers',()=>{tBig.checked=false;filter();}]);
  if(q.value.trim()) active.push(['"'+q.value.trim()+'"',()=>{q.value='';filter();}]);
  chips.innerHTML=active.map(([label,fn])=>
    '<button type="button" class="chip show" data-x="1">'+label+' <span aria-hidden="true">×</span></button>'
  ).join('');
  $$('.chip[data-x]').forEach((c,i)=>c.addEventListener('click',active[i][1]));
}
function filter(){
  const term=(q?.value||'').trim().toLowerCase(), state=fState?.value||'', role=fRole?.value||'',
        maxDays=parseInt(fPosted?.value,10)||9999, mode=fMode?.value||'', st=fStatus?.value||'',
        fit=parseFloat(fFit?.value)||0, onlyNew=!!tNew?.checked, onlyBig=!!tBig?.checked;
  let shown=0;
  rows.forEach(r=>{
    const d=r.dataset;
    const search=(d.search||'').toLowerCase();
    const days=parseInt(d.days,10); const daysOk=isNaN(days)||days<=maxDays;
    const rowFit=parseFloat(d.fit)||0;
    const stateOk=!state||(state==='__notax'?d.notax==='1':d.state===state);
    const ok=(!term||search.includes(term))&&stateOk&&(!role||d.role===role)&&daysOk
      &&(!mode||d.mode===mode)&&(!st||d.status===st)&&(rowFit>=fit)
      &&(!onlyNew||d.new==='1')&&(!onlyBig||d.big==='1');
    r.classList.toggle('row-out',!ok); if(ok) shown++;
  });
  count.innerHTML='<b>'+shown+'</b> of '+rows.length;
  $('#empty').classList.toggle('show', shown===0);
  [tNew,tBig].forEach(t=>t.closest('.toggle').classList.toggle('on',t.checked));
  setPreset($('#pNotax'), state==='__notax');
  setPreset($('#pNontech'), role==='Non-technical');
  setPreset($('#pRemote'), mode==='Remote');
  setPreset($('#pNew'), onlyNew);
  updateChips();
}
[q,fState,fRole,fPosted,fMode,fStatus,fFit].forEach(e=>e.addEventListener('input',filter));
[tNew,tBig].forEach(e=>e.addEventListener('change',filter));

// quick presets
$('#pNotax')?.addEventListener('click',()=>{fState.value=fState.value==='__notax'?'':'__notax';filter();});
$('#pNontech')?.addEventListener('click',()=>{fRole.value=fRole.value==='Non-technical'?'':'Non-technical';filter();});
$('#pRemote')?.addEventListener('click',()=>{fMode.value=fMode.value==='Remote'?'':'Remote';filter();});
$('#pNew')?.addEventListener('click',()=>{tNew.checked=!tNew.checked;filter();});
$('#clearFilters')?.addEventListener('click',()=>{resetFilters(); filter();});

function resetFilters(){
  q.value=''; fState.value=''; fRole.value=''; fPosted.value='9999';
  fMode.value=''; fStatus.value=''; fFit.value='0';
  tNew.checked=false; tBig.checked=false;
}

// keyboard: / focuses search
document.addEventListener('keydown',e=>{
  if(e.key==='/' && document.activeElement!==q){
    e.preventDefault(); q.focus(); q.select();
  }
  if(e.key==='Escape' && document.activeElement===q){ q.blur(); }
});

// mobile filter drawer
const sidebar=$('#sidebar'), backdrop=$('#backdrop'), ft=$('#filterToggle');
ft?.addEventListener('click',()=>{sidebar.classList.add('open'); backdrop.classList.add('show');});
backdrop?.addEventListener('click',()=>{sidebar.classList.remove('open'); backdrop.classList.remove('show');});

// ---- sorting ----
$$('thead th').forEach((th,i)=>{
  if(th.dataset.nosort!==undefined) return;
  th.addEventListener('click',()=>{
    const dir=th.dataset.dir==='asc'?'desc':'asc';
    $$('thead th').forEach(o=>{delete o.dataset.dir; const a=o.querySelector('.arw'); if(a)a.textContent='';});
    th.dataset.dir=dir; const arw=th.querySelector('.arw'); if(arw)arw.textContent=dir==='asc'?'▲':'▼';
    const num=th.dataset.num!==undefined;
    [...tb.rows].sort((a,b)=>{
      let x=a.cells[i].dataset.sort??a.cells[i].innerText, y=b.cells[i].dataset.sort??b.cells[i].innerText;
      if(num){x=parseFloat(x)||0; y=parseFloat(y)||0; return dir==='asc'?x-y:y-x;}
      return dir==='asc'?(''+x).localeCompare(y):(''+y).localeCompare(x);
    }).forEach(r=>tb.appendChild(r));
  });
});
if(q){q.setAttribute('readonly','readonly');
  q.addEventListener('focus',()=>q.removeAttribute('readonly'),{once:true});}
resetFilters();
filter();
"""


def write_dashboard(matches, new_today):
    from html import escape as esc
    new_urls = {r["url"] for r in new_today}
    n_emp = len(set(r["employer"] for r in matches))
    n_remote = sum(1 for r in matches if r["work_mode"] == "Remote")
    n_notax = sum(1 for r in matches if r.get("no_tax_state"))
    n_nontech = sum(1 for r in matches if r.get("role_type") == "Non-technical")
    n_big = sum(1 for r in matches if r.get("big_employer"))
    stat_opts = ["New", "Saved", "Applied", "Interview", "Rejected", "Offer"]
    all_states = sorted({r["state"] for r in matches if r.get("state")})

    rows = []
    for r in matches:
        is_new = r["url"] in new_urls
        score = r["fit_score"]
        fit_cls = "fit-hi" if score >= 8 else ("fit-mid" if score >= 7 else "fit-lo")
        mode = r["work_mode"] or "On-site"
        sal = r["salary"]
        sal_html = (f'<span class="sal mono">{esc(sal)}</span>' if sal.startswith("$")
                    else '<span class="sal-none">Not disclosed</span>')
        days = r.get("days_old")
        posted = (f"{days}d ago" if isinstance(days, int)
                  else (r.get("date_posted") or "")[:10] or "—")
        title = esc(r["title"] or "Untitled")
        emp = esc(r["employer"] or "")
        big = ' <span class="pill-big" title="Large health-informatics employer">★</span>' if r.get("big_employer") else ""
        loc = esc(r["location"] or "—")
        st = r.get("state") or ""
        st_html = (f'<span class="st-chip{" st-notax" if r.get("no_tax_state") else ""}" '
                   f'title="{"No state income tax" if r.get("no_tax_state") else ""}">{esc(st)}</span>'
                   if st else '<span class="sal-none">—</span>')
        role = r.get("role_type") or "Mixed"
        role_html = f'<span class="role role-{esc(role.split()[0].lower())}">{esc(role)}</span>'
        ben = " · ".join(r.get("benefits") or [])
        src = esc(r.get("source_platform") or "")
        url = esc(r["url"], quote=True)
        visa = '<span class="pill-visa">Visa</span>' if r["visa_flag"] else ""
        app = (f'<a href="../{esc(r["app_folder"], quote=True)}/">Bundle</a>'
               if r.get("app_folder") else "")
        search = esc(f"{r['title']} {r['employer']} {r['location']}".lower(), quote=True)
        opts = "".join(f'<option{" selected" if o == r["status"] else ""}>{o}</option>'
                       for o in stat_opts)
        new_tag = '<span class="new-tag">NEW</span>' if is_new else ""
        rows.append(
            f'<tr class="{"is-new" if is_new else ""}" data-search="{search}" '
            f'data-mode="{esc(mode, quote=True)}" data-fit="{score}" data-new="{"1" if is_new else "0"}" '
            f'data-state="{esc(st, quote=True)}" data-notax="{"1" if r.get("no_tax_state") else "0"}" '
            f'data-role="{esc(role, quote=True)}" data-big="{"1" if r.get("big_employer") else "0"}" '
            f'data-days="{days if isinstance(days, int) else 9999}">'
            f'<td class="c-title"><a href="{url}" target="_blank" rel="noopener">{title}</a>{new_tag}'
            f'<span class="src">{src}{(" · " + ben) if ben else ""}</span></td>'
            f'<td class="c-emp">{emp}{big}</td>'
            f'<td class="c-st" data-sort="{esc(st, quote=True)}">{st_html}</td>'
            f'<td class="c-loc">{loc}</td>'
            f'<td>{role_html}</td>'
            f'<td class="c-sal" data-sort="{score}">{sal_html}</td>'
            f'<td><span class="mode mode-{esc(mode.replace(" ", "-"), quote=True)}">{esc(mode)}</span></td>'
            f'<td class="mono" style="color:var(--muted);font-size:12.5px" '
            f'data-sort="{days if isinstance(days, int) else 9999}">{esc(posted)}</td>'
            f'<td data-sort="{score}"><span class="fit {fit_cls}"><b>{score}</b>'
            f'<span class="fit-bar"><i style="width:{min(100, score*10):.0f}%"></i></span></span></td>'
            f'<td>{visa}</td>'
            f'<td><select class="status" data-url="{url}">{opts}</select></td>'
            f'<td><input class="notes" data-url="{url}" placeholder="Add note…" '
            f'aria-label="Note for {title}"></td>'
            f'<td class="c-app">{app}</td>'
            f'</tr>'
        )

    heads = [
        ("Job Title", ""), ("Employer", ""), ("State", ""), ("Location", ""),
        ("Role", ""), ("Salary", ' data-num'), ("Mode", ""), ("Posted", ' data-num'),
        ("Fit", ' data-num'), ("Flags", ' data-nosort'),
        ("Status", ""), ("Notes", ' data-nosort'), ("App", ' data-nosort'),
    ]
    thead = "".join(f'<th{attr}>{esc(label)}<span class="arw"></span></th>' for label, attr in heads)

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Healthcare Job Search</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>{DASH_CSS}</style></head><body>
<div class="app">
<aside class="sidebar" id="sidebar" aria-label="Filters">
  <div class="sidebar-head">Filters</div>
  <div class="sidebar-body" autocomplete="off">
    <div class="presets">
      <button type="button" class="preset" id="pNontech">Non-technical</button>
      <button type="button" class="preset" id="pNotax">No-tax</button>
      <button type="button" class="preset" id="pRemote">Remote</button>
      <button type="button" class="preset" id="pNew">New</button>
    </div>
    <div class="filter-label">State</div>
    <label class="sel"><select id="fState" aria-label="Filter by state"><option value="">All states</option><option value="__notax">No-tax states</option>{''.join(f'<option value="{esc(s, quote=True)}">{esc(s)}</option>' for s in all_states)}</select></label>
    <div class="filter-label">Role type</div>
    <label class="sel"><select id="fRole" aria-label="Filter by role type"><option value="">All roles</option><option>Non-technical</option><option>Mixed</option><option>Technical</option></select></label>
    <div class="filter-label">Posted</div>
    <label class="sel"><select id="fPosted" aria-label="Filter by recency"><option value="9999">Any time</option><option value="7">Last 7 days</option><option value="14">Last 14 days</option><option value="30">Last 30 days</option></select></label>
    <div class="filter-label">Work mode</div>
    <label class="sel"><select id="fMode" aria-label="Filter by work mode"><option value="">All modes</option><option>Remote</option><option>Hybrid</option><option>On-site</option></select></label>
    <div class="filter-label">Status</div>
    <label class="sel"><select id="fStatus" aria-label="Filter by status"><option value="">All statuses</option>{''.join(f'<option>{o}</option>' for o in stat_opts)}</select></label>
    <div class="filter-label">Minimum fit</div>
    <label class="sel"><select id="fFit" aria-label="Filter by minimum fit"><option value="0">Any fit</option><option value="6">6+</option><option value="7">7+</option><option value="8">8+</option><option value="9">9+</option></select></label>
    <label class="toggle"><input id="tNew" type="checkbox">New this run only</label>
    <label class="toggle"><input id="tBig" type="checkbox">Large employers</label>
    <button type="button" class="preset" id="clearFilters" style="margin-top:6px;width:100%;border-radius:8px">Clear all filters</button>
  </div>
</aside>
<main class="main">
<header class="topbar">
  <div class="brandrow">
    <div class="brand">
      <h1>Healthcare Job<span class="mark">.</span>Search</h1>
      <span class="meta">Direct from {n_emp} employer career pages · no job boards</span>
    </div>
    <span class="updated">Updated {date.today().isoformat()}</span>
  </div>
  <div class="kpis">
    <div class="kpi accent"><b>{len(matches)}</b><span>Matches</span></div>
    <div class="kpi"><b>{len(new_today)}</b><span>New this run</span></div>
    <div class="kpi"><b>{n_nontech}</b><span>Non-technical</span></div>
    <div class="kpi"><b>{n_notax}</b><span>No-tax states</span></div>
    <div class="kpi"><b>{n_big}</b><span>Large employers</span></div>
    <div class="kpi"><b>{n_remote}</b><span>Remote</span></div>
  </div>
</header>
<div class="toolbar">
  <button type="button" class="filter-toggle" id="filterToggle" aria-label="Open filters">Filters</button>
  <div class="search">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" type="search" name="job-q" placeholder="Search title, employer, location…" aria-label="Search jobs" autocomplete="off" autocorrect="off" spellcheck="false">
    <kbd>/</kbd>
  </div>
  <div class="count" id="count"><b>{len(matches)}</b> of {len(matches)}</div>
  <div class="chips" id="chips" aria-label="Active filters"></div>
</div>
<section class="table-panel">
  <div class="table-note" id="tableNote"><b>{len(matches)}</b> matched roles loaded — scroll the table below or use filters to narrow results.</div>
  <div class="table-scroll">
  <table>
    <thead><tr>{thead}</tr></thead>
    <tbody id="tb">{chr(10).join(rows)}</tbody>
  </table>
  </div>
  <div class="empty" id="empty"><b>No matches for these filters</b>Try clearing filters or lowering the fit threshold.</div>
</section>
</main>
</div>
<div class="backdrop" id="backdrop" aria-hidden="true"></div>
<script>{DASH_JS}</script>
</body></html>"""
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text(html)


if __name__ == "__main__":
    main()
