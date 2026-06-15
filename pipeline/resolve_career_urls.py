#!/usr/bin/env python3
"""
Step 2: Resolve real career-page URLs.

Reads data/facilities.json and, for each facility:
  - If it already has a deep career URL (path beyond "/", or a known ATS host),
    verify it returns < 400 and keep it.
  - If it only has a root domain (url_source == "salvaged-domain") or the deep
    URL is dead, probe a prioritized list of common careers paths and keep the
    first that resolves to a careers-like page.

Writes data/facilities_resolved.json adding:
  - resolved_url     best verified careers URL (or None)
  - resolved_status  HTTP status of resolved_url
  - resolve_method   "verified-existing" | "probed-path" | "failed"
  - still_blank      True when nothing resolved AND no domain known (web search needed)

Runs concurrently with short timeouts. Re-runnable (idempotent).
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / "data" / "facilities.json"
OUT = ROOT / "data" / "facilities_resolved.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}
TIMEOUT = 12
CAREER_PATHS = [
    "/careers", "/careers/", "/jobs", "/jobs/", "/careers/job-search",
    "/careers/jobs", "/careers/search-jobs", "/about/careers", "/work-here",
    "/careers/search", "/en/careers", "/about-us/careers", "/employment",
    "/careers/open-positions", "/joinourteam", "/career",
]
CAREER_HINT = re.compile(r"\b(career|careers|job|jobs|join|employ|opportunit|work-?here|hiring|vacanc)",
                         re.I)
KNOWN_ATS = ("myworkdayjobs.com", "icims.com", "taleo.net", "oraclecloud.com",
             "brassring.com", "healthcaresource.com", "selectminds.com",
             "workforcenow.adp.com", "ultipro.com", "smartrecruiters.com",
             "greenhouse.io", "lever.co", "jobvite.com", "successfactors.com",
             "phenompeople.com", "avature.net", "paylocity.com", "applicantpro.com")


def get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.url, (r.text[:4000] if r.text else "")
    except Exception:
        return None, url, ""


def is_career_like(url, body):
    low = url.lower()
    if any(a in low for a in KNOWN_ATS):
        return True
    if CAREER_HINT.search(low):
        return True
    if body and len(CAREER_HINT.findall(body)) >= 3:
        return True
    return False


def hosts_for(domain):
    """Yield apex and www variants for a bare domain."""
    domain = domain.lstrip(".")
    yield f"https://{domain}"
    if not domain.startswith("www."):
        yield f"https://www.{domain}"


def resolve(fac):
    url = fac.get("career_url")
    src = fac.get("url_source")

    # Case A: we have a deep/ATS URL already -> verify
    if url and src in ("hyperlink", "text"):
        status, final, body = get(url)
        if status and status < 400:
            return {**fac, "resolved_url": final, "resolved_status": status,
                    "resolve_method": "verified-existing", "still_blank": False}
        # fall through to probing the domain if verification failed

    # Determine a base domain to probe
    domain = None
    if url:
        p = urlparse(url if "://" in url else "https://" + url)
        domain = p.netloc or None
    if not domain and fac.get("hyperlink"):
        p = urlparse(fac["hyperlink"])
        domain = p.netloc or None

    if not domain:
        return {**fac, "resolved_url": None, "resolved_status": None,
                "resolve_method": "failed", "still_blank": True}

    # If domain is itself an ATS host, just verify root
    if any(a in domain.lower() for a in KNOWN_ATS):
        status, final, body = get(f"https://{domain}")
        if status and status < 400:
            return {**fac, "resolved_url": final, "resolved_status": status,
                    "resolve_method": "verified-existing", "still_blank": False}

    # Case B: probe common careers paths on apex + www
    apex = domain[4:] if domain.startswith("www.") else domain
    for base in hosts_for(apex):
        for path in CAREER_PATHS:
            status, final, body = get(base + path)
            if status and status < 400 and is_career_like(final, body):
                return {**fac, "resolved_url": final, "resolved_status": status,
                        "resolve_method": "probed-path", "still_blank": False}
        # also try the homepage to confirm domain is alive (keeps domain known)
    # nothing career-like found, but domain is known -> not fully blank
    return {**fac, "resolved_url": None, "resolved_status": None,
            "resolve_method": "failed", "still_blank": False}


def main():
    facs = json.loads(IN.read_text())
    results = [None] * len(facs)
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs = {ex.submit(resolve, f): i for i, f in enumerate(facs)}
        done = 0
        for fut in as_completed(futs):
            i = futs[fut]
            results[i] = fut.result()
            done += 1
            if done % 50 == 0:
                print(f"  ...resolved {done}/{len(facs)}")

    OUT.write_text(json.dumps(results, indent=2))

    methods = {}
    for r in results:
        methods[r["resolve_method"]] = methods.get(r["resolve_method"], 0) + 1
    resolved = sum(1 for r in results if r["resolved_url"])
    still_blank = sum(1 for r in results if r["still_blank"])
    print(f"\nWrote {OUT}")
    print(f"Total: {len(results)}")
    print(f"Resolved to a verified career URL: {resolved}")
    print("By method:")
    for k, v in sorted(methods.items(), key=lambda x: -x[1]):
        print(f"  {k:20} {v}")
    print(f"Fully blank (need web search, no domain): {still_blank}")
    print(f"Known domain but no career page found yet: "
          f"{sum(1 for r in results if not r['resolved_url'] and not r['still_blank'])}")


if __name__ == "__main__":
    main()
