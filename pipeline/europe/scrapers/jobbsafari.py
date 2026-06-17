"""Jobbsafari.se scraper (Sweden / Nordic)."""

from __future__ import annotations

import json
import re
from urllib.parse import quote

import requests

from ..config import SEARCH_QUERIES

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html",
}
TIMEOUT = 20
BASE = "https://jobbsafari.se"


def _job_url(entry: dict) -> str:
    slug = entry.get("slug") or ""
    if slug:
        return f"{BASE}/lediga-jobb/{slug}"
    pk = entry.get("pk")
    if pk:
        return f"{BASE}/lediga-jobb/{pk}"
    return ""


def _apply_url(entry: dict) -> str:
    apply = entry.get("apply") or {}
    href = apply.get("href") or ""
    if href.startswith("http") or href.startswith("mailto:"):
        return href
    return _job_url(entry)


def _location(entry: dict) -> str:
    locs = entry.get("locations") or []
    if not locs:
        return "Sweden"
    names = [loc.get("name") or (loc.get("area") or {}).get("name") for loc in locs]
    names = [n for n in names if n]
    return ", ".join(names) if names else "Sweden"


def scrape_jobbsafari(queries=None, max_per_query: int = 40) -> list[dict]:
    queries = queries or SEARCH_QUERIES[:10]
    jobs, seen = [], set()
    for q in queries:
        try:
            r = requests.get(
                f"{BASE}/lediga-jobb",
                params={"q": q},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
            if not m:
                continue
            data = json.loads(m.group(1))
            entries = (data.get("props", {}).get("pageProps", {}).get("jobEntries") or {}).get("results") or []
            for entry in entries[:max_per_query]:
                url = _apply_url(entry)
                if not url or url in seen:
                    continue
                seen.add(url)
                company = (entry.get("company") or {}).get("name") or "Unknown employer"
                jobs.append({
                    "employer": company,
                    "title": entry.get("title") or "Untitled",
                    "location": _location(entry),
                    "url": url,
                    "description": "",
                    "salary_text": "",
                    "remote_type": "",
                    "employment_type": "",
                    "date_posted": (entry.get("startDate") or "")[:10],
                    "source_platform": "Jobbsafari",
                })
        except Exception:
            continue
    return jobs
