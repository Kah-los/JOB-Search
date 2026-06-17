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
    DOCS_SEG_PATH, DOCS_SEG_DEFAULT,
)
from europe.score import score_job, days_old, title_relevant


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


EU_CSS = """
:root{--bg:#f0f4f8;--surface:#fff;--ink:#0f172a;--text:#1e293b;--muted:#64748b;
--line:#dbe3ec;--primary:#1d4ed8;--primary-soft:#dbeafe;--hi:#047857;--hi-soft:#d1fae5;
--mid:#b45309;--mid-soft:#fef3c7;--lo:#94a3b8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:'Fira Sans',system-ui,sans-serif;font-size:14px;line-height:1.5}
a{color:var(--primary)}.wrap{max-width:1280px;margin:0 auto;padding:20px}
.top{background:linear-gradient(135deg,#1e3a5f,#1d4ed8);color:#fff;padding:24px 28px;border-radius:14px;margin-bottom:18px}
.top h1{margin:0 0 6px;font-size:24px}.top p{margin:0;opacity:.9;font-size:13px}
.nav{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.nav a{font-size:13px;padding:6px 12px;background:var(--surface);border:1px solid var(--line);
border-radius:8px;text-decoration:none;color:var(--ink);font-weight:500}
.nav a.on{background:var(--primary-soft);border-color:var(--primary);color:#1e40af}
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
const rows=$$('#tb tr'), q=$('#q'), fCountry=$('#fCountry'), fLang=$('#fLang'), fMode=$('#fMode');
function filter(){
  const term=(q?.value||'').toLowerCase(), c=fCountry?.value||'', lg=fLang?.value||'', md=fMode?.value||'';
  let n=0;
  rows.forEach(r=>{
    const ok=(!term||r.dataset.search.includes(term))&&(!c||r.dataset.country===c)
      &&(!lg||r.dataset.lang===lg)&&(!md||r.dataset.mode===md);
    r.classList.toggle('row-out',!ok); if(ok) n++;
  });
  $('#count').textContent=n+' of '+rows.length;
}
[q,fCountry,fLang,fMode].forEach(e=>e?.addEventListener('input',filter));
filter();
"""

ROW_OUT = "tbody tr.row-out{display:none}"


def write_dashboard(matches, new_today):
    new_urls = {r["url"] for r in new_today}
    countries = sorted({r.get("country") for r in matches if r.get("country")})
    n_english_high = sum(1 for r in matches if r.get("english_priority") == "high")
    n_remote = sum(1 for r in matches if "remote" in (r.get("work_mode") or "").lower())
    us_link = "../5b49cmxred/" if (ROOT / "docs" / "5b49cmxred").exists() else "#"

    rows = []
    for r in matches:
        is_new = r["url"] in new_urls
        pri = r.get("english_priority", "medium")
        pill_cls = {"high": "pill-high", "medium": "pill-medium", "low": "pill-low"}.get(pri, "pill-medium")
        langs = esc(r.get("languages_display") or "—")
        search = esc(f"{r['title']} {r['employer']} {r.get('country','')} {r.get('city','')}".lower())
        rows.append(
            f'<tr data-search="{search}" data-country="{esc(r.get("country") or "")}" '
            f'data-lang="{esc(pri)}" data-mode="{esc(r.get("work_mode") or "")}">'
            f'<td class="c-title"><a href="{esc(r["url"], quote=True)}" target="_blank" rel="noopener">'
            f'{esc(r["title"] or "Untitled")}</a>'
            f'{"<span class=\"pill pill-high\" style=\"margin-left:6px\">NEW</span>" if is_new else ""}'
            f'<div class="src">{esc(r.get("source_platform") or "")}</div></td>'
            f'<td>{esc(r.get("employer") or "")}</td>'
            f'<td>{esc((r.get("city") or "") + (", " if r.get("city") and r.get("country") else "") + (r.get("country") or ""))}</td>'
            f'<td>{esc(r.get("experience_level") or "—")}</td>'
            f'<td>{esc(r.get("work_mode") or "—")}</td>'
            f'<td>{esc(r.get("date_posted") or "—")}</td>'
            f'<td>{langs}<br><span class="pill {pill_cls}">{esc(r.get("english_flag") or pri)}</span></td>'
            f'<td class="c-desc">{esc(r.get("summary") or "")}</td></tr>'
        )

    country_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in countries)
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Europe Jobs — Health Informatics</title>
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>{EU_CSS}{ROW_OUT}</style></head><body>
<div class="wrap">
<nav class="nav">
  <a href="{esc(us_link)}">🇺🇸 U.S. Jobs</a>
  <a href="#" class="on">🌍 Europe Jobs</a>
</nav>
<div class="top">
  <h1>Europe Jobs</h1>
  <p>Health informatics &amp; healthcare IT — EU/EEA, UK, Switzerland. English-friendly roles ranked first. Direct employer links only.</p>
  <div class="kpis">
    <div class="kpi"><b>{len(matches)}</b><span>Matches</span></div>
    <div class="kpi"><b>{len(new_today)}</b><span>New this run</span></div>
    <div class="kpi"><b>{n_english_high}</b><span>English-friendly</span></div>
    <div class="kpi"><b>{n_remote}</b><span>Remote</span></div>
  </div>
  <p style="margin-top:12px;font-size:11px;opacity:.75">Updated {date.today().isoformat()} · Sources: Arbetsförmedlingen, EURES, employer career pages</p>
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
  <span class="count" id="count">{len(matches)} of {len(matches)}</span>
</div>
<table><thead><tr>
  <th>Job Title</th><th>Company</th><th>Country + City</th><th>Experience</th>
  <th>Mode</th><th>Posted</th><th>Language Requirements</th><th>Description</th>
</tr></thead><tbody id="tb">{"".join(rows)}</tbody></table>
<p class="empty" id="empty" style="display:none">No matches for these filters.</p>
</div>
<script>{EU_JS}</script></body></html>"""
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
        if not title_relevant(job.get("title", "")):
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
            "first_seen": prev.get("first_seen") if prev else today,
            "last_seen": today,
            "updated": is_new or is_updated,
            "reasons": scored["reasons"],
        }
        matches.append(rec)
        seen[url] = {"fingerprint": fp, "first_seen": rec["first_seen"], "last_seen": today}
        if is_new or is_updated:
            new_today.append(rec)

    # Sort: English-friendly first, then language score, then recency
    tier_order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda r: (
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
