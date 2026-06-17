"""FlexJobs scraper — remote/flexible Europe health-informatics listings.

FlexJobs is subscription-based; public country browse pages list job cards,
but automated access is often throttled. Supports:

1. Live scrape of /remote-jobs/world/{country} and /remote-jobs/healthcare-medical
2. Optional subscriber session via env FLEXJOBS_COOKIE (copy from browser)
3. Optional manual import from data/europe/flexjobs_import.json (gitignored)
"""

from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from pathlib import Path

import requests

from ..config import SEARCH_QUERIES_BY_BOARD, DATA

BASE = "https://www.flexjobs.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 12)  # connect, read — fail fast when FlexJobs throttles bots
MAX_CONSECUTIVE_FAILURES = 3

# FlexJobs country URL slugs (remote-jobs/world/{slug})
EU_COUNTRY_SLUGS = [
    "United-Kingdom", "Ireland", "Sweden", "Norway", "Denmark", "Finland",
    "Germany", "France", "Netherlands", "Belgium", "Switzerland", "Austria",
    "Spain", "Portugal", "Italy", "Poland", "Czechia", "Greece", "Hungary",
    "Romania", "Croatia", "Slovenia", "Slovakia", "Lithuania", "Latvia",
    "Estonia", "Luxembourg", "Malta", "Cyprus", "Iceland",
]

# Default scrape: high-yield EU markets first (full list still available via arg)
PRIORITY_COUNTRY_SLUGS = [
    "United-Kingdom", "Ireland", "Sweden", "Germany", "Netherlands",
    "Denmark", "Norway", "Finland", "France", "Switzerland",
]

CATEGORY_SLUGS = [
    "healthcare-medical",
    "computer-it",
    "data-entry",
    "project-management",
]

IMPORT_PATH = DATA / "flexjobs_import.json"

