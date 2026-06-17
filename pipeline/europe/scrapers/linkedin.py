"""LinkedIn Jobs guest API scraper — Europe health-informatics + health-tech startups.

Uses LinkedIn's public guest endpoints (no login required):
  /jobs-guest/jobs/api/seeMoreJobPostings/search
  /jobs-guest/jobs/api/jobPosting/{id}

Prioritises remote/hybrid roles and private health-tech companies that hire
international candidates. Optional LINKEDIN_COOKIE for richer results.
"""

from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

import requests

from ..config import DATA, SEARCH_QUERIES_BY_BOARD
from ..employer_signals import match_seed_employer

BASE = "https://www.linkedin.com"
SEARCH_URL = f"{BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_URL = f"{BASE}/jobs-guest/jobs/api/jobPosting"
IMPORT_PATH = DATA / "linkedin_import.json"
STARTUP_SEED_PATH = DATA / "healthtech_startups.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 20)
DELAY = 0.7
MAX_PAGES = 1
PAGE_SIZE = 25
MAX_KEYWORD_LOC_PAIRS = 24
MAX_STARTUP_COMPANIES = 12

# LinkedIn geoId values for priority EU markets
EU_LOCATIONS = [
    {"location": "Sweden", "geo_id": "105117694", "country": "Sweden"},
    {"location": "United Kingdom", "geo_id": "101165590", "country": "UK"},
    {"location": "Germany", "geo_id": "101282230", "country": "Germany"},
    {"location": "Netherlands", "geo_id": "102890719", "country": "Netherlands"},
    {"location": "Ireland", "geo_id": "104738515", "country": "Ireland"},
    {"location": "France", "geo_id": "105015875", "country": "France"},
    {"location": "Denmark", "geo_id": "104514075", "country": "Denmark"},
    {"location": "Norway", "geo_id": "103819153", "country": "Norway"},
    {"location": "Finland", "geo_id": "100456013", "country": "Finland"},
    {"location": "Switzerland", "geo_id": "106693272", "country": "Switzerland"},
]

CARD_RE = re.compile(
    r'data-entity-urn="urn:li:jobPosting:(\d+)"[\s\S]*?'
    r'base-search-card__title[^>]*>\s*([^<]+?)\s*</h3>[\s\S]*?'
    r'base-search-card__subtitle[^>]*>[\s\S]*?>\s*([^<]+?)\s*</a>[\s\S]*?'
    r'job-search-card__location[^>]*>\s*([^<]+?)\s*</span>',
    re.I | re.S,
)
DATE_RE = re.compile(
    r'job-search-card__listdate[^>]*--new[^>]*>\s*([^<]+?)\s*</time>|'
    r'job-search-card__listdate[^>]*>\s*([^<]+?)\s*</time>',
    re.I | re.S,
)
DESC_RE = re.compile(
    r'<div[^>]+class="[^"]*description[^"]*"[^>]*>([\s\S]*?)</div>',
    re.I,
)
SHOW_MORE_RE = re.compile(r"Show more", re.I)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    cookie = os.environ.get("LINKEDIN_COOKIE", "").strip()
    if cookie:
        s.headers["Cookie"] = cookie
    return s


def _fetch(session: requests.Session, url: str, params: dict | None = None) -> str | None:
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 200 and len(r.text) > 200:
            return r.text
    except Exception:
        pass
    return None


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _parse_cards(html: str, default_country: str = "") -> list[dict]:
    jobs, seen = [], set()
    for block in re.findall(r"<li>[\s\S]*?</li>", html):
        urn = re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', block)
        if not urn:
            continue
        job_id = urn.group(1)
        if job_id in seen:
            continue
        title_m = re.search(r"base-search-card__title[^>]*>\s*([^<]+?)\s*</h3>", block, re.I | re.S)
        company_m = re.search(
            r"base-search-card__subtitle[^>]*>[\s\S]*?>\s*([^<]+?)\s*</a>", block, re.I | re.S
        )
        loc_m = re.search(r"job-search-card__location[^>]*>\s*([^<]+?)\s*</span>", block, re.I | re.S)
        date_m = DATE_RE.search(block)
        if not title_m:
            continue
        title = unescape(re.sub(r"\s+", " ", title_m.group(1)).strip())
        employer = unescape(re.sub(r"\s+", " ", (company_m.group(1) if company_m else "")).strip())
        location = unescape(re.sub(r"\s+", " ", (loc_m.group(1) if loc_m else default_country)).strip())
        date_posted = ""
        if date_m:
            date_posted = unescape((date_m.group(1) or date_m.group(2) or "").strip())

        work_mode = "Remote" if re.search(r"\bremote\b", location, re.I) else (
            "Hybrid" if re.search(r"\bhybrid\b", location, re.I) else "On-site"
        )
        country = default_country
        for c in ("Sweden", "United Kingdom", "Germany", "Netherlands", "Ireland",
                  "France", "Denmark", "Norway", "Finland", "Switzerland", "Poland", "Spain"):
            if re.search(rf"\b{re.escape(c)}\b", location, re.I):
                country = "UK" if c == "United Kingdom" else c
                break

        jobs.append({
            "employer": employer or "Unknown",
            "title": title,
            "location": location,
            "country": country,
            "city": location.split(",")[0].strip() if "," in location else "",
            "url": f"{BASE}/jobs/view/{job_id}",
            "linkedin_job_id": job_id,
            "description": "",
            "salary_text": "",
            "work_mode": work_mode,
            "remote_type": work_mode,
            "employment_type": "Full-time",
            "date_posted": date_posted,
            "experience_level": "",
            "source_platform": "LinkedIn",
            "source_board": "linkedin",
            "region": "europe",
        })
        seen.add(job_id)
    return jobs


