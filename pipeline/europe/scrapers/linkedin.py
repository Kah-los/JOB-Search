"""LinkedIn Jobs guest API scraper — full Europe coverage for all target titles.

Uses LinkedIn public guest endpoints (no login):
  /jobs-guest/jobs/api/seeMoreJobPostings/search
  /jobs-guest/jobs/api/jobPosting/{id}

Searches every EU/EEA target title across all European countries (remote,
hybrid, and on-site). Optional LINKEDIN_COOKIE for richer results.
"""

from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from pathlib import Path

import requests

from ..config import DATA
from ..target_titles import ALL_TARGET_TITLES, SEARCH_QUERIES

BASE = "https://www.linkedin.com"
SEARCH_URL = f"{BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_URL = f"{BASE}/jobs-guest/jobs/api/jobPosting"
IMPORT_PATH = DATA / "linkedin_import.json"
CHECKPOINT_PATH = DATA / "linkedin_checkpoint.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 20)
DELAY = 0.45
PAGE_SIZE = 25

# LinkedIn geoId per EU/EEA + UK + CH country
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
    {"location": "Belgium", "geo_id": "100565514", "country": "Belgium"},
    {"location": "Austria", "geo_id": "103883259", "country": "Austria"},
    {"location": "Spain", "geo_id": "105646813", "country": "Spain"},
    {"location": "Italy", "geo_id": "103350119", "country": "Italy"},
    {"location": "Portugal", "geo_id": "101174742", "country": "Portugal"},
    {"location": "Poland", "geo_id": "105072130", "country": "Poland"},
    {"location": "Czech Republic", "geo_id": "104508036", "country": "Czech Republic"},
    {"location": "Greece", "geo_id": "104677530", "country": "Greece"},
    {"location": "Hungary", "geo_id": "100288700", "country": "Hungary"},
    {"location": "Romania", "geo_id": "106670623", "country": "Romania"},
    {"location": "Bulgaria", "geo_id": "105333783", "country": "Bulgaria"},
    {"location": "Croatia", "geo_id": "104688944", "country": "Croatia"},
    {"location": "Slovenia", "geo_id": "106137033", "country": "Slovenia"},
    {"location": "Slovakia", "geo_id": "106061489", "country": "Slovakia"},
    {"location": "Lithuania", "geo_id": "101464403", "country": "Lithuania"},
    {"location": "Latvia", "geo_id": "104341318", "country": "Latvia"},
    {"location": "Estonia", "geo_id": "102425227", "country": "Estonia"},
    {"location": "Luxembourg", "geo_id": "104042105", "country": "Luxembourg"},
    {"location": "Malta", "geo_id": "100961908", "country": "Malta"},
    {"location": "Cyprus", "geo_id": "106774002", "country": "Cyprus"},
    {"location": "Iceland", "geo_id": "105238872", "country": "Iceland"},
]

COUNTRY_ALIASES = {
    "United Kingdom": "UK",
    "Czech Republic": "Czech Republic",
    "Czechia": "Czech Republic",
}

DATE_RE = re.compile(
    r'job-search-card__listdate[^>]*--new[^>]*>\s*([^<]+?)\s*</time>|'
    r'job-search-card__listdate[^>]*>\s*([^<]+?)\s*</time>',
    re.I | re.S,
)
DESC_RE = re.compile(
    r'<div[^>]+class="[^"]*description[^"]*"[^>]*>([\s\S]*?)</div>',
    re.I,
)


def _linkedin_queries() -> list[str]:
    seen, out = set(), []
    for q in list(ALL_TARGET_TITLES) + list(SEARCH_QUERIES):
        key = (q or "").lower().strip()
        if not key or key in seen or len(q) > 90:
            continue
        seen.add(key)
        out.append(q)
    return out


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
    country_names = [loc["location"] for loc in EU_LOCATIONS] + ["UK", "Czechia"]
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
        date_posted = unescape((date_m.group(1) or date_m.group(2) or "").strip()) if date_m else ""

        work_mode = "Remote" if re.search(r"\bremote\b", location, re.I) else (
            "Hybrid" if re.search(r"\bhybrid\b", location, re.I) else "On-site"
        )
        country = COUNTRY_ALIASES.get(default_country, default_country)
        for c in country_names:
            if re.search(rf"\b{re.escape(c)}\b", location, re.I):
                country = COUNTRY_ALIASES.get(c, c)
                if country == "United Kingdom":
                    country = "UK"
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
        if len(chunk) > 80:
            return chunk[:2500]
    sm = re.search(r"show-more-less-html__markup[^>]*>([\s\S]*?)</div>", html, re.I)
    return _strip_html(sm.group(1))[:2500] if sm else ""


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
    max_pages: int = 1,
) -> list[dict]:
    jobs = []
    for page in range(max_pages):
        params = {
            "keywords": keywords,
            "location": location,
            "geoId": geo_id,
            "start": page * PAGE_SIZE,
            "f_TPR": "r2592000",
            "f_JT": "F",
        }
        html = _fetch(session, SEARCH_URL, params)
        time.sleep(DELAY)
        if not html:
            break
        batch = _parse_cards(html, default_country=country)
        if not batch:
            break
        jobs.extend(batch)
    return jobs


def _save_checkpoint(jobs: list[dict], seen: set[str], done: int) -> None:
    CHECKPOINT_PATH.write_text(json.dumps({
        "done": done,
        "jobs": jobs,
        "seen": list(seen),
    }))


def _load_checkpoint() -> tuple[list[dict], set[str], int]:
    if not CHECKPOINT_PATH.exists():
        return [], set(), 0
    try:
        raw = json.loads(CHECKPOINT_PATH.read_text())
        return raw.get("jobs", []), set(raw.get("seen", [])), int(raw.get("done", 0))
    except Exception:
        return [], set(), 0


def scrape_linkedin(
    *,
    fetch_descriptions: bool = True,
    max_description_fetches: int = 120,
    resume: bool = True,
) -> list[dict]:
    session = _session()
    queries = _linkedin_queries()
    jobs, seen, skip = _load_checkpoint() if resume else ([], set(), 0)
    total_searches = len(EU_LOCATIONS) * len(queries)
    done = 0

    if skip:
        print(f"     (resuming LinkedIn from search {skip + 1}/{total_searches}, {len(jobs)} jobs cached)")

    print(f"     ({len(queries)} titles × {len(EU_LOCATIONS)} countries = {total_searches} searches)")

    for loc in EU_LOCATIONS:
        for q in queries:
            done += 1
            if done <= skip:
                continue
            if done % 50 == 0:
                print(f"     … LinkedIn {done}/{total_searches} searches, {len(jobs)} jobs so far")
                _save_checkpoint(jobs, seen, done)
            batch = _search(
                session,
                keywords=q,
                location=loc["location"],
                geo_id=loc["geo_id"],
                country=loc["country"],
            )
            for job in batch:
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                job["search_query"] = q
                job["search_country"] = loc["country"]
                jobs.append(job)

    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink(missing_ok=True)

    if fetch_descriptions and jobs:
        fetched = 0
        for job in jobs:
            if fetched >= max_description_fetches:
                break
            jid = job.get("linkedin_job_id") or ""
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

    if not jobs and not imported:
        print(
            "     (LinkedIn guest API returned no jobs — try LINKEDIN_COOKIE "
            "or add data/europe/linkedin_import.json)"
        )
    return jobs
