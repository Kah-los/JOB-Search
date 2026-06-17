#!/usr/bin/env python3
"""
Europe Jobs scraper — employer career pages + approved EU job boards only.
Never mixes with U.S. data. Forbidden: Indeed, Glassdoor, Jooble, ZipRecruiter.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))
from europe.config import DATA, JOBS_RAW, FORBIDDEN_SOURCES
from europe.scrapers.jobtech import scrape_jobtech
from europe.scrapers.eures import scrape_eures
from europe.scrapers.employers import scrape_eu_employers

DATA.mkdir(parents=True, exist_ok=True)

US_LOC = re.compile(
    r"\b(united states|u\.s\.a?|usa|new york|california|texas|florida|"
    r"remote.*united states|remote.*usa)\b", re.I)


def is_excluded_country(text: str) -> bool:
    return bool(re.search(
        r"\b(united states|u\.s\.a?|usa|canada)\b", text, re.I))


def is_europe_location(job: dict) -> bool:
    loc = " ".join([
        job.get("location") or "",
        job.get("country") or "",
        job.get("city") or "",
        job.get("description") or ""[:500],
    ]).lower()
    if is_excluded_country(loc):
        return False
    if US_LOC.search(loc):
        return False
    if re.search(r"\bremote\b", loc, re.I) and is_excluded_country(loc):
        return False
    return True


def is_valid_source(job: dict) -> bool:
    url = (job.get("url") or "").lower()
    board = (job.get("source_board") or "").lower()
    if any(f in url for f in FORBIDDEN_SOURCES):
        return False
    if any(f in board for f in FORBIDDEN_SOURCES):
        return False
    if not url.startswith("http"):
        return False
    return True


def dedupe(jobs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for j in jobs:
        key = (j.get("url") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


def main():
    print("Europe Jobs scrape starting…")
    all_jobs = []

    print("  → Arbetsförmedlingen (Jobtech / Sweden)…")
    jt = scrape_jobtech()
    print(f"     +{len(jt)} jobs")
    all_jobs.extend(jt)

    print("  → EURES (EU/EEA)…")
    eu = scrape_eures()
    print(f"     +{len(eu)} jobs")
    all_jobs.extend(eu)

    print("  → EU employer career pages…")
    emp = scrape_eu_employers()
    print(f"     +{len(emp)} jobs")
    all_jobs.extend(emp)

    filtered = [j for j in all_jobs if is_valid_source(j) and is_europe_location(j)]
    jobs = dedupe(filtered)
    JOBS_RAW.write_text(json.dumps(jobs, indent=2))
    print(f"\nWrote {JOBS_RAW}: {len(jobs)} Europe jobs "
          f"(filtered from {len(all_jobs)} raw)")


if __name__ == "__main__":
    main()
