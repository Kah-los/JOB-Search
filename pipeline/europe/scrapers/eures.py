"""EURES (European Employment Services) API scraper."""

import re
import uuid
import requests

from ..config import SEARCH_QUERIES, SEARCH_QUERIES_BY_BOARD, EURES_LOCATIONS

API = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
DETAIL_API = "https://europa.eu/eures/api/jv-searchengine/public/jv/id/{id}"
HEADERS = {"User-Agent": "JOB-Search-Europe/1.0", "Content-Type": "application/json",
           "Accept": "application/json"}
TIMEOUT = 30

EXP_MAP = {
    "LESS_THAN_1_YEAR_EXPERIENCE": "Junior",
    "BETWEEN_1_AND_2_YEARS_EXPERIENCE": "Junior",
    "BETWEEN_2_AND_5_YEARS_EXPERIENCE": "Mid",
    "MORE_THAN_5_YEARS_EXPERIENCE": "Senior",
}


def _experience_from_codes(codes: list) -> str:
    for c in codes or []:
        if c in EXP_MAP:
            return EXP_MAP[c]
    return "Not specified"


def _work_mode(schedule: list) -> str:
    codes = schedule or []
    if "FULL_TIME" in codes or "PART_TIME" in codes:
        return "On-site"
    return "Not specified"


def _search_page(keyword: str, page: int, locations: list) -> dict:
    payload = {
        "resultsPerPage": 25,
        "page": page,
        "sortSearch": "MOST_RECENT",
        "keywords": [{"keyword": keyword, "specificSearchCode": "EVERYWHERE"}],
        "occupationUris": [],
        "skillUris": [],
        "requiredExperienceCodes": [],
        "positionScheduleCodes": [],
        "sectorCodes": [],
        "educationAndQualificationLevelCodes": [],
        "positionOfferingCodes": [],
        "locationCodes": locations,
        "euresFlagCodes": [],
        "otherBenefitsCodes": [],
        "requiredLanguages": [],
        "sessionId": str(uuid.uuid4()),
        "requestLanguage": "en",
    }
    r = requests.post(API, json=payload, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _fetch_detail(jv_id: str) -> dict:
    try:
        r = requests.get(DETAIL_API.format(id=jv_id), headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def _normalize(jv: dict, detail: dict | None = None) -> dict | None:
    d = detail or jv
    title = d.get("title") or jv.get("title") or "Untitled"
    emp_obj = d.get("employer") or jv.get("employer")
    if isinstance(emp_obj, dict):
        emp = emp_obj.get("name") or "Unknown employer"
    else:
        emp = d.get("employerName") or jv.get("employerName") or "Unknown employer"
    loc_map = jv.get("locationMap") or {}
    country_names = {"SE": "Sweden", "DE": "Germany", "NL": "Netherlands", "DK": "Denmark",
                     "NO": "Norway", "FI": "Finland", "FR": "France", "IE": "Ireland",
                     "UK": "United Kingdom", "GB": "United Kingdom", "AT": "Austria",
                     "CH": "Switzerland", "BE": "Belgium", "ES": "Spain", "IT": "Italy"}
    country = ""
    city = ""
    if loc_map:
        code = list(loc_map.keys())[0]
        country = country_names.get(code, code)
    loc = d.get("positionLocation") or jv.get("positionLocation") or {}
    if isinstance(loc, list) and loc:
        loc = loc[0]
    if isinstance(loc, dict):
        country = loc.get("countryDescription") or country_names.get(loc.get("countryCode", ""), country)
        city = loc.get("cityName") or loc.get("region") or ""
    desc = d.get("jvDescription") or d.get("description") or jv.get("description") or ""
    if isinstance(desc, dict):
        desc = desc.get("text") or ""
    desc = re.sub(r"<[^>]+>", " ", desc or "")
    jv_id = jv.get("id") or d.get("id")
    url = d.get("applicationUrl") or d.get("jvDetailUrl") or ""
    if not url and jv_id:
        url = f"https://europa.eu/eures/portal/jv-se/jv-details/{jv_id}?lang=en"
    if not url:
        return None
    pub = d.get("creationDate") or jv.get("creationDate") or ""
    if isinstance(pub, int):
        from datetime import datetime
        pub = datetime.utcfromtimestamp(pub / 1000).strftime("%Y-%m-%d")
    else:
        pub = str(pub)[:10]
    exp = _experience_from_codes(d.get("requiredExperienceCodes") or jv.get("requiredExperienceCodes") or [])
    return {
        "title": title,
        "employer": emp,
        "country": country,
        "city": city,
        "location": ", ".join(x for x in [city, country] if x),
        "url": url,
        "description": desc,
        "employment_type": "Full-time",
        "date_posted": pub if pub else "",
        "source_platform": "EURES",
        "source_board": "eures",
        "region": "europe",
        "experience_level": exp,
        "work_mode": _work_mode(d.get("positionScheduleCodes")),
    }


def scrape_eures(queries=None, max_pages_per_query=3, locations=None) -> list[dict]:
    queries = queries or SEARCH_QUERIES_BY_BOARD["eures"]
    locations = locations or EURES_LOCATIONS
    jobs, seen = [], set()
    for q in queries:
        for page in range(1, max_pages_per_query + 1):
            try:
                data = _search_page(q, page, locations)
                jvs = data.get("jvs") or []
                if not jvs:
                    break
                for jv in jvs:
                    jid = jv.get("id")
                    if not jid or jid in seen:
                        continue
                    job = _normalize(jv)
                    if job and job["url"] not in seen:
                        seen.add(jid)
                        jobs.append(job)
            except Exception:
                break
    return jobs
