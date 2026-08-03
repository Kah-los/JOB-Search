#!/usr/bin/env python3
"""
Aggregator / job-board sources for the Europe search.

NOTE ON SOURCING: the original brief was "employer career pages only, no job
boards". These sources are third-party aggregators, added later on explicit
request to widen thin European coverage. Everything from here is tagged
source_kind="job-board" so it stays distinguishable from direct-employer results.

Only boards that are technically accessible are implemented:
  * Informatics Europe  - public RSS feed (academic informatics posts)
  * EU Remote Jobs      - server-rendered listing page

Deliberately NOT implemented:
  * digital-health-jobs.com - returns HTTP 403 to automated clients
  * BMJ Health Careers      - listings rendered client-side, nothing to parse
  * LinkedIn                - requires authentication and prohibits scraping
  * EURES                   - single-page app, no reachable public API
Those remain worthwhile for manual browsing.
"""
import re

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
TIMEOUT = 25


def _tag(block, name):
    m = re.search(rf"<{name}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", block, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", m.group(1))).strip()


def scrape_informatics_europe():
    """Informatics Europe job platform RSS. Mostly academic computer-science
    posts; the health-context filter downstream keeps only relevant ones."""
    url = ("https://www.informatics-europe.org/services/informatics-job-platform/"
           "feed/rss/informatics-jobs-platform/informatics-jobs.feed")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    jobs = []
    for block in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        link = _tag(block, "link")
        title = _tag(block, "title")
        if not link or not title:
            continue
        jobs.append({
            "employer": "(via Informatics Europe)", "title": title,
            "location": "", "url": link,
            "description": _tag(block, "description")[:4000],
            "salary_text": "", "remote_type": "", "employment_type": "",
            "date_posted": _tag(block, "pubDate")[:16],
            "source_platform": "Informatics Europe",
            "source_kind": "job-board",
        })
    return jobs


def scrape_eu_remote_jobs():
    """EU Remote Jobs - server-rendered listing page (general remote roles;
    health filtering downstream removes the non-health majority)."""
    try:
        r = requests.get("https://euremotejobs.com/", headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        html = r.text
    except Exception:
        return []
    rows = re.findall(
        r'href="(https://euremotejobs\.com/job/[^"]+)"[^>]*>\s*(?:<[^>]*>\s*)*([^<]{5,120})',
        html)
    seen, jobs = set(), []
    for url, title in rows:
        if url in seen:
            continue
        seen.add(url)
        t = re.sub(r"\s+", " ", title).strip()
        if len(t) < 5:
            continue
        # fall back to the URL slug when the anchor text is not the title
        if t.lower() in ("read more", "apply", "view job"):
            t = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        jobs.append({
            "employer": "(via EU Remote Jobs)", "title": t,
            "location": "Remote (Europe)", "url": url, "description": "",
            "salary_text": "", "remote_type": "Remote", "employment_type": "",
            "date_posted": "", "source_platform": "EU Remote Jobs",
            "source_kind": "job-board",
        })
    return jobs


BOARDS = [scrape_informatics_europe, scrape_eu_remote_jobs]


def scrape_all_boards():
    out = []
    for fn in BOARDS:
        try:
            jobs = fn()
        except Exception as e:
            jobs = []
            print(f"  [err] {fn.__name__}: {e}")
        print(f"  {fn.__name__.replace('scrape_', ''):26} +{len(jobs)}")
        out += jobs
    return out


if __name__ == "__main__":
    for j in scrape_all_boards()[:10]:
        print(f"  {j['source_platform']:20} {j['title'][:60]}")
