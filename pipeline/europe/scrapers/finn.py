"""Finn.no / Arbeidsplassen.no job search (official Norwegian listings API)."""

from __future__ import annotations

import requests

from ..config import SEARCH_QUERIES

API = "https://arbeidsplassen.nav.no/stillinger/api/search"
BASE = "https://arbeidsplassen.nav.no/stillinger/stilling"
HEADERS = {
    "User-Agent": "JOB-Search-Europe/1.0",
    "Accept": "application/json",
}
TIMEOUT = 25


def _location(hit: dict) -> str:
    locs = hit.get("locationList") or []
    if not locs:
        return "Norway"
    loc = locs[0]
    parts = [loc.get("city"), loc.get("municipal"), loc.get("county"), "Norway"]
    return ", ".join(p for p in parts if p)


def _employer(hit: dict) -> str:
    emp = hit.get("employer") or {}
    return emp.get("name") or hit.get("businessName") or "Unknown employer"


def scrape_finn(queries=None, max_per_query: int = 60) -> list[dict]:
    """Norwegian jobs via Arbeidsplassen search API (same vacancy pool as Finn.no)."""
    queries = queries or SEARCH_QUERIES[:10]
    jobs, seen = [], set()
    for q in queries:
        offset = 0
        while offset < max_per_query:
            try:
                r = requests.get(
                    API,
                    params={"q": q, "from": offset, "size": 25},
                    headers=HEADERS,
                    timeout=TIMEOUT,
                )
                if r.status_code != 200:
                    break
                hits = (r.json().get("hits") or {}).get("hits") or []
                if not hits:
                    break
                for item in hits:
                    src = item.get("_source") or {}
                    uuid = src.get("uuid") or item.get("_id")
                    if not uuid:
                        continue
                    jurl = f"{BASE}/{uuid}"
                    if jurl in seen:
                        continue
                    seen.add(jurl)
                    jobs.append({
                        "employer": _employer(src),
                        "title": src.get("title") or "Untitled",
                        "location": _location(src),
                        "url": jurl,
                        "description": (src.get("generatedSearchMetadata") or {}).get("shortSummary", ""),
                        "salary_text": "",
                        "remote_type": "",
                        "employment_type": "",
                        "date_posted": (src.get("published") or "")[:10],
                        "source_platform": "Finn.no",
                    })
                offset += 25
                if len(hits) < 25:
                    break
            except Exception:
                break
    return jobs