JOB_LINK_RE = re.compile(
    r'<a[^>]+href="(?:https://www\.flexjobs\.com)?/HostedJob\.aspx\?id=(\d+)"[^>]*>'
    r'(?:<[^>]+>)*([^<]+?)(?:</[^>]+>)*</a>',
    re.I | re.S,
)
REMOTE_RE = re.compile(r"100%\s*Remote|Hybrid\s*Remote|Option\s+for\s+Remote", re.I)
DATE_RE = re.compile(
    r"\b(\d+\s+days?\s+ago|\d+\s+weeks?\s+ago|Yesterday|Today|\d+\s+months?\s+ago)\b",
    re.I,
)
SALARY_RE = re.compile(
    r"([\d,.]+\s*-\s*[\d,.]+\s*(?:USD|GBP|EUR|CHF|SEK|NOK|DKK)\s*(?:Annually|Hourly|Monthly)?)",
    re.I,
)
COUNTRY_FROM_SLUG = {
    "United-Kingdom": "UK",
    "Czechia": "Czech Republic",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    cookie = os.environ.get("FLEXJOBS_COOKIE", "").strip()
    if cookie:
        s.headers["Cookie"] = cookie
    return s


def _fetch(session: requests.Session, url: str) -> str | None:
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 2000:
            return r.text
    except Exception:
        pass
    return None


def _parse_listing(html: str, default_country: str = "") -> list[dict]:
    jobs, seen = [], set()
    for m in JOB_LINK_RE.finditer(html):
        job_id, title = m.group(1), unescape(re.sub(r"\s+", " ", m.group(2)).strip())
        if not title or job_id in seen:
            continue
        seen.add(job_id)
        block = html[m.end(): m.end() + 1200]
        block_plain = re.sub(r"<[^>]+>", " ", block)
        block_plain = unescape(re.sub(r"\s+", " ", block_plain))

        remote_m = REMOTE_RE.search(block_plain)
        work_mode = "Remote" if remote_m and "100%" in remote_m.group(0) else (
            "Hybrid" if remote_m and "Hybrid" in remote_m.group(0) else "On-site"
        )
        date_m = DATE_RE.search(block_plain)
        sal_m = SALARY_RE.search(block_plain)
        loc = default_country
        for pat in (
            r"United Kingdom", r"London, United Kingdom", r"Sweden", r"Norway",
            r"Denmark", r"Finland", r"Germany", r"France", r"Netherlands",
            r"Ireland", r"Switzerland", r"Spain", r"Portugal", r"Work from Anywhere",
        ):
            lm = re.search(pat, block_plain, re.I)
            if lm:
                loc = lm.group(0)
                break

        desc_m = re.search(
            r"(?:Employee|Freelance|Contract)\s+(.{40,400}?)(?:\[|HostedJob|<)",
            block_plain,
        )
        description = desc_m.group(1).strip() if desc_m else block_plain[:350].strip()

        jobs.append({
            "employer": "FlexJobs listing",
            "title": title,
            "location": loc or "Europe",
            "country": COUNTRY_FROM_SLUG.get(default_country, default_country) or loc,
            "url": f"{BASE}/HostedJob.aspx?id={job_id}",
            "description": description,
            "salary_text": sal_m.group(1) if sal_m else "",
            "remote_type": work_mode,
            "employment_type": "Full-time" if "Full-Time" in block_plain else "",
            "date_posted": date_m.group(1) if date_m else "",
            "source_platform": "FlexJobs",
            "source_board": "flexjobs",
            "region": "europe",
        })
    return jobs


def _load_import() -> list[dict]:
    if not IMPORT_PATH.exists():
        return []
    try:
        raw = json.loads(IMPORT_PATH.read_text())
    except Exception:
        return []
    jobs = []
    for item in raw if isinstance(raw, list) else raw.get("jobs", []):
        url = item.get("url") or ""
        if not url.startswith("http"):
            url = f"{BASE}/HostedJob.aspx?id={item.get('id', '')}"
        jobs.append({
            "employer": item.get("employer") or item.get("company") or "FlexJobs listing",
            "title": item.get("title") or "Untitled",
            "location": item.get("location") or "Europe",
            "country": item.get("country") or "",
            "url": url,
            "description": item.get("description") or "",
            "salary_text": item.get("salary") or item.get("salary_text") or "",
            "remote_type": item.get("remote_type") or item.get("work_mode") or "",
            "employment_type": item.get("employment_type") or "Full-time",
            "date_posted": item.get("date_posted") or item.get("date") or "",
            "source_platform": "FlexJobs",
            "source_board": "flexjobs",
            "region": "europe",
        })
    return jobs


def _keyword_urls(queries: list[str]) -> list[str]:
    urls = []
    for q in queries[:6]:
        slug = q.replace(" ", "+")
        urls.append(f"{BASE}/search?search={slug}&searchkeyword={slug}")
    return urls


def scrape_flexjobs(
    country_slugs=None,
    categories=None,
    max_per_source: int = 40,
    all_countries: bool = False,
) -> list[dict]:
    country_slugs = country_slugs or (
        EU_COUNTRY_SLUGS if all_countries else PRIORITY_COUNTRY_SLUGS
    )
    categories = categories or CATEGORY_SLUGS[:1]
    queries = SEARCH_QUERIES_BY_BOARD.get("flexjobs", [])
    session = _session()
    jobs, seen = [], set()
    failures = 0

    sources = [f"{BASE}/remote-jobs/world/{slug}" for slug in country_slugs]
    sources += [f"{BASE}/remote-jobs/{cat}" for cat in categories]
    if os.environ.get("FLEXJOBS_COOKIE"):
        sources += _keyword_urls(queries)

    for url in sources:
        slug = url.rsplit("/", 1)[-1]
        default_country = slug.replace("-", " ") if "/world/" in url else ""
        html = _fetch(session, url)
        if not html:
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES and not jobs:
                break
            continue
        failures = 0
        for job in _parse_listing(html, default_country=default_country):
            if job["url"] in seen:
                continue
            seen.add(job["url"])
            jobs.append(job)
            if len(jobs) >= max_per_source * len(sources):
                break

    imported = _load_import()
    for job in imported:
        if job["url"] not in seen:
            seen.add(job["url"])
            jobs.append(job)

    if not jobs and failures and not imported:
        print(
            "     (FlexJobs unreachable or paywalled — set FLEXJOBS_COOKIE "
            "or add data/europe/flexjobs_import.json)"
        )
    return jobs
