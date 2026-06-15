#!/usr/bin/env bash
# Daily re-runnable pipeline. Safe to run on a schedule (cron/launchd).
# Re-scrapes employer career pages, re-scores, regenerates apps + dashboard,
# and prints how many NEW/updated matches appeared (data/new_today.json).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[$(date)] JOB-Search daily run starting"

# 1. (Re)extract facilities from the Excel (cheap, idempotent)
python3 pipeline/extract_facilities.py >/dev/null

# 2. Resolve career URLs only if we don't have a resolved file yet
#    (full re-resolution is slow; run pipeline/resolve_career_urls.py manually to refresh)
if [ ! -f data/facilities_resolved.json ]; then
  python3 pipeline/resolve_career_urls.py
fi

# 3. Scrape API-backed employer career pages (Workday/Greenhouse/Lever/SmartRecruiters)
python3 pipeline/scrape.py --only-api

# 4. Score, filter, tailor, dedup, dashboard
python3 pipeline/run_all.py

NEW=$(python3 -c "import json;print(len(json.load(open('data/new_today.json'))))" 2>/dev/null || echo 0)
echo "[$(date)] Done. New/updated matches today: $NEW"
echo "Dashboard: dashboard/index.html"
