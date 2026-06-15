# JOB-Search — Direct-from-employer healthcare job pipeline

Searches jobs **directly from each employer's own career page / ATS** (no job
boards, no aggregators) for the 669 Epic-using US healthcare facilities in
`Healthcare organizations using Epic EHR.xlsx`, scores them against Carlos
Adabe's profile, and generates tailored CV + cover-letter bundles plus a
dashboard.

## Pipeline

| Step | Script | Output |
|------|--------|--------|
| 1. Extract facilities + salvage domains | `pipeline/extract_facilities.py` | `data/facilities.json` |
| 2. Resolve real career URLs (HTTP prober) | `pipeline/resolve_career_urls.py` | `data/facilities_resolved.json` |
| 3. Scrape jobs from career pages | `pipeline/scrape.py` | `data/jobs_raw.json` |
| 4. Score + filter + tailor + dashboard | `pipeline/run_all.py` | `data/matches.json`, `applications/`, `dashboard/index.html` |
| Daily run (all of the above) | `pipeline/daily.sh` | + `data/new_today.json` |

## Quick start
```bash
pip3 install openpyxl requests
python3 pipeline/extract_facilities.py
python3 pipeline/resolve_career_urls.py      # slow (web probing); run once
python3 pipeline/scrape.py --only-api        # Workday/Greenhouse/Lever/SmartRecruiters
python3 pipeline/run_all.py                  # scoring, bundles, dashboard
open dashboard/index.html
```

## Scraper adapters
- **Workday** (`*.myworkdayjobs.com`) — JSON CXS API. Most reliable; ~67 employers here.
- **Greenhouse / Lever / SmartRecruiters** — public board APIs.
- **generic HTML** — best-effort fallback, flagged `low-confidence`.

**iCIMS** — best-effort adapter (`scrape_icims`) works only for tenants that serve
job rows server-side in the iframe. Many tenants (e.g. Garnet Health, Lehigh Valley)
force-redirect the iframe to a custom JS SPA domain and render client-side, which a
requests-based scraper cannot follow — those need a headless browser (Playwright).
**Avature, Taleo, ADP, HealthcareSource** are similarly JS-heavy/SPA and not covered;
they fall through to the generic scraper and are flagged. Their discovered career
URLs are still recorded in `data/discovered_urls.json` for a future headless pass.

## Scoring (0–10)
Weighted: title fit 35%, skills match 30%, domain relevance 15%, seniority 10%,
location 10%. Only roles **≥ 6** surface. Hard filters: US, full-time, salary
≥ $85k where disclosed, **excludes** roles requiring clinical licensure
(MD/RN/NP/PharmD…). **Flags** (not exclusions): on-site roles, and any role
mentioning visa sponsorship / work authorization (important — candidate is
Stockholm-based and likely needs sponsorship).

## Daily automation
`pipeline/daily.sh` is idempotent and tracks seen jobs in `data/seen.json`, so
already-seen postings are not resurfaced unless their content changed. Schedule
with cron, e.g. every day at 07:00:
```
0 7 * * * /Users/kah-los/JOB-Search/pipeline/daily.sh >> /Users/kah-los/JOB-Search/data/daily.log 2>&1
```

## Known limitations (honest)
- Not every one of the 669 sites scrapes reliably — only API-backed ATS plus a
  weak HTML fallback. Coverage grows as adapters are added.
- "Daily autonomous forever" = a scheduled local job, not a hosted service.
- Tailored CV/cover letters are strong **templated drafts**; top matches deserve
  a hand polish.
