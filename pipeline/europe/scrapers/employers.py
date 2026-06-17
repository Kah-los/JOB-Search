"""Scrape EU employer career pages using existing ATS adapters."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import scrape as us_scrape  # noqa: E402
from europe.config import FACILITY_EU_LABELS, SEARCH_QUERIES  # noqa: E402

FACS = ROOT / "data" / "facilities_resolved.json"


def scrape_eu_employers() -> list[dict]:
    if not FACS.exists():
        return []
    facs = json.loads(FACS.read_text())
    targets = [
        f for f in facs
        if f.get("resolved_url") and f.get("country") in FACILITY_EU_LABELS
    ]
    jobs, seen = [], set()
    for f in targets:
        url = f["resolved_url"]
        adapter = scrape_phenom if f.get("ats") == "Phenom" else us_scrape.pick_adapter(url)
        if adapter is us_scrape.scrape_generic:
            continue
        try:
            raw = adapter(url, f["name"], SEARCH_QUERIES[:8])
        except Exception:
            raw = []
        for j in raw:
            u = j.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            jobs.append({
                "title": j.get("title"),
                "employer": j.get("employer") or f["name"],
                "country": f.get("country") or "",
                "city": "",
                "location": j.get("location") or f.get("country") or "",
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


# Phenom adapter reference
scrape_phenom = us_scrape.scrape_phenom
