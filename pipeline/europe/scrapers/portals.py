"""Direct employer portal scrapers for EU healthcare sites (RSS, Karolinska, Region Stockholm)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
}
TIMEOUT = 20


def scrape_rss(url: str, employer: str, queries=None, cap: int = 50) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
    except Exception:
        return []

    jobs = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        jobs.append({
            "employer": employer,
            "title": title,
            "location": "",
            "url": link,
            "description": (item.findtext("description") or "")[:2000],
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": (item.findtext("pubDate") or "")[:16],
            "source_platform": "Employer RSS",
        })
        if len(jobs) >= cap:
            break
    return jobs


def scrape_karolinska(url: str, employer: str, queries=None, cap: int = 80) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        html = r.text
    except Exception:
        return []

    jobs, seen = [], set()
    for path, title in re.findall(
        r'href="(/jobba-hos-oss/lediga-jobb/lediga-jobb-detaljsida/\?positionId=\d+)"[^>]*>([^<]+)</a>',
        html,
        flags=re.I,
    ):
        jurl = urljoin("https://www.karolinska.se", unescape(path))
        if jurl in seen:
            continue
        seen.add(jurl)
        jobs.append({
            "employer": employer,
            "title": unescape(re.sub(r"\s+", " ", title)).strip(),
            "location": "Stockholm, Sweden",
            "url": jurl,
            "description": "",
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": "",
            "source_platform": "Karolinska",
        })
        if len(jobs) >= cap:
            break
    return jobs


def scrape_region_stockholm(url: str, employer: str, queries=None, cap: int = 80) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        html = r.text
    except Exception:
        return []

    jobs, seen = [], set()
    for path in sorted(set(re.findall(r"(/jobb/lediga-jobb/[^\"\s#]+/)", html))):
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) < 4:
            continue
        slug = parts[-1]
        title = unescape(slug.replace("-", " ")).strip().title()
        jurl = urljoin("https://www.regionstockholm.se", path)
        if jurl in seen:
            continue
        seen.add(jurl)
        jobs.append({
            "employer": employer,
            "title": title,
            "location": "Stockholm, Sweden",
            "url": jurl,
            "description": "",
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": "",
            "source_platform": "Region Stockholm",
        })
        if len(jobs) >= cap:
            break
    return jobs


def scrape_varbi(url: str, employer: str, queries=None, cap: int = 120) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        html = r.text
    except Exception:
        return []

    host = urlparse(url).netloc
    locale = "se"
    m = re.search(r"varbi\.com/([a-z]{2})/", url, re.I)
    if m:
        locale = m.group(1).lower()

    jobs, seen = [], set()
    for match in re.finditer(
        r'what:job/jobID:(\d+)[^"]*"[^>]*>\s*([^<]{8,160}?)\s*</',
        html,
        flags=re.I,
    ):
        job_id = match.group(1)
        clean = unescape(re.sub(r"\s+", " ", match.group(2)).strip())
        if job_id in seen or re.match(r"\d{4}-\d{2}-\d{2}", clean) or len(clean) < 12:
            continue
        seen.add(job_id)
        jobs.append({
            "employer": employer,
            "title": clean,
            "location": "",
            "url": f"https://{host}/{locale}/what:job/jobID:{job_id}/where:1/",
            "description": "",
            "salary_text": "",
            "remote_type": "",
            "employment_type": "",
            "date_posted": "",
            "source_platform": "Varbi",
        })
        if len(jobs) >= cap:
            break
    return jobs