def _fetch_description(session: requests.Session, job_id: str) -> str:
    html = _fetch(session, f"{JOB_URL}/{job_id}")
    if not html:
        return ""
    for m in DESC_RE.finditer(html):
        chunk = _strip_html(m.group(1))
        if len(chunk) > 80 and not SHOW_MORE_RE.search(chunk[:40]):
            return chunk[:2500]
    # Fallback: show-more block
    sm = re.search(r"show-more-less-html__markup[^>]*>([\s\S]*?)</div>", html, re.I)
    if sm:
        return _strip_html(sm.group(1))[:2500]
    return ""


def _load_startup_seed() -> list[dict]:
    if not STARTUP_SEED_PATH.exists():
        return []
    try:
        return json.loads(STARTUP_SEED_PATH.read_text())
    except Exception:
        return []


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
            jid = item.get("linkedin_job_id") or item.get("id") or ""
            url = f"{BASE}/jobs/view/{jid}" if jid else ""
        jobs.append({
            "employer": item.get("employer") or item.get("company") or "Unknown",
            "title": item.get("title") or "Untitled",
            "location": item.get("location") or "Europe",
            "country": item.get("country") or "",
            "city": item.get("city") or "",
            "url": url,
            "description": item.get("description") or "",
            "work_mode": item.get("work_mode") or item.get("remote_type") or "",
            "remote_type": item.get("remote_type") or item.get("work_mode") or "",
            "date_posted": item.get("date_posted") or "",
            "source_platform": "LinkedIn",
            "source_board": "linkedin",
            "region": "europe",
        })
    return jobs


def _search(
    session: requests.Session,
    *,
    keywords: str,
    location: str,
    geo_id: str,
    country: str,
    company_id: str = "",
    remote_only: bool = False,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    jobs = []
    for page in range(max_pages):
        params = {
            "keywords": keywords,
            "location": location,
            "geoId": geo_id,
            "start": page * PAGE_SIZE,
            "f_TPR": "r2592000",  # past month
        }
        if remote_only:
            params["f_WT"] = "2"
        if company_id:
            params["f_C"] = company_id
        html = _fetch(session, SEARCH_URL, params)
        time.sleep(DELAY)
        if not html:
            break
        batch = _parse_cards(html, default_country=country)
        if not batch:
            break
        jobs.extend(batch)
    return jobs


def scrape_linkedin(
    *,
    fetch_descriptions: bool = True,
    max_description_fetches: int = 40,
    remote_first: bool = True,
) -> list[dict]:
    session = _session()
    queries = SEARCH_QUERIES_BY_BOARD.get("linkedin", [])
    jobs, seen = [], set()
    failures = 0

    # 1) Remote keyword searches across EU hubs (best for foreign candidates)
    locs = EU_LOCATIONS[:6]
    pairs_done = 0
    for loc in locs:
        for q in queries[:6]:
            if pairs_done >= MAX_KEYWORD_LOC_PAIRS:
                break
            batch = _search(
                session,
                keywords=q,
                location=loc["location"],
                geo_id=loc["geo_id"],
                country=loc["country"],
                remote_only=True,
                max_pages=1,
            )
            pairs_done += 1
            for job in batch:
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                jobs.append(job)
        if pairs_done >= MAX_KEYWORD_LOC_PAIRS:
            break

    # 2) Health-tech startup / private company pages
    for row in _load_startup_seed()[:MAX_STARTUP_COMPANIES]:
        cid = row.get("linkedin_company_id")
        if not cid:
            continue
        batch = _search(
            session,
            keywords="informatics OR health OR clinical OR data OR implementation OR integration",
            location=row.get("country", "Europe"),
            geo_id=next(
                (l["geo_id"] for l in EU_LOCATIONS if l["country"] == row.get("country")),
                EU_LOCATIONS[0]["geo_id"],
            ),
            country=row.get("country", ""),
            company_id=str(cid),
            max_pages=1,
        )
        for job in batch:
            if job["url"] in seen:
                continue
            seen.add(job["url"])
            seed = match_seed_employer(job["employer"]) or row
            job["employer"] = seed.get("name") or job["employer"]
            job["startup_match"] = True
            jobs.append(job)

    # 3) Enrich descriptions for startup matches + remote roles first
    if fetch_descriptions and jobs:
        priority = sorted(
            jobs,
            key=lambda j: (
                0 if j.get("startup_match") else 1,
                0 if "remote" in (j.get("work_mode") or "").lower() else 1,
            ),
        )
        fetched = 0
        for job in priority:
            if fetched >= max_description_fetches:
                break
            jid = job.get("linkedin_job_id") or re.search(r"/jobs/view/(\d+)", job["url"])
            jid = jid if isinstance(jid, str) else (jid.group(1) if jid else "")
            if not jid or job.get("description"):
                continue
            desc = _fetch_description(session, jid)
            time.sleep(DELAY)
            if desc:
                job["description"] = desc
                fetched += 1

    imported = _load_import()
    for job in imported:
        if job["url"] not in seen:
            seen.add(job["url"])
            jobs.append(job)

    if not jobs and failures > 5 and not imported:
        print(
            "     (LinkedIn guest API returned no jobs — try LINKEDIN_COOKIE "
            "or add data/europe/linkedin_import.json)"
        )
    return jobs
