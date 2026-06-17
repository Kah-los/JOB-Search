#!/usr/bin/env python3
"""
Europe Jobs orchestrator: score → filter → dashboard.
Fully separate from U.S. pipeline. Sorts English-friendly roles first.
"""
import json
import hashlib
import sys
from datetime import date
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

from europe.config import (
    DATA, JOBS_RAW, MATCHES, NEW_TODAY, SEEN, PROFILE_PATH, DASH,
    DOCS_SEG_PATH, DOCS_SEG_DEFAULT, ALL_TARGET_TITLES,
)
from europe.score import score_job, days_old, title_relevant
from dashboard_nav import SITE_NAV_CSS, site_nav_html, site_nav_js


def job_fingerprint(job):
    h = hashlib.sha1()
    h.update((job.get("title", "") + "|" + (job.get("description", "")[:500])).encode())
    return h.hexdigest()[:12]


def load_json(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def publish_dashboard():
    seg = DOCS_SEG_PATH.read_text().strip() if DOCS_SEG_PATH.exists() else DOCS_SEG_DEFAULT
    dest_dir = ROOT / "docs" / seg
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "index.html"
    if DASH.exists():
        dest.write_text(DASH.read_text())
    return dest


EU_CSS = SITE_NAV_CSS + """
:root{--bg:#f0f4f8;--surface:#fff;--ink:#0f172a;--text:#1e293b;--muted:#64748b;
--line:#dbe3ec;--primary:#1d4ed8;--primary-soft:#dbeafe;--hi:#047857;--hi-soft:#d1fae5;
--mid:#b45309;--mid-soft:#fef3c7;--lo:#94a3b8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:'Fira Sans',system-ui,sans-serif;font-size:14px;line-height:1.5}
a{color:var(--primary)}.wrap{max-width:1280px;margin:0 auto;padding:20px}
.top{background:linear-gradient(135deg,#1e3a5f,#1d4ed8);color:#fff;padding:24px 28px;border-radius:14px;margin-bottom:18px}
.top h1{margin:0 0 6px;font-size:24px}.top p{margin:0;opacity:.9;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:16px 0}
.kpi{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);border-radius:10px;padding:12px}
.kpi b{display:block;font-size:22px}.kpi span{font-size:11px;opacity:.85}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.toolbar input,.toolbar select{padding:9px 12px;border:1px solid var(--line);border-radius:8px;font:inherit}
.toolbar input{flex:1;min-width:200px}.count{margin-left:auto;font-size:13px;color:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden}
thead th{background:#f8fafc;color:var(--muted);font-size:11px;text-transform:uppercase;
letter-spacing:.05em;text-align:left;padding:10px 12px;border-bottom:1px solid var(--line)}
tbody td{padding:10px 12px;border-bottom:1px solid #eef2f6;vertical-align:top}
tbody tr:hover{background:#f8fafc}
.c-title{font-weight:600;max-width:260px}.c-desc{font-size:12.5px;color:var(--muted);max-width:320px}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px}
.pill-high{color:var(--hi);background:var(--hi-soft)}
.pill-medium{color:var(--mid);background:var(--mid-soft)}
.pill-low{color:var(--muted);background:#f1f5f9}
.src{font-size:11px;color:var(--muted)}
.empty{padding:40px;text-align:center;color:var(--muted)}
"""

EU_JS = """
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const rows=$$('#tb tr'), q=$('#q'), fCountry=$('#fCountry'), fLang=$('#fLang'), fMode=$('#fMode'),
  fEmp=$('#fEmp'), fForeigner=$('#fForeigner');
function filter(){
  const term=(q?.value||'').toLowerCase(), c=fCountry?.value||'', lg=fLang?.value||'', md=fMode?.value||'',
    emp=fEmp?.value||'', fr=fForeigner?.value||'';
  let n=0;
  rows.forEach(r=>{
    const ok=(!term||r.dataset.search.includes(term))&&(!c||r.dataset.country===c)
      &&(!lg||r.dataset.lang===lg)&&(!md||r.dataset.mode===md)
      &&(!emp||r.dataset.emp===emp)&&(!fr||r.dataset.foreigner===fr);
    r.classList.toggle('row-out',!ok); if(ok) n++;
  });
  $('#count').textContent=n+' of '+rows.length;
}
[q,fCountry,fLang,fMode,fEmp,fForeigner].forEach(e=>e?.addEventListener('input',filter));
filter();
"""

ROW_OUT = "tbody tr.row-out{display:none}"


def write_dashboard(matches, new_today):
    new_urls = {r["url"] for r in new_today}
    countries = sorted({r.get("country") for r in matches if r.get("country")})
    n_english_high = sum(1 for r in matches if r.get("english_priority") == "high")
    n_remote = sum(1 for r in matches if "remote" in (r.get("work_mode") or "").lower())
    n_startup = sum(1 for r in matches if r.get("employer_type") in ("startup", "scaleup", "private", "consulting"))
    n_foreigner = sum(1 for r in matches if r.get("foreigner_tier") == "high")
    rows = []
    for r in matches:
        is_new = r["url"] in new_urls
        pri = r.get("english_priority", "medium")
        pill_cls = {"high": "pill-high", "medium": "pill-medium", "low": "pill-low"}.get(pri, "pill-medium")
        langs = esc(r.get("languages_display") or "—")
        emp_type = r.get("employer_type") or "unknown"
        f_tier = r.get("foreigner_tier") or "low"
        emp_pill = {
            "startup": "pill-high", "scaleup": "pill-high", "private": "pill-medium",
            "consulting": "pill-medium", "public_sector": "pill-low", "hospital": "pill-low",
        }.get(emp_type, "pill-medium")
        f_pill = {"high": "pill-high", "medium": "pill-medium", "low": "pill-low"}.get(f_tier, "pill-low")
        startup_badge = '<span class="pill pill-high" style="margin-left:4px">startup</span>' if r.get("startup_match") else ""
        search = esc(f"{r['title']} {r['employer']} {r.get('country','')} {r.get('city','')} {emp_type}".lower())
        rows.append(
            f'<tr data-search="{search}" data-country="{esc(r.get("country") or "")}" '
            f'data-lang="{esc(pri)}" data-mode="{esc(r.get("work_mode") or "")}" '
            f'data-emp="{esc(emp_type)}" data-foreigner="{esc(f_tier)}">'
            f'<td class="c-title"><a href="{esc(r["url"], quote=True)}" target="_blank" rel="noopener">'
            f'{esc(r["title"] or "Untitled")}</a>'
            f'{"<span class=\"pill pill-high\" style=\"margin-left:6px\">NEW</span>" if is_new else ""}'
            f'<div class="src">{esc(r.get("source_platform") or "")}</div></td>'
            f'<td>{esc(r.get("employer") or "")}'
            f'<br><span class="pill {emp_pill}">{esc(emp_type.replace("_", " "))}</span>'
            f'{startup_badge}'
            f'</td>'
            f'<td>{esc((r.get("city") or "") + (", " if r.get("city") and r.get("country") else "") + (r.get("country") or ""))}</td>'
            f'<td>{esc(r.get("experience_level") or "—")}</td>'
            f'<td>{esc(r.get("work_mode") or "—")}</td>'
            f'<td>{esc(r.get("date_posted") or "—")}</td>'
            f'<td>{langs}<br><span class="pill {pill_cls}">{esc(r.get("english_flag") or pri)}</span>'
            f'<br><span class="pill {f_pill}">foreigner: {esc(f_tier)}</span></td>'
            f'<td class="c-desc">{esc(r.get("summary") or "")}</td></tr>'
        )

    country_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in countries)
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Europe Jobs — {len(matches)} matches · Health Informatics</title>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>{EU_CSS}{ROW_OUT}</style></head><body>
{site_nav_html("europe")}
<div class="wrap">
<div class="top">
  <h1>Europe Jobs</h1>
  <p>Health informatics &amp; healthcare IT — EU/EEA, UK, Switzerland. Ranked by fit to your CV and target titles (all employer types). Sources: Arbetsförmedlingen, EURES, Jobindex.dk, Finn.no, Jobbsafari, StepStone, FlexJobs, LinkedIn, EU employer seed list.</p>
  <div class="kpis">
    <div class="kpi"><b>{len(matches)}</b><span>Matches</span></div>
    <div class="kpi"><b>{len(new_today)}</b><span>New this run</span></div>
    <div class="kpi"><b>{n_english_high}</b><span>English-friendly</span></div>
    <div class="kpi"><b>{n_remote}</b><span>Remote</span></div>
    <div class="kpi"><b>{n_startup}</b><span>Private/startup</span></div>
    <div class="kpi"><b>{n_foreigner}</b><span>Foreigner-friendly</span></div>
  </div>
  <p style="margin-top:12px;font-size:11px;opacity:.75">Updated {date.today().isoformat()} · {len(ALL_TARGET_TITLES)} target titles · Sources: Jobtech, EURES, Jobindex, Finn, Jobbsafari, StepStone, FlexJobs, LinkedIn, employers</p>
