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

    print(f"Scored {len(raw)} raw jobs")
    print(f"Matches (score>={PROFILE['filters']['min_fit_score']}, filters pass): {len(matches)}")
    print(f"New or updated this run: {len(new_today)}")
    print(f"Dashboard: {DASH}")
    return matches, new_today


DASH_CSS = """
:root{
  --bg:#f6f7f9; --surface:#ffffff; --ink:#14171c; --text:#3c434f; --muted:#6b7280;
  --line:#e6e8ec; --line-soft:#eef0f3; --header:#15181e; --header-2:#1c2026;
  --header-ink:#eef0f3; --header-muted:#9aa3b0;
  --accent:#0d7c6c; --accent-ink:#0a655a; --accent-soft:#e6f2ef;
  --hi:#0a7a4d; --mid:#a9760f; --lo:#7a828f;
  --ease:cubic-bezier(0.23,1,0.32,1);
  --z-thead:20; --z-toolbar:25; --z-header:30;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased;
  font-feature-settings:"cv01","cv03","ss01";
}
.mono{font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums; letter-spacing:-0.01em}

/* ---- header ---- */
header{
  position:sticky; top:0; z-index:var(--z-header);
  background:linear-gradient(180deg,var(--header),var(--header-2));
  color:var(--header-ink); padding:20px 28px 16px;
  border-bottom:1px solid #000;
}
.brandrow{display:flex; align-items:baseline; gap:12px; flex-wrap:wrap}
header h1{margin:0; font-size:19px; font-weight:600; letter-spacing:-0.02em; color:#fff}
header h1 .dot{color:var(--accent)}
.meta{color:var(--header-muted); font-size:12.5px}
.stats{display:flex; gap:8px; margin-top:14px; flex-wrap:wrap}
.stat{
  display:flex; flex-direction:column; gap:1px; padding:7px 13px;
  background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08);
  border-radius:9px; min-width:78px;
}
.stat b{font-size:18px; font-weight:600; color:#fff; letter-spacing:-0.02em}
.stat span{font-size:11px; color:var(--header-muted)}
.stat.accent b{color:#3fd9bf}

/* ---- toolbar ---- */
.toolbar{
  position:sticky; top:0; z-index:var(--z-toolbar);
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:12px 28px; background:rgba(246,247,249,.92);
  backdrop-filter:saturate(1.1) blur(8px); border-bottom:1px solid var(--line);
}
.search{flex:1 1 280px; position:relative; min-width:220px}
.search input{
  width:100%; padding:9px 12px 9px 34px; font-size:13.5px; color:var(--ink);
  background:var(--surface); border:1px solid var(--line); border-radius:9px;
  transition:border-color 140ms var(--ease), box-shadow 140ms var(--ease);
}
.search input::placeholder{color:#9aa1ab}
.search input:focus{outline:none; border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft)}
.search svg{position:absolute; left:11px; top:50%; transform:translateY(-50%);
  width:15px; height:15px; color:#9aa1ab; pointer-events:none}
.filters{display:flex; gap:8px; flex-wrap:wrap; align-items:center}
.sel{position:relative}
.sel select, .chk{
  appearance:none; font:inherit; font-size:13px; color:var(--ink);
  background:var(--surface); border:1px solid var(--line); border-radius:9px;
  padding:8px 30px 8px 12px; cursor:pointer;
  transition:border-color 140ms var(--ease), box-shadow 140ms var(--ease);
}
.sel::after{content:""; position:absolute; right:12px; top:50%; width:7px; height:7px;
  border-right:1.6px solid #9aa1ab; border-bottom:1.6px solid #9aa1ab;
  transform:translateY(-65%) rotate(45deg); pointer-events:none}
.sel select:focus{outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft)}
.toggle{display:inline-flex; align-items:center; gap:7px; font-size:13px; color:var(--text);
  padding:8px 12px; background:var(--surface); border:1px solid var(--line);
  border-radius:9px; cursor:pointer; user-select:none;
  transition:border-color 140ms var(--ease), background 140ms var(--ease)}
.toggle input{accent-color:var(--accent); width:15px; height:15px; cursor:pointer}
.toggle.on{border-color:var(--accent); background:var(--accent-soft); color:var(--accent-ink)}
.count{margin-left:auto; font-size:12.5px; color:var(--muted); white-space:nowrap}
.count b{color:var(--ink); font-weight:600}

/* ---- table ---- */
.wrap{padding:0 16px 60px}
table{width:100%; border-collapse:separate; border-spacing:0; background:var(--surface);
  border:1px solid var(--line); border-radius:14px; overflow:hidden;
  box-shadow:0 1px 2px rgba(20,23,28,.04), 0 8px 24px -16px rgba(20,23,28,.18)}
thead th{
  position:sticky; top:57px; z-index:var(--z-thead);
  background:#fbfcfd; color:var(--muted); font-weight:600; font-size:11px;
  letter-spacing:0.04em; text-transform:uppercase; text-align:left;
  padding:11px 14px; border-bottom:1px solid var(--line); cursor:pointer;
  white-space:nowrap; transition:color 120ms var(--ease)}
thead th:hover{color:var(--ink)}
thead th .arw{opacity:0; margin-left:4px; font-size:9px; transition:opacity 120ms var(--ease)}
thead th[data-dir] .arw{opacity:1}
tbody td{padding:11px 14px; border-bottom:1px solid var(--line-soft); vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr{transition:background-color 130ms var(--ease)}
@media (hover:hover){tbody tr:hover{background:#fafbfc}}
tr.is-new td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
.c-title a{color:var(--ink); font-weight:550; text-decoration:none; letter-spacing:-0.01em}
.c-title a:hover{color:var(--accent-ink); text-decoration:underline; text-underline-offset:2px}
.c-title .src{display:block; font-size:11px; color:var(--muted); margin-top:2px}
.new-tag{display:inline-block; margin-left:7px; font-size:10px; font-weight:600;
  color:var(--accent-ink); background:var(--accent-soft); padding:1px 6px; border-radius:999px;
  vertical-align:middle; letter-spacing:0.02em}
.c-emp{color:var(--text); font-weight:500}
.c-loc{color:var(--muted); font-size:13px}
.sal{color:var(--ink); font-weight:550} .sal-none{color:#aab0b9; font-weight:400}
.mode{font-size:12px; font-weight:550; padding:3px 9px; border-radius:999px; white-space:nowrap}
.mode-Remote{color:#0a655a; background:#e3f2ef}
.mode-Hybrid{color:#7a5a00; background:#f6efda}
.mode-On-site{color:#52585f; background:#eef0f3}
.fit{display:inline-flex; flex-direction:column; gap:3px; width:46px}
.fit b{font-size:13.5px; font-weight:650; font-family:'JetBrains Mono',monospace;
  font-variant-numeric:tabular-nums}
.fit i{height:3px; border-radius:2px; background:currentColor; opacity:.85}
.fit-hi{color:var(--hi)} .fit-mid{color:var(--mid)} .fit-lo{color:var(--lo)}
.pill-visa{font-size:11px; font-weight:600; color:#9a5800; background:#fbf0dc;
  padding:2px 8px; border-radius:999px}
.pill-big{color:#b8860b; font-size:13px; cursor:help}
.st-chip{display:inline-block; font-family:'JetBrains Mono',monospace; font-size:12px;
  font-weight:600; letter-spacing:0.02em; color:#52585f; background:#eef0f3;
  padding:2px 7px; border-radius:6px}
.st-chip.st-notax{color:#0a655a; background:#e3f2ef}
.role{font-size:12px; font-weight:550; padding:3px 9px; border-radius:999px; white-space:nowrap}
.role-non-technical,.role-non{color:#0a655a; background:#e3f2ef}
.role-technical{color:#52585f; background:#eef0f3}
.role-mixed{color:#7a5a00; background:#f6efda}
select.status{appearance:none; font:inherit; font-size:12.5px; font-weight:550;
  padding:5px 24px 5px 10px; border-radius:8px; border:1px solid transparent;
  cursor:pointer; background-position:right 7px center; background-repeat:no-repeat;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 8 8'%3E%3Cpath d='M1 2l3 3 3-3' stroke='%237a828f' stroke-width='1.4' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
  transition:border-color 130ms var(--ease), box-shadow 130ms var(--ease)}
select.status:focus{outline:none; box-shadow:0 0 0 3px var(--accent-soft)}
.st-New{color:#0a655a; background:#e3f2ef} .st-Saved{color:#1d4ed8; background:#e7edfd}
.st-Applied{color:#5b21b6; background:#efe7fb} .st-Interview{color:#9a5800; background:#fbf0dc}
.st-Rejected{color:#9f1239; background:#fbe3ea} .st-Offer{color:#0a7a4d; background:#e1f4ea}
input.notes{width:100%; min-width:130px; font:inherit; font-size:12.5px; color:var(--ink);
  background:transparent; border:1px solid transparent; border-radius:7px; padding:5px 8px;
  transition:border-color 130ms var(--ease), background 130ms var(--ease)}
input.notes::placeholder{color:#b6bcc4}
input.notes:hover{background:#f4f5f7}
input.notes:focus{outline:none; background:var(--surface); border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-soft)}
.c-app a{display:inline-flex; align-items:center; gap:3px; font-size:12px; font-weight:550;
  color:var(--accent-ink); text-decoration:none; white-space:nowrap}
.c-app a:hover{text-decoration:underline; text-underline-offset:2px}
.empty{display:none; padding:60px 20px; text-align:center; color:var(--muted)}
.empty.show{display:block}
@media (prefers-reduced-motion:reduce){*{transition:none!important; animation:none!important}}
@media (max-width:760px){
  header,.toolbar{padding-left:14px; padding-right:14px}
  .count{margin-left:0; width:100%}
  thead th{top:0}
}
"""

