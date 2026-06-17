"""Jobindex.dk scraper (Denmark)."""

from __future__ import annotations

import json
import re
from html import unescape
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
BASE = "https://www.jobindex.dk"


def _parse_job_posting(html: str, fallback_url: str) -> dict | None:
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "JobPosting":
            continue
        org = data.get("hiringOrganization") or {}
        employer = org.get("name") if isinstance(org, dict) else str(org)
        loc = data.get("jobLocation") or {}
        location = "Denmark"
        if isinstance(loc, dict):
            addr = loc.get("address") or {}
            if isinstance(addr, dict):
                location = ", ".join(
                    x for x in [addr.get("addressLocality"), addr.get("addressRegion"), "Denmark"] if x
                )
        return {
            "employer": employer or "Unknown employer",
            "title": (data.get("title") or "Untitled").strip(),
            "location": location,
            "url": data.get("url") or fallback_url,
            "description": (data.get("description") or "")[:2000],
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": (data.get("datePosted") or "")[:10],
            "source_platform": "Jobindex.dk",
        }
    title_m = re.search(r"<h1[^>]*>\s*Job ad:\s*([^<]+)\s*</h1>", html, re.I)
    if title_m:
        return {
            "employer": "Unknown employer",
            "title": unescape(title_m.group(1).strip()),
            "location": "Denmark",
            "url": fallback_url,
            "description": "",
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": "",
            "source_platform": "Jobindex.dk",
        }
    return None


def scrape_jobindex(queries=None, max_per_query: int = 25) -> list[dict]:
    queries = queries or SEARCH_QUERIES[:8]
    jobs, seen = [], set()
    for q in queries:
        try:
            r = requests.get(
                f"{BASE}/jobsoegning",
                params={"q": q},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue
            text = r.text.replace("\\/", "/")
            ids = sorted(set(re.findall(r"/vis-job/(h\d+)", text)))
            for tid in ids[:max_per_query]:
                jurl = f"{BASE}/vis-job/{tid}"
                if jurl in seen:
                    continue
                try:
                    detail = requests.get(jurl, headers=HEADERS, timeout=TIMEOUT)
                    if detail.status_code != 200:
                        continue
                    job = _parse_job_posting(detail.text, jurl)
                    if not job:
                        continue
                    seen.add(jurl)
                    jobs.append(job)
                except Exception:
                    continue
        except Exception:
            continue
    return jobs