</div>
<div class="toolbar">
  <input id="q" type="search" placeholder="Search title, company, country…" autocomplete="off">
  <select id="fCountry"><option value="">All countries</option>{country_opts}</select>
  <select id="fLang"><option value="">All language tiers</option>
    <option value="high">English-friendly (high)</option>
    <option value="medium">Medium</option>
    <option value="low">Local language focus</option></select>
  <select id="fMode"><option value="">All modes</option>
    <option>Remote</option><option>Hybrid</option><option>On-site</option></select>
  <select id="fEmp"><option value="">All employers</option>
    <option value="startup">Startup</option><option value="scaleup">Scale-up</option>
    <option value="private">Private</option><option value="consulting">Consulting</option>
    <option value="public_sector">Public sector</option><option value="hospital">Hospital</option></select>
  <select id="fForeigner"><option value="">All mobility tiers</option>
    <option value="high">Foreigner-friendly (high)</option>
    <option value="medium">Medium</option><option value="low">Local focus</option></select>
  <span class="count" id="count">{len(matches)} of {len(matches)}</span>
</div>
<table><thead><tr>
  <th>Job Title</th><th>Company</th><th>Country + City</th><th>Experience</th>
  <th>Mode</th><th>Posted</th><th>Language Requirements</th><th>Description</th>