DASH_JS = """
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const tb=$('#tb'), rows=$$('#tb tr');
const ST_KEY='jobsearch_status', NT_KEY='jobsearch_notes';
const stStore=JSON.parse(localStorage.getItem(ST_KEY)||'{}');
const ntStore=JSON.parse(localStorage.getItem(NT_KEY)||'{}');

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
function filter(){
  const term=q.value.trim().toLowerCase(), state=fState.value, role=fRole.value,
        maxDays=parseInt(fPosted.value)||9999, mode=fMode.value, st=fStatus.value,
        fit=parseFloat(fFit.value)||0, onlyNew=tNew.checked, onlyBig=tBig.checked;
  let shown=0;
  rows.forEach(r=>{
    let stateOk = !state || (state==='__notax' ? r.dataset.notax==='1' : r.dataset.state===state);
    let ok = (!term || r.dataset.search.includes(term))
      && stateOk
      && (!role || r.dataset.role===role)
      && (parseInt(r.dataset.days)<=maxDays)
      && (!mode || r.dataset.mode===mode)
      && (!st || r.dataset.status===st)
      && (parseFloat(r.dataset.fit)>=fit)
      && (!onlyNew || r.dataset.new==='1')
      && (!onlyBig || r.dataset.big==='1');
    r.hidden=!ok; if(ok) shown++;
  });
  count.innerHTML='<b>'+shown+'</b> of '+rows.length;
  $('#empty').classList.toggle('show', shown===0);
  [tNew,tBig].forEach(t=>t.closest('.toggle').classList.toggle('on',t.checked));
}
[q,fState,fRole,fPosted,fMode,fStatus,fFit].forEach(e=>e.addEventListener('input',filter));
[tNew,tBig].forEach(e=>e.addEventListener('change',filter));

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
            f'<i style="width:{min(100, score*10):.0f}%"></i></span></td>'
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>{DASH_CSS}</style></head><body>
<header>
  <div class="brandrow">
    <h1>Healthcare Job Search<span class="dot">.</span></h1>
    <span class="meta">Direct from {n_emp} employer career pages · no job boards · updated {date.today().isoformat()}</span>
  </div>
  <div class="stats">
    <div class="stat accent"><b>{len(matches)}</b><span>Matches</span></div>
    <div class="stat"><b>{len(new_today)}</b><span>New this run</span></div>
    <div class="stat"><b>{n_nontech}</b><span>Non-technical</span></div>
    <div class="stat"><b>{n_notax}</b><span>No-tax states</span></div>
    <div class="stat"><b>{n_big}</b><span>Large employers</span></div>
    <div class="stat"><b>{n_remote}</b><span>Remote</span></div>
    <div class="stat"><b>{n_emp}</b><span>Employers</span></div>
  </div>
</header>
<div class="toolbar">
  <div class="search">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id="q" type="search" placeholder="Search title, employer, location…" aria-label="Search jobs">
  </div>
  <div class="filters">
    <label class="sel"><select id="fState" aria-label="Filter by state"><option value="">All states</option><option value="__notax">No-tax states ★</option>{''.join(f'<option value="{esc(s, quote=True)}">{esc(s)}</option>' for s in all_states)}</select></label>
    <label class="sel"><select id="fRole" aria-label="Filter by role type"><option value="">All roles</option><option>Non-technical</option><option>Mixed</option><option>Technical</option></select></label>
    <label class="sel"><select id="fPosted" aria-label="Filter by recency"><option value="9999">Any time</option><option value="7">≤ 7 days</option><option value="14">≤ 14 days</option><option value="30">≤ 30 days</option></select></label>
    <label class="sel"><select id="fMode" aria-label="Filter by work mode"><option value="">All modes</option><option>Remote</option><option>Hybrid</option><option>On-site</option></select></label>
    <label class="sel"><select id="fStatus" aria-label="Filter by status"><option value="">All statuses</option>{''.join(f'<option>{o}</option>' for o in stat_opts)}</select></label>
    <label class="sel"><select id="fFit" aria-label="Filter by minimum fit"><option value="0">Any fit</option><option value="6">6+</option><option value="7">7+</option><option value="8">8+</option><option value="9">9+</option></select></label>
    <label class="toggle"><input id="tNew" type="checkbox">New only</label>
    <label class="toggle"><input id="tBig" type="checkbox">Large employers</label>
  </div>
  <div class="count" id="count"><b>{len(matches)}</b> of {len(matches)}</div>
</div>
<div class="wrap">
  <table>
    <thead><tr>{thead}</tr></thead>
    <tbody id="tb">{''.join(rows)}</tbody>
  </table>
  <div class="empty" id="empty">No matches for these filters. Try clearing the search or lowering the fit threshold.</div>
</div>
<script>{DASH_JS}</script>
</body></html>"""
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text(html)


if __name__ == "__main__":
    main()
