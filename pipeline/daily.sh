#!/usr/bin/env bash
# Re-runnable pipeline. Scheduled WEEKLY via launchd (Mondays 08:00) —
# see ~/Library/LaunchAgents/com.jobsearch.weekly.plist. Safe to run manually too.
# Scrapes employer career pages, folds in discovered URLs, re-scores, regenerates
# apps + dashboard, publishes the dashboard to GitHub Pages, then sends a weekly
# Telegram summary if any new matches appeared (silent otherwise).
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date)] JOB-Search weekly run starting"

# 1. (Re)extract facilities from the Excel (cheap, idempotent)
python3 pipeline/extract_facilities.py >/dev/null

# 2. Resolve career URLs once (slow); fold in any web-discovered URLs every run
if [ ! -f data/facilities_resolved.json ]; then
  python3 pipeline/resolve_career_urls.py
fi
python3 pipeline/merge_discovered.py >/dev/null

# 3. Scrape ALL postings from API-backed employer career pages
python3 pipeline/scrape.py --only-api

# 4. Enrich relevant postings with full descriptions (REQUIRED before scoring)
python3 pipeline/enrich.py

# 5. Score, filter, tailor, dedup, regenerate dashboard
python3 pipeline/run_all.py

# 6. Publish dashboard to the secret /docs path for GitHub Pages, push so it updates
SEG=$(cat pipeline/dashboard_path.txt 2>/dev/null || echo "")
mkdir -p "docs/$SEG"
cp dashboard/index.html "docs/$SEG/index.html"
if command -v git >/dev/null 2>&1; then
  git add "docs/$SEG/index.html" docs/robots.txt >/dev/null 2>&1 || true
  git commit -m "Weekly dashboard update $(date +%Y-%m-%d)" >/dev/null 2>&1 || true
  git push >/dev/null 2>&1 || echo "[warn] git push skipped (run 'gh auth login' once to enable)"
fi

NEW=$(python3 -c "import json;print(len(json.load(open('data/new_today.json'))))" 2>/dev/null || echo 0)
echo "[$(date)] Done. New matches this run: $NEW"
echo "Dashboard: dashboard/index.html  |  https://kah-los.github.io/JOB-Search/"

# 7. Telegram notification — stays silent unless there are new matches
python3 pipeline/telegram_notify.py || echo "[warn] telegram notify failed"