</tr></thead><tbody id="tb">{"".join(rows)}</tbody></table>
<p class="empty" id="empty" style="display:none">No matches for these filters.</p>
</div>
<script>{EU_JS}{site_nav_js()}</script></body></html>"""
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text(html)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    profile = load_json(PROFILE_PATH, {})
    raw = load_json(JOBS_RAW, [])
    seen = load_json(SEEN, {})
    prev_matches = {m["url"]: m for m in load_json(MATCHES, [])}
    today = date.today().isoformat()
    max_days = profile.get("filters", {}).get("max_days_old", 60)
    min_fit = profile.get("filters", {}).get("min_fit_score", 4)

    matches, new_today = [], []
    for job in raw:
        if not title_relevant(job.get("title", ""), job.get("description", "")):
            continue
        days = days_old(job)
        if days is not None and days > max_days:
            continue
        scored = score_job(job, profile)
        if not scored["passes_filters"] or scored["fit_score"] < min_fit:
            continue
        url = job["url"]
        fp = job_fingerprint(job)
        prev = seen.get(url)
        is_new = prev is None
        is_updated = prev and prev.get("fingerprint") != fp
        fl = scored["flags"]
        rec = {
            "title": job.get("title"),
            "employer": job.get("employer"),
            "country": fl.get("country") or job.get("country"),
            "city": fl.get("city") or job.get("city"),
            "location": job.get("location"),
            "url": url,
            "experience_level": fl.get("experience_level"),
            "work_mode": fl.get("work_mode"),
            "date_posted": job.get("date_posted"),
            "languages_display": ", ".join(fl.get("languages") or []),
            "english_priority": fl.get("english_priority"),
            "english_flag": fl.get("english_flag"),
            "language_score": fl.get("language_score"),
            "summary": fl.get("summary"),
            "fit_score": scored["fit_score"],
            "priority": scored["priority"],
            "source_platform": job.get("source_platform"),
            "source_board": job.get("source_board"),
            "employer_type": fl.get("employer_type"),
            "foreigner_tier": fl.get("foreigner_tier"),
            "foreigner_score": fl.get("foreigner_score"),
            "startup_match": fl.get("startup_match"),
            "startup_name": fl.get("startup_name"),
            "first_seen": prev.get("first_seen") if prev else today,
            "last_seen": today,
            "updated": is_new or is_updated,
            "reasons": scored["reasons"],
        }
        matches.append(rec)
        seen[url] = {"fingerprint": fp, "first_seen": rec["first_seen"], "last_seen": today}
        if is_new or is_updated:
            new_today.append(rec)

    # Sort: best CV/title fit first, then English-friendly, then overall priority
    tier_order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda r: (
        -(r.get("fit_score") or 0),
        tier_order.get(r.get("english_priority"), 9),
        -(r.get("language_score") or 0),
        -(r.get("priority") or 0),
    ))

    MATCHES.write_text(json.dumps(matches, indent=2))
    NEW_TODAY.write_text(json.dumps(new_today, indent=2))
    SEEN.write_text(json.dumps(seen, indent=2))
    write_dashboard(matches, new_today)
    published = publish_dashboard()

    print(f"Scored {len(raw)} Europe jobs")
    print(f"Matches (fit>={min_fit}, filters pass): {len(matches)}")
    print(f"New or updated: {len(new_today)}")
    print(f"Dashboard: {DASH}")
    if published:
        print(f"Published: {published}")


if __name__ == "__main__":
    main()
