"""Arbetsförmedlingen / Jobtech API scraper (Sweden)."""

import re
import requests
from datetime import datetime

from ..config import SEARCH_QUERIES_BY_BOARD

API = "https://jobsearch.api.jobtechdev.se/search"
HEADERS = {"User-Agent": "JOB-Search-Europe/1.0", "Accept": "application/json"}
TIMEOUT = 25


def _experience_level(title: str, desc: str) -> str:
    blob = f"{title} {desc}".lower()
    if re.search(r"\b(intern|praktik|trainee|graduate program|nyexaminerad)\b", blob):
        return "Internship / Graduate"
    if re.search(r"\b(junior|entry|nybörjare|assistent)\b", blob):
        return "Junior"
    if re.search(r"\b(senior|lead|chef|manager|director|head)\b", blob):
        return "Senior"
    if re.search(r"\b(mid|erfaren|specialist)\b", blob):
        return "Mid"
    return "Not specified"


def _work_mode(desc: str, addr: dict) -> str:
    blob = (desc or "").lower()
    if re.search(r"\b(remote|distans|hemarbete|work from home)\b", blob):
        return "Remote"
    if re.search(r"\b(hybrid|delvis på plats)\b", blob):
        return "Hybrid"
    return "On-site"


def _normalize(hit: dict) -> dict | None:
    emp = hit.get("employer") or {}
    addr = hit.get("workplace_address") or {}
    desc = (hit.get("description") or {}).get("text") or ""
    app = hit.get("application_details") or {}
    url = app.get("url") or app.get("email") or ""
    if not url or not url.startswith("http"):
        return None
    city = addr.get("municipality") or addr.get("city") or ""
    country = "Sweden"
    title = hit.get("headline") or hit.get("label") or "Untitled"
    pub = hit.get("publication_date") or ""
    return {
        "title": title,
        "employer": emp.get("name") or "Unknown employer",
        "country": country,
        "city": city,
        "location": ", ".join(x for x in [city, country] if x),
        "url": url,
        "description": desc,
        "employment_type": "Full-time",
        "date_posted": pub[:10] if pub else "",
        "source_platform": "Jobtech",
        "source_board": "jobtech",
        "region": "europe",
        "experience_level": _experience_level(title, desc),
        "work_mode": _work_mode(desc, addr),
    }


def scrape_jobtech(queries=None, max_per_query=80) -> list[dict]:
    queries = queries or SEARCH_QUERIES_BY_BOARD["jobtech"]
    jobs, seen = [], set()
    for q in queries:
        offset = 0
        while offset < max_per_query:
            try:
                r = requests.get(API, params={"q": q, "limit": 20, "offset": offset},
                                 headers=HEADERS, timeout=TIMEOUT)
                if r.status_code != 200:
                    break
                data = r.json()
                hits = data.get("hits") or []
                if not hits:
                    break
                for hit in hits:
                    job = _normalize(hit)
                    if job and job["url"] not in seen:
                        seen.add(job["url"])
                        jobs.append(job)
                offset += 20
                if len(hits) < 20:
                    break
            except Exception:
                break
    return jobs
