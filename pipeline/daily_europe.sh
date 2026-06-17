#!/usr/bin/env bash
# Europe Jobs pipeline — fully separate from U.S. job search.
# Scrapes Arbetsförmedlingen, EURES, and EU employer career pages only.
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date)] Europe Jobs pipeline starting"

python3 pipeline/europe/scrape.py
python3 pipeline/europe/run_all.py

SEG=$(cat pipeline/dashboard_path_europe.txt 2>/dev/null || echo "europe-jobs")
mkdir -p "docs/$SEG"
cp dashboard/europe/index.html "docs/$SEG/index.html"

if command -v git >/dev/null 2>&1; then
  git add "docs/$SEG/index.html" dashboard/europe/index.html data/europe/ pipeline/europe/ pipeline/profile_europe.json pipeline/dashboard_path_europe.txt 2>/dev/null || true
  git commit -m "Europe Jobs dashboard update $(date +%Y-%m-%d)" >/dev/null 2>&1 || true
  git push >/dev/null 2>&1 || echo "[warn] git push skipped"
fi

NEW=$(python3 -c "import json;print(len(json.load(open('data/europe/new_today.json'))))" 2>/dev/null || echo 0)
echo "[$(date)] Done. Europe matches: $(python3 -c "import json;print(len(json.load(open('data/europe/matches.json'))))" 2>/dev/null || echo 0) | New: $NEW"
echo "Dashboard: https://kah-los.github.io/JOB-Search/$SEG/"
