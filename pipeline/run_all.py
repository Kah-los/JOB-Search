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

        rec = {
            "title": job.get("title"), "employer": job.get("employer"),
            "location": job.get("location") or job.get("employer_state"),
            "salary": (f"${scored['flags']['salary_usd_max']:,}"
                       if scored["flags"]["salary_usd_max"] else "Salary Not Disclosed"),
            "work_mode": scored["flags"]["remote_type"],
            "date_posted": job.get("date_posted") or "",
            "fit_score": scored["fit_score"],
            "visa_flag": "⚑ Visa mentioned" if scored["flags"]["visa_sponsorship_mentioned"] else "",
            "onsite_flag": "On-site" if scored["flags"]["onsite"] else "",
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

    matches.sort(key=lambda r: r["fit_score"], reverse=True)
    MATCHES.write_text(json.dumps(matches, indent=2))
    NEW_TODAY.write_text(json.dumps(new_today, indent=2))
    SEEN.write_text(json.dumps(seen, indent=2))
    write_dashboard(matches, new_today)

    print(f"Scored {len(raw)} raw jobs")
    print(f"Matches (score>={PROFILE['filters']['min_fit_score']}, filters pass): {len(matches)}")
    print(f"New or updated this run: {len(new_today)}")
    print(f"Dashboard: {DASH}")
    return matches, new_today


def write_dashboard(matches, new_today):
    new_urls = {r["url"] for r in new_today}
    rows = []
    for r in matches:
        cls = "new" if r["url"] in new_urls else ""
        flags = " ".join(f for f in [r["visa_flag"], r["onsite_flag"]] if f)
        score = r["fit_score"]
        sc_cls = "hi" if score >= 8 else ("mid" if score >= 7 else "lo")
        folder = (f'<a href="../{r["app_folder"]}/">bundle</a>' if r["app_folder"] else "")
        rows.append(f"""<tr class="{cls}">
  <td>{r['title'] or ''}</td>
  <td>{r['employer'] or ''}</td>
  <td>{r['location'] or ''}</td>
  <td>{r['salary']}</td>
  <td>{r['work_mode']}</td>
  <td>{r['date_posted']}</td>
  <td class="score {sc_cls}">{score}</td>
  <td class="flag">{flags}</td>
  <td><a href="{r['url']}" target="_blank">open ↗</a></td>
  <td><select data-url="{r['url']}">{status_options(r['status'])}</select></td>
  <td>{folder}</td>
</tr>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Carlos — Job Search Dashboard</title>
<style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#1a2330;background:#f6f8fb}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#5b6b80;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);border-radius:8px;overflow:hidden}}
th,td{{padding:9px 11px;text-align:left;border-bottom:1px solid #eef1f5;vertical-align:top}}
th{{background:#0f2a43;color:#fff;font-weight:600;cursor:pointer;position:sticky;top:0}}
tr.new{{background:#eafbf0}} tr:hover{{background:#f1f6ff}}
.score{{font-weight:700;text-align:center}} .hi{{color:#0a7d33}} .mid{{color:#b8860b}} .lo{{color:#888}}
.flag{{color:#b00020;font-size:12px}} a{{color:#1565c0;text-decoration:none}} a:hover{{text-decoration:underline}}
select{{font:13px sans-serif;padding:3px;border-radius:4px;border:1px solid #ccd4e0}}
.bar{{display:flex;gap:18px;margin-bottom:14px;flex-wrap:wrap}}
.card{{background:#fff;border-radius:8px;padding:10px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card b{{font-size:20px;display:block}}
</style></head><body>
<h1>Carlos Adabe — Healthcare Job Search</h1>
<div class="sub">Direct from {len(set(r['employer'] for r in matches))} employer career pages ·
Updated {date.today().isoformat()} · Sources: employer ATS only (no job boards)</div>
<div class="bar">
  <div class="card"><b>{len(matches)}</b>Matches (score ≥ 6)</div>
  <div class="card"><b>{len(new_today)}</b>New / updated</div>
  <div class="card"><b>{sum(1 for r in matches if r['fit_score']>=8)}</b>Strong (≥ 8)</div>
  <div class="card"><b>{sum(1 for r in matches if r['work_mode']=='Remote')}</b>Remote</div>
  <div class="card"><b>{sum(1 for r in matches if r['visa_flag'])}</b>Visa mentioned</div>
</div>
<table id="t">
<thead><tr>
<th>Job Title</th><th>Employer</th><th>Location</th><th>Salary</th><th>Mode</th>
<th>Posted</th><th>Fit</th><th>Flags</th><th>Link</th><th>Status</th><th>App</th>
</tr></thead><tbody>
{''.join(rows)}
</tbody></table>
<script>
// click-to-sort
document.querySelectorAll('th').forEach((th,i)=>th.onclick=()=>{{
 const tb=document.querySelector('tbody');
 const rows=[...tb.rows].sort((a,b)=>{{
   let x=a.cells[i].innerText,y=b.cells[i].innerText;
   let nx=parseFloat(x),ny=parseFloat(y);
   if(!isNaN(nx)&&!isNaN(ny))return ny-nx; return x.localeCompare(y);
 }});
 rows.forEach(r=>tb.appendChild(r));
}});
// persist status changes to localStorage (offline-friendly)
const KEY='cv_job_status';
const saved=JSON.parse(localStorage.getItem(KEY)||'{{}}');
document.querySelectorAll('select[data-url]').forEach(s=>{{
  const u=s.dataset.url; if(saved[u])s.value=saved[u];
  s.onchange=()=>{{saved[u]=s.value;localStorage.setItem(KEY,JSON.stringify(saved));}};
}});
</script>
</body></html>"""
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text(html)


def status_options(current):
    opts = ["New", "Saved", "Applied", "Interview", "Rejected", "Offer"]
    return "".join(f'<option {"selected" if o==current else ""}>{o}</option>' for o in opts)


if __name__ == "__main__":
    main()
