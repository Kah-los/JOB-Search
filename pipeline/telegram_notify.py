#!/usr/bin/env python3
"""
Telegram notifier for the JOB-Search pipeline.

Reads pipeline/telegram_config.json (bot_token, chat_id), data/new_today.json
(matches that are new or updated this run), data/matches.json (all current
matches), and data/jobs_raw.json (for employer count), then sends a formatted
Telegram message with a summary + the top 3 new matches.

Usage:
  python3 telegram_notify.py            # send only if there are new matches
  python3 telegram_notify.py --always   # send even if 0 new (daily heartbeat)
  python3 telegram_notify.py --test      # send a sample message to confirm setup
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


def _config_path():
    """Resolve telegram_config.json — local pipeline/ first, then parent JOB-Search/."""
    here = ROOT / "pipeline" / "telegram_config.json"
    if here.exists():
        return here
    parent = ROOT.parent / "pipeline" / "telegram_config.json"
    if parent.exists():
        return parent
    return here


CFG = _config_path()
NEW = ROOT / "data" / "new_today.json"
MATCHES = ROOT / "data" / "matches.json"
RAW = ROOT / "data" / "jobs_raw.json"
SEEN_EMP = ROOT / "data" / "seen_employers.json"
DASH_PATH = ROOT / "dashboard" / "index.html"
# Published via GitHub Pages (main /docs) behind a hard-to-guess path segment
# stored in pipeline/dashboard_path.txt (single source of truth, shared with daily.sh).
_seg_file = ROOT / "pipeline" / "dashboard_path.txt"
_seg = _seg_file.read_text().strip() if _seg_file.exists() else ""
DASHBOARD_LINK = f"https://kah-los.github.io/JOB-Search/{_seg}/" if _seg \
    else "https://kah-los.github.io/JOB-Search/"


def load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, timeout=20, data={
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    })
    ok = r.json().get("ok", False)
    if not ok:
        print("Telegram send FAILED:", r.text, file=sys.stderr)
    return ok


def fmt_match(i, m):
    return (
        f"{i}. {m.get('title','(untitled)')} — {m.get('employer','')}\n"
        f"   \U0001F4CD {m.get('location') or 'Location N/A'} | "
        f"\U0001F4B0 {m.get('salary','Salary Not Disclosed')}\n"
        f"   ⭐ Fit Score: {m.get('fit_score','?')}/10\n"
        f"   \U0001F517 {m.get('url','')}"
    )


def week_range(today=None):
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())   # Monday of this week
    sunday = monday + timedelta(days=6)
    return monday, sunday


def build_message(new_matches, all_matches, employer_count, new_employers, today=None):
    today = today or date.today()
    monday, sunday = week_range(today)
    top5 = sorted(new_matches, key=lambda m: m.get("fit_score", 0), reverse=True)[:5]
    lines = [
        f"\U0001F514 Weekly Job Search Update — {today.isoformat()}",
        f"\U0001F4C5 Week of {monday.isoformat()} to {sunday.isoformat()}",
        "",
        "\U0001F4CA Weekly Summary:",
        f"- New jobs found this week: {len(new_matches)}",
        f"- Total matches to date: {len(all_matches)}",
        f"- Employers scraped: {employer_count}",
        f"- New employers added: {new_employers}",
        "",
    ]
    if top5:
        lines.append("\U0001F3C6 Top 5 New Matches This Week:")
        lines.append("")
        for i, m in enumerate(top5, 1):
            lines.append(fmt_match(i, m))
            lines.append("")
    else:
        lines.append("No new matching roles this week.")
        lines.append("")
    lines.append(f"\U0001F4C2 View full dashboard: {DASHBOARD_LINK}")
    return "\n".join(lines)


def update_new_employers(raw):
    """Return count of employers not seen in prior runs; persist the union."""
    current = sorted({j.get("employer") for j in raw if j.get("employer")})
    prev = set(load(SEEN_EMP, []))
    new_count = len([e for e in current if e not in prev])
    SEEN_EMP.write_text(json.dumps(current, indent=2))
    return new_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--always", action="store_true", help="send even if 0 new matches")
    ap.add_argument("--test", action="store_true", help="send a sample test message")
    args = ap.parse_args()

    cfg = load(CFG, {})
    token, chat_id = cfg.get("bot_token"), cfg.get("chat_id")
    if not token or not chat_id:
        sys.exit("Missing bot_token/chat_id in pipeline/telegram_config.json")

    if args.test:
        sample_new = [{
            "title": "Sr. Healthcare Data Analyst - Epic", "employer": "Hattiesburg Clinic",
            "location": "Remote", "salary": "Salary Not Disclosed", "fit_score": 9.0,
            "url": "https://example.com/job/123",
        }, {
            "title": "Lead Analyst, Quality Analytics", "employer": "Molina Healthcare",
            "location": "Remote", "salary": "Salary Not Disclosed", "fit_score": 8.8,
            "url": "https://example.com/job/456",
        }, {
            "title": "Clinical & Translational Research Innovation Analyst", "employer": "Tufts Medicine",
            "location": "Remote", "salary": "$107,481", "fit_score": 8.6,
            "url": "https://example.com/job/789",
        }, {
            "title": "Compliance & Privacy Analyst", "employer": "Edward-Elmhurst Health",
            "location": "Hybrid", "salary": "$92,000", "fit_score": 7.4,
            "url": "https://example.com/job/321",
        }, {
            "title": "Revenue Cycle Systems Analyst", "employer": "Montefiore Medical Center",
            "location": "On-site", "salary": "$100,000", "fit_score": 7.9,
            "url": "https://example.com/job/654",
        }]
        msg = "✅ TEST — " + build_message(sample_new, load(MATCHES, []) or sample_new, 29, 2)
        ok = send(token, chat_id, msg)
        print("Test message sent." if ok else "Test send failed.")
        return

    new_matches = load(NEW, [])
    all_matches = load(MATCHES, [])
    raw = load(RAW, [])
    employer_count = len({j.get("employer") for j in raw if j.get("employer")})
    new_employers = update_new_employers(raw)

    # Stay silent on weeks with nothing new (per requirement)
    if not new_matches and not args.always:
        print("No new matches this week — staying silent.")
        return

    ok = send(token, chat_id,
              build_message(new_matches, all_matches, employer_count, new_employers))
    print(f"Sent: {len(new_matches)} new matches notified." if ok else "Send failed.")


if __name__ == "__main__":
    main()
