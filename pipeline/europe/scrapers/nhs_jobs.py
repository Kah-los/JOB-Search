"""Scrape vacancies from the official NHS Jobs portal (jobs.nhs.uk) per employer."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html",
}
TIMEOUT = 20
BASE = "https://www.jobs.nhs.uk"


def _employer_from_url(url: str) -> str:
    qs = parse_qs(urlparse(url).query)
    raw = qs.get("employer", [""])[0]
    return unquote(raw.replace("+", " "))


def scrape_nhs_jobs(url: str, employer: str, queries=None, cap: int = 80) -> list[dict]:
    employer_name = _employer_from_url(url) or employer
    jobs, seen = [], set()
    page = 1
    while len(jobs) < cap:
        sep = "&" if "?" in url else "?"
        page_url = f"{url}{sep}page={page}" if page > 1 else url
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                break
            html = r.text
        except Exception:
            break

        rows = re.findall(
            r'data-test="search-result-job-title"[^>]*>\s*([^<]+?)\s*</a>\s*</h2>[\s\S]*?'
            r'href="(/candidate/jobadvert/[^"]+)"',
            html,
            flags=re.I,
        )
        if not rows:
            rows = re.findall(
                r'href="(/candidate/jobadvert/[^"]+)"[\s\S]*?'
                r'data-test="search-result-job-title"[^>]*>\s*([^<]+?)\s*</a>',
                html,
                flags=re.I,
            )
            rows = [(title, path) for path, title in rows]

        if not rows:
            break

        for title, path in rows:
            path = unescape(path).replace("&amp;", "&")
            jurl = urljoin(BASE, path)
            if jurl in seen:
                continue
            seen.add(jurl)
            clean_title = unescape(re.sub(r"\s+", " ", title)).strip()
            jobs.append({
                "employer": employer_name,
                "title": clean_title,
                "location": "UK",
                "url": jurl,
                "description": "",
                "salary_text": "",
                "remote_type": "",
                "employment_type": "",
                "date_posted": "",
                "source_platform": "NHS Jobs",
            })
            if len(jobs) >= cap:
                break

        if 'rel="next"' not in html and f"page={page + 1}" not in html:
            break
        page += 1
        if page > 10:
            break
    return jobs
