"""StepStone.de scraper (Germany / Europe)."""

from __future__ import annotations

import re
from html import unescape

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/json",
}
TIMEOUT = 45
BASE = "https://www.stepstone.de"
STEPSTONE_QUERIES = [
    "health-informatics",
    "medizinische-informatik",
    "krankenhaus-informatik",
    "healthcare-data",
]


def _slug_parts(path: str) -> tuple[str, str, str]:
    """Parse /stellenangebote--Title--Location-Company--ID-inline.html"""
    slug = path.split("/stellenangebote--", 1)[-1]
    slug = slug.replace("-inline.html", "").replace(".html", "")
    parts = slug.split("--")
    if len(parts) < 2:
        return slug.replace("-", " "), "", ""
    job_id = parts[-1]
    body = parts[:-1]
    if len(body) >= 2:
        title = body[0].replace("-", " ")
        company = body[-1].replace("-", " ")
        location = " ".join(body[1:-1]).replace("-", " ") if len(body) > 2 else ""
        return title, company, location
    return body[0].replace("-", " "), "", job_id


def _parse_search(html: str, employer_default: str) -> list[dict]:
    jobs, seen = [], set()
    for block in re.findall(r"<article[^>]*data-at=\"job-item\"[\s\S]*?</article>", html):
        link = re.search(r'href="(/stellenangebote[^"]+)"', block)
        if not link:
            continue
        path = unescape(link.group(1))
        jurl = BASE + path
        if jurl in seen:
            continue
        seen.add(jurl)
        title_m = re.search(r'data-at="job-item-title"[^>]*>\s*<span[^>]*>([^<]+)</span>', block)
        company_m = re.search(r'data-at="job-item-company-name"[^>]*>([^<]+)<', block)
        loc_m = re.search(r'data-at="job-item-location"[^>]*>([^<]+)<', block)
        title, company, location = _slug_parts(path)
        if title_m:
            title = unescape(title_m.group(1).strip())
        if company_m:
            company = unescape(company_m.group(1).strip())
        if loc_m:
            location = unescape(loc_m.group(1).strip())
        jobs.append({
            "employer": company or employer_default,
            "title": title or "Untitled",
            "location": location or "Germany",
            "url": jurl,
            "description": "",
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": "",
            "source_platform": "StepStone",
        })
    if jobs:
        return jobs

    for path in re.findall(r'href="(/stellenangebote--[^"]+)"', html):
        path = unescape(path)
        jurl = BASE + path
        if jurl in seen:
            continue
        seen.add(jurl)
        title, company, location = _slug_parts(path)
        jobs.append({
            "employer": company or employer_default,
            "title": title or "Untitled",
            "location": location or "Germany",
            "url": jurl,
            "description": "",
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": "",
            "source_platform": "StepStone",
        })
    return jobs


def scrape_stepstone(queries=None, max_per_query: int = 30) -> list[dict]:
    queries = queries or STEPSTONE_QUERIES
    jobs, seen = [], set()
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(BASE + "/", timeout=TIMEOUT)
    except Exception:
        pass
    failures = 0
    for q in queries:
        slug = q.strip().lower().replace(" ", "-")
        url = f"{BASE}/jobs/{slug}"
        html = None
        for attempt in range(2):
            try:
                r = session.get(
                    url,
                    timeout=TIMEOUT,
                    headers={"Referer": BASE + "/"},
                )
                if r.status_code == 200:
                    html = r.text
                    break
                failures += 1
            except Exception:
                failures += 1
                continue
        if not html:
            continue
        for job in _parse_search(html, "Unknown employer"):
            if job["url"] in seen:
                continue
            seen.add(job["url"])
            jobs.append(job)
            if len(jobs) >= max_per_query * len(queries):
                return jobs
    if not jobs and failures:
        print("     (StepStone unreachable from this network — timeouts/403; scraper wired for when access works)")
    return jobs
