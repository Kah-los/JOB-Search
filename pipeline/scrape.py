#!/usr/bin/env python3
"""
Step 3: Scrape job postings DIRECTLY from employer career pages.

No job boards / aggregators — only the employer's own career site / ATS.

Platform adapters (in priority order of reliability):
  - Workday   (JSON CXS API)      -> most employers in this dataset
  - Greenhouse (public board API)
  - Lever     (public postings API)
  - SmartRecruiters (public API)
  - generic_html  (best-effort link/title scrape; flagged low-confidence)

Each adapter yields normalized job dicts:
  {employer, title, location, url, description, salary_text, remote_type,
   employment_type, date_posted, source_platform}

Usage:
  python3 scrape.py --limit 20            # scrape first N resolved facilities
  python3 scrape.py --ats Workday         # only Workday employers
  python3 scrape.py --search "analyst"    # pass a query where supported
Writes data/jobs_raw.json (deduped by url).
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
FACS = ROOT / "data" / "facilities_resolved.json"
OUT = ROOT / "data" / "jobs_raw.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
           "Accept": "application/json,text/html"}
TIMEOUT = 20

# Broad query terms spanning ALL of the candidate's domains. Epic/EHR is just one
# slice among many. Kept generic so the list APIs surface the full relevant universe
# (analyst/coordinator/manager/specialist roles across HIM, CDI, data, quality,
# compliance, revenue cycle, population health, project mgmt, operations, etc.).
DEFAULT_QUERIES = [
    "analyst", "informatics", "health information", "data", "data analyst",
    "analytics", "business intelligence", "reporting", "documentation",
    "clinical documentation", "CDI", "coding", "revenue cycle", "revenue integrity",
    "compliance", "regulatory", "privacy", "governance", "quality",
    "quality improvement", "patient safety", "population health", "interoperability",
    "project manager", "program manager", "project coordinator", "operations",
    "case management", "care coordination", "medical records", "health information management",
    "informatics analyst", "business analyst", "systems analyst", "decision support",
    "EHR", "Epic", "clinical informatics", "training", "education", "consultant",
    "digital health", "transformation", "policy", "auditor", "registry",
]


# ---------------- Workday ----------------
WD_RE = re.compile(r"https?://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/([^/?#]+)", re.I)


def scrape_workday(url, employer, queries=None, cap=4000):
    """Fetch ALL postings (empty searchText, full pagination)."""
    m = WD_RE.search(url)
    if not m:
        return []
    tenant, dc, site = m.group(1), m.group(2), m.group(3)
    api = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    base_view = f"https://{tenant}.{dc}.myworkdayjobs.com/{site}"
    seen, jobs, offset = set(), [], 0
    while offset < cap:
        try:
            r = requests.post(api, headers={**HEADERS, "Content-Type": "application/json"},
                              json={"appliedFacets": {}, "limit": 20,
                                    "offset": offset, "searchText": ""}, timeout=TIMEOUT)
            if r.status_code != 200:
                break
            data = r.json()
        except Exception:
            break
        postings = data.get("jobPostings", [])
        if not postings:
            break
        for p in postings:
            ext = p.get("externalPath", "")
            jurl = base_view + ext
            if jurl in seen:
                continue
            seen.add(jurl)
            jobs.append({
                "employer": employer, "title": p.get("title"),
                "location": p.get("locationsText"), "url": jurl,
                "description": "", "salary_text": "",
                "remote_type": "", "employment_type": "",
                "date_posted": p.get("postedOn", ""),
                "source_platform": "Workday",
            })
        offset += 20
        if len(postings) < 20:
            break
    return jobs


# ---------------- Greenhouse ----------------
def scrape_greenhouse(url, employer, queries=None):
    # token is the path segment after greenhouse.io/
    m = re.search(r"greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9\-]+)", url, re.I)
    token = m.group(1) if m else None
    if not token:
        return []
    api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    try:
        r = requests.get(api, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "employer": employer, "title": j.get("title"),
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "description": re.sub("<[^>]+>", " ", j.get("content", "") or "")[:6000],
            "salary_text": "", "remote_type": "", "employment_type": "",
            "date_posted": j.get("updated_at", ""), "source_platform": "Greenhouse",
        })
    return jobs


# ---------------- Lever ----------------
def scrape_lever(url, employer, queries=None):
    m = re.search(r"lever\.co/([a-z0-9\-]+)", url, re.I)
    token = m.group(1) if m else None
    if not token:
        return []
    api = f"https://api.lever.co/v0/postings/{token}?mode=json"
    try:
        r = requests.get(api, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    jobs = []
    for j in data:
        cat = j.get("categories", {}) or {}
        jobs.append({
            "employer": employer, "title": j.get("text"),
            "location": cat.get("location"), "url": j.get("hostedUrl"),
            "description": re.sub("<[^>]+>", " ", j.get("descriptionPlain", "") or "")[:6000],
            "salary_text": "", "remote_type": cat.get("commitment", ""),
            "employment_type": cat.get("commitment", ""),
            "date_posted": "", "source_platform": "Lever",
        })
    return jobs


# ---------------- SmartRecruiters ----------------
def scrape_smartrecruiters(url, employer, queries=None):
    m = re.search(r"smartrecruiters\.com/([a-z0-9\-]+)", url, re.I)
    company = m.group(1) if m else None
    if not company:
        return []
    api = f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100"
    try:
        r = requests.get(api, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    jobs = []
    for j in data.get("content", []):
        loc = j.get("location", {}) or {}
        jobs.append({
            "employer": employer, "title": j.get("name"),
            "location": ", ".join(filter(None, [loc.get("city"), loc.get("region")])),
            "url": f"https://jobs.smartrecruiters.com/{company}/{j.get('id')}",
            "description": "", "salary_text": "",
            "remote_type": "Remote" if loc.get("remote") else "",
            "employment_type": "", "date_posted": j.get("releasedDate", ""),
            "source_platform": "SmartRecruiters",
        })
    return jobs


# ---------------- Oracle Cloud Recruiting (ORC) ----------------
ORC_RE = re.compile(r"https?://([^/]+)/hcmUI/CandidateExperience/[^/]+/sites/([^/?#]+)", re.I)


def scrape_oracle(url, employer, queries=None, cap=4000):
    """Fetch ALL requisitions (no keyword, paginated by offset)."""
    m = ORC_RE.search(url)
    if not m:
        return []
    host, site = m.group(1), m.group(2)
    api = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    view = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job"
    seen, jobs, offset, total = set(), [], 0, None
    while offset < cap:
        try:
            r = requests.get(api, headers={**HEADERS, "Accept": "application/json"},
                             params={"onlyData": "true", "expand": "requisitionList",
                                     "finder": f"findReqs;siteNumber={site},"
                                               f"sortBy=POSTING_DATES_DESC,limit=50,offset={offset}"},
                             timeout=TIMEOUT)
            if r.status_code != 200:
                break
            items = r.json().get("items", [])
        except Exception:
            break
        if not items:
            break
        total = items[0].get("TotalJobsCount", total)
        page = items[0].get("requisitionList", [])
        if not page:
            break
        for j in page:
            jid = j.get("Id")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            jobs.append({
                "employer": employer, "title": j.get("Title"),
                "location": j.get("PrimaryLocation"),
                "url": f"{view}/{jid}",
                "description": re.sub("<[^>]+>", " ", j.get("ShortDescriptionStr", "") or ""),
                "salary_text": "", "remote_type": "", "employment_type": "",
                "date_posted": j.get("PostedDate", ""),
                "source_platform": "OracleORC", "_orc_api": api, "_orc_site": site,
            })
        offset += 50
        if total is not None and offset >= total:
            break
    return jobs


# ---------------- UKG / UltiPro ----------------
ULTI_RE = re.compile(r"https?://([^/]+)/([^/]+)/JobBoard/([0-9a-f\-]+)", re.I)


def scrape_ultipro(url, employer, queries=None, cap=2000):
    """Fetch ALL opportunities (empty QueryString, paginated by Skip)."""
    m = ULTI_RE.search(url)
    if not m:
        return []
    host, comp, guid = m.group(1), m.group(2), m.group(3)
    api = f"https://{host}/{comp}/JobBoard/{guid}/JobBoardView/LoadSearchResults"
    detail = f"https://{host}/{comp}/JobBoard/{guid}/OpportunityDetail?opportunityId="
    seen, jobs, skip = set(), [], 0
    while skip < cap:
        body = {"opportunitySearch": {"Top": 50, "Skip": skip, "QueryString": "",
                                      "OrderBy": [{"Value": "postedDateDesc"}], "Filters": []},
                "matchCriteria": {"PreferredJobs": [], "Educations": [],
                                  "LicenseAndCertifications": [], "Skills": [],
                                  "WorkExperiences": [], "PreferredLocations": []}}
        try:
            r = requests.post(api, headers={**HEADERS, "Content-Type": "application/json"},
                              json=body, timeout=TIMEOUT)
            if r.status_code != 200:
                break
            opps = r.json().get("opportunities", [])
        except Exception:
            break
        if not opps:
            break
        for o in opps:
            oid = o.get("Id") or o.get("Guid")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            jobs.append({
                "employer": employer, "title": o.get("Title"),
                "location": o.get("LocationDescription") or "",
                "url": detail + str(o.get("Id", oid)),
                "description": re.sub("<[^>]+>", " ", o.get("Description", "") or "")[:8000],
                "salary_text": "", "remote_type": "", "employment_type": "",
                "date_posted": o.get("PostedDate", ""), "source_platform": "UltiPro",
            })
        skip += 50
        if len(opps) < 50:
            break
    return jobs


# ---------------- Phenom (CareerSite /api/jobs JSON) ----------------
def scrape_phenom(url, employer, queries=None, cap=3000):
    """Phenom career sites expose /api/jobs as JSON with descriptions inline.
    Covers the common variant (e.g. Mount Sinai, Orlando Health). Some Phenom
    tenants instead serve /search-jobs/results HTML — those return [] here."""
    host = urlparse(url if "://" in url else "https://" + url).netloc
    if not host:
        return []
    api = f"https://{host}/api/jobs"
    seen, jobs, page = set(), [], 1
    while len(jobs) < cap:
        try:
            r = requests.get(api, headers={**HEADERS, "Accept": "application/json"},
                             params={"page": page, "limit": 100}, timeout=TIMEOUT)
            if r.status_code != 200 or "application/json" not in r.headers.get("content-type", ""):
                break
            d = r.json()
        except Exception:
            break
        page_jobs = d.get("jobs", [])
        if not page_jobs:
            break
        for jw in page_jobs:
            j = jw.get("data", {}) or {}
            slug = j.get("slug") or j.get("req_id")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            loc = ", ".join(filter(None, [j.get("city"), j.get("state")])) or j.get("location_name", "")
            sal = j.get("salary_value") or j.get("salary_min_value") or ""
            jobs.append({
                "employer": employer, "title": j.get("title"), "location": loc,
                "url": f"https://{host}/jobs/{slug}",
                "description": re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", j.get("description", "") or "")).strip()[:8000],
                "salary_text": str(sal), "remote_type": "", "employment_type": "",
                "date_posted": j.get("posted_date", ""), "source_platform": "Phenom",
            })
        tc = d.get("totalCount")
        if tc and len(seen) >= tc:
            break
        if len(page_jobs) < 100:
            break
        page += 1
    return jobs


# ---------------- iCIMS (best-effort) ----------------
# NOTE: many iCIMS tenants force-redirect the job iframe to a custom JS SPA domain
# and render listings client-side, which a requests-based scraper cannot follow.
# This adapter works only for cooperative tenants that serve job rows server-side
# in the iframe. Redirect-configured tenants (e.g. Garnet, LVHN) need a headless
# browser and will return [] here.
ICIMS_RE = re.compile(r"https?://([a-z0-9\-]+\.icims\.com)", re.I)


def scrape_icims(url, employer, queries=None, max_pages=20):
    m = ICIMS_RE.search(url)
    if not m:
        return []
    host = m.group(1)
    base = f"https://{host}/jobs/search"
    s = requests.Session()
    s.headers.update(HEADERS)
    seen, jobs = set(), []
    for pr in range(max_pages):
        parent = f"{base}?ss=1&searchKeyword=&pr={pr}"
        try:
            s.get(parent, timeout=TIMEOUT)
            r = s.get(f"{parent}&in_iframe=1&needsRedirect=false",
                      headers={"Referer": parent}, timeout=TIMEOUT)
            t = r.text
        except Exception:
            break
        if "window.top.location" in t or len(t) < 500:
            break  # tenant force-redirects — not scrapable here
        rows = re.findall(r'<a[^>]+href="([^"]*?/jobs/\d+/[^"]*?/job[^"]*)"[^>]*>(.*?)</a>',
                          t, re.S)
        new = 0
        for href, inner in rows:
            jurl = href if href.startswith("http") else f"https://{host}{href}"
            if jurl in seen:
                continue
            seen.add(jurl)
            title = re.sub(r"<[^>]+>", " ", inner)
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            jobs.append({
                "employer": employer, "title": title, "location": "",
                "url": jurl, "description": "", "salary_text": "",
                "remote_type": "", "employment_type": "", "date_posted": "",
                "source_platform": "iCIMS",
            })
            new += 1
        if new == 0:
            break
    return jobs


# ---------------- generic html (low confidence) ----------------
def scrape_generic(url, employer, queries):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200 or not r.text:
            return []
        html = r.text
    except Exception:
        return []
    jobs = []
    # naive: anchor tags whose text looks like a job title near careers context
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,90})</a>', html, re.I):
        href, text = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        if re.search(r"(analyst|manager|specialist|coordinator|informatics|"
                     r"director|technician|engineer|consultant|administrator)", text, re.I):
            if href.startswith("/"):
                p = urlparse(url)
                href = f"{p.scheme}://{p.netloc}{href}"
            jobs.append({
                "employer": employer, "title": text, "location": "",
                "url": href, "description": "", "salary_text": "",
                "remote_type": "", "employment_type": "", "date_posted": "",
                "source_platform": "generic-html(low-confidence)",
            })
    # dedupe by title
    out, seen = [], set()
    for j in jobs:
        if j["title"].lower() in seen:
            continue
        seen.add(j["title"].lower())
        out.append(j)
    return out[:40]


def pick_adapter(url):
    low = (url or "").lower()
    if "myworkdayjobs.com" in low:
        return scrape_workday
    if "greenhouse.io" in low:
        return scrape_greenhouse
    if "lever.co" in low:
        return scrape_lever
    if "smartrecruiters.com" in low:
        return scrape_smartrecruiters
    if "oraclecloud.com" in low and "candidateexperience" in low:
        return scrape_oracle
    if "/jobboard/" in low and ("ultipro.com" in low or "ukg.com" in low):
        return scrape_ultipro
    if ".icims.com" in low:
        return scrape_icims
    return scrape_generic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max facilities to scrape (0=all)")
    ap.add_argument("--ats", default=None, help="only this detected ATS")
    ap.add_argument("--search", default=None, help="single search term override")
    ap.add_argument("--only-api", action="store_true",
                    help="skip generic-html adapter (API platforms only)")
    args = ap.parse_args()

    facs = json.loads(FACS.read_text())
    targets = [f for f in facs if f.get("resolved_url")]
    if args.ats:
        targets = [f for f in targets if (f.get("ats") or "").lower() == args.ats.lower()]
    if args.limit:
        targets = targets[:args.limit]
    queries = [args.search] if args.search else DEFAULT_QUERIES

    all_jobs, seen = [], set()
    for i, f in enumerate(targets, 1):
        url = f["resolved_url"]
        # Phenom hosts vary (careers.X / jobs.X), so route by the facility's ats tag
        adapter = scrape_phenom if (f.get("ats") == "Phenom") else pick_adapter(url)
        if args.only_api and adapter is scrape_generic:
            continue
        try:
            jobs = adapter(url, f["name"], queries)
        except Exception as e:
            print(f"  [err] {f['name']}: {e}", file=sys.stderr)
            jobs = []
        added = 0
        for j in jobs:
            if not j.get("url") or j["url"] in seen:
                continue
            seen.add(j["url"])
            j["employer_state"] = f.get("state")
            all_jobs.append(j)
            added += 1
        print(f"[{i}/{len(targets)}] {f['name'][:40]:40} {adapter.__name__:22} +{added}")

    OUT.write_text(json.dumps(all_jobs, indent=2))
    print(f"\nWrote {OUT}: {len(all_jobs)} jobs from {len(targets)} employers")


if __name__ == "__main__":
    main()
