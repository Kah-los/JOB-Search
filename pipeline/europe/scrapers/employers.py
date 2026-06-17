"""Scrape European employer career pages from data/europe/employers_seed.json.

NOT sourced from the U.S. Epic employer list (facilities_resolved.json).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import scrape as us_scrape  # noqa: E402
from europe.config import DATA, SEARCH_QUERIES  # noqa: E402

SEED = DATA / "employers_seed.json"
scrape_phenom = us_scrape.scrape_phenom


def scrape_eu_employers() -> list[dict]:
    if not SEED.exists():
        return []
    employers = json.loads(SEED.read_text())
    jobs, seen = [], set()
    for emp in employers:
        url = emp.get("career_url")
        if not url:
            continue
        adapter = scrape_phenom if emp.get("ats") == "Phenom" else us_scrape.pick_adapter(url)
        if adapter is us_scrape.scrape_generic:
            continue
        try:
            raw = adapter(url, emp["name"], SEARCH_QUERIES[:8])
        except Exception:
            raw = []
        for j in raw:
            u = j.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            jobs.append({
                "title": j.get("title"),
                "employer": j.get("employer") or emp["name"],
                "country": emp.get("country") or "",
                "city": "",
                "location": j.get("location") or emp.get("country") or "",
                "url": u,
                "description": j.get("description") or "",
                "employment_type": j.get("employment_type") or "",
                "date_posted": j.get("date_posted") or "",
                "source_platform": j.get("source_platform") or "Employer",
                "source_board": "employer",
                "region": "europe",
                "experience_level": "Not specified",
                "work_mode": j.get("remote_type") or "On-site",
            })
    return jobs
