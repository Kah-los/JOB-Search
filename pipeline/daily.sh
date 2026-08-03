#!/usr/bin/env bash
# Re-runnable pipeline. Scheduled WEEKLY via launchd (Mondays 08:00) —
# see ~/Library/LaunchAgents/com.jobsearch.weekly.plist. Safe to run manually too.
# Scrapes employer career pages, folds in discovered URLs, re-scores, regenerates
# apps + dashboard, publishes the dashboard to GitHub Pages, then sends a weekly
# Telegram summary if any new matches appeared (silent otherwise).
set -uo pipefail
cd "$(dirname "$0")/.."

# --- interpreter + dependency preflight -------------------------------------
# launchd/cron run with a minimal PATH that excludes /usr/local/bin, so a bare
# `python3` resolves to Apple's system Python which lacks requests/openpyxl.
# Pin an interpreter that actually has the deps, and abort loudly if none does.
PY=""
for cand in /usr/local/bin/python3 \
            /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
            /opt/homebrew/bin/python3 \
            "$(command -v python3 || true)"; do
  [ -x "$cand" ] || continue
  if "$cand" -c "import requests, openpyxl" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "[$(date)] FATAL: no python3 with requests+openpyxl found. Pipeline aborted."
  echo "  Fix: /usr/local/bin/python3 -m pip install requests openpyxl"
  exit 1
fi
echo "[$(date)] using interpreter: $PY"

echo "[$(date)] JOB-Search weekly run starting"

# 1. (Re)extract facilities from the Excel (cheap, idempotent)
"$PY" pipeline/extract_facilities.py >/dev/null

# 2. Resolve career URLs once (slow); fold in any web-discovered URLs every run
if [ ! -f data/facilities_resolved.json ]; then
  "$PY" pipeline/resolve_career_urls.py
fi
"$PY" pipeline/merge_discovered.py >/dev/null

# 3. Scrape ALL postings from API-backed employer career pages
"$PY" pipeline/scrape.py --only-api

# 4. Enrich relevant postings with full descriptions (REQUIRED before scoring)
"$PY" pipeline/enrich.py

# 5. Score, filter, tailor, dedup, regenerate dashboard
"$PY" pipeline/run_all.py

# 6. Publish dashboard to the secret /docs path for GitHub Pages, push so it updates
SEG=$(cat pipeline/dashboard_path.txt 2>/dev/null || echo "")
mkdir -p "docs/$SEG"
cp dashboard/index.html "docs/$SEG/index.html"
if command -v git >/dev/null 2>&1; then
  git add "docs/$SEG/index.html" docs/robots.txt >/dev/null 2>&1 || true
  git commit -m "Weekly dashboard update $(date +%Y-%m-%d)" >/dev/null 2>&1 || true
  git push >/dev/null 2>&1 || echo "[warn] git push skipped (run 'gh auth login' once to enable)"
fi

NEW=$("$PY" -c "import json;print(len(json.load(open('data/new_today.json'))))" 2>/dev/null || echo 0)
echo "[$(date)] Done. New matches this run: $NEW"
echo "Dashboard: dashboard/index.html  |  https://kah-los.github.io/JOB-Search/$(cat pipeline/dashboard_path.txt 2>/dev/null || echo '')/"

# 7. Telegram notification — stays silent unless there are new matches
# --always: send every week even with 0 new matches, so a silent week is
# distinguishable from a broken pipeline (this outage went unnoticed for 7 weeks).
"$PY" pipeline/telegram_notify.py --always || echo "[warn] telegram notify failed"
