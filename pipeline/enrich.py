#!/usr/bin/env python3
"""
Step 3b: Enrich title-relevant jobs with full descriptions.

The Workday list API returns no description/salary, so we fetch each job's
detail via the Workday CXS job endpoint and fill in description, salary_text,
remote/location, and employment_type. Only title-relevant jobs are enriched
(keeps fetch volume sane). Writes data/jobs_enriched.json.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "jobs_raw.json"
OUT = ROOT / "data" / "jobs_enriched.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
           "Accept": "application/json"}
TIMEOUT = 20

# BROAD relevance across all 19 domains. Match on transferable role nouns +
# healthcare-info context, not just Epic/EHR. The score step does the real ranking;
# this gate only decides what to fetch a description for.
TITLE_INCLUDE = re.compile(
    r"(informatics|health information|\bhim\b|\bhims\b|\bcdi\b|clinical document|"
    r"medical record|\behr\b|\bemr\b|epic|interoperab|health information exchange|\bhie\b|"
    r"\bhl7\b|\bfhir\b|analyst|analytics|business intelligence|\bbi\b|reporting|"
    r"data (quality|integrity|governance|steward|management|analy)|decision support|"
    r"compliance|regulatory|privacy|governance|hipaa|audit|"
    r"revenue cycle|revenue integrity|coding|coder|billing|reimbursement|charge|"
    r"population health|quality|patient safety|accreditation|performance improvement|"
    r"project (manager|coordinator|lead)|program (manager|coordinator)|\bpmo\b|"
    r"operations (manager|analyst|coordinator|specialist)|process improvement|"
    r"case management|care coordination|utilization|"
    r"business analyst|systems analyst|application analyst|clinical systems|"
    r"informatics|training|educator|education specialist|"
    r"consultant|advisory|digital health|transformation|policy|registry|"
    r"document (specialist|control)|records (specialist|manager|coordinator)|"
    # generic mid-career role nouns — admitted broadly; scoring + healthcare-context
    # gate + >=6 threshold decide relevance. (User: stop excluding these titles.)
    r"\bcoordinator\b|\bspecialist\b|\bassociate\b|\btechnician\b|\bofficer\b|"
    r"\badministrator\b|\banalyst\b|\bmanager\b|\bsupervisor\b|\bdirector\b)", re.I)
# Hard non-matches: clinical/manual/unrelated/pure-engineering — never enrich.
TITLE_EXCLUDE = re.compile(
    r"\((?:rn|np|aprn|lpn|crna|pa)\)|(?:"
    r"registered nurse|nurse practitioner|"
    r"\bnurse\b|physician|surgeon|pharmacist|\bpharmd\b|respiratory therapist|"
    r"physical therapist|occupational therapist|phlebotom|sonograph|radiolog|"
    r"technologist|\bcna\b|caregiver|dietitian|social worker|chaplain|"
    r"housekeep|food service|nutrition service|\bcook\b|janitor|custodian|"
    r"security officer|valet|driver|maintenance|groundskeep|cafeteria|"
    r"software engineer|backend|back-end|front-end|frontend|devops|"
    r"site reliability|infrastructure engineer|network engineer|cloud engineer|"
    r"full stack|full-stack|web developer|mobile developer|\bsre\b|"
    r"plumber|electrician|hvac|carpenter|welder|warehouse|"
    # clinical/manual technician & coordinator variants that aren't health-info roles
    r"patient care tech|surgical tech|pharmacy tech|sterile processing|"
    r"anesthesia tech|ekg tech|telemetry tech|monitor tech|nursing assistant|"
    r"medical assistant|patient access representative|unit (secretary|coordinator)|"
    r"scheduling coordinator|dietary|transport|environmental service|"
    r"database administrator|systems administrator|network administrator|"
    r"\bdba\b|linux administrator|server administrator)", re.I)


def title_relevant(title):
    t = title or ""
    if TITLE_EXCLUDE.search(t):
        return False
    return bool(TITLE_INCLUDE.search(t))

WD_VIEW_RE = re.compile(r"https?://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/([^/]+)(/.*)")


def workday_detail_url(view_url):
    m = WD_VIEW_RE.match(view_url)
    if not m:
        return None
    tenant, dc, site, ext = m.groups()
    return f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{ext}"


ORC_JOB_RE = re.compile(r"https?://([^/]+)/hcmUI/CandidateExperience/[^/]+/sites/([^/]+)/job/([^/?#]+)")
ULTI_DETAIL_RE = re.compile(r"https?://([^/]+)/([^/]+)/JobBoard/([0-9a-f\-]+)/OpportunityDetail\?opportunityId=(\d+)", re.I)


def enrich_orc(job):
    m = ORC_JOB_RE.match(job["url"])
    if not m:
        return job
    host, site, jid = m.groups()
    api = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
           f'?expand=all&finder=ById;Id="{jid}",siteNumber={site}')
    try:
        r = requests.get(api, headers=HEADERS, timeout=TIMEOUT)
        items = (r.json() or {}).get("items", [])
        if not items:
            return job
        d = items[0]
        desc = " ".join(filter(None, [d.get("ExternalDescriptionStr", ""),
                                       d.get("ExternalQualificationsStr", ""),
                                       d.get("ExternalResponsibilitiesStr", "")]))
        job = {**job}
        job["description"] = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", desc)).strip()[:8000]
        job["location"] = d.get("PrimaryLocation") or job.get("location")
        job["date_posted"] = d.get("PostedDate") or job.get("date_posted")
    except Exception:
        pass
    return job


def enrich_ultipro(job):
    m = ULTI_DETAIL_RE.match(job["url"])
    if not m:
        return job
    host, comp, guid, oid = m.groups()
    api = f"https://{host}/{comp}/JobBoard/{guid}/JobBoardView/LoadOpportunity"
    try:
        r = requests.post(api, headers={**HEADERS, "Content-Type": "application/json"},
                          json={"opportunityId": int(oid)}, timeout=TIMEOUT)
        d = r.json() or {}
        desc = d.get("Description") or d.get("Responsibilities") or ""
        job = {**job}
        job["description"] = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", desc)).strip()[:8000]
        job["location"] = d.get("LocationDescription") or job.get("location")
    except Exception:
        pass
    return job


def enrich_one(job):
    plat = job.get("source_platform")
    if plat == "OracleORC" and not job.get("description", "").strip():
        return enrich_orc(job)
    if plat == "UltiPro" and not job.get("description", "").strip():
        return enrich_ultipro(job)
    if plat != "Workday":
        return job  # other platforms already carry descriptions
    detail = workday_detail_url(job["url"])
    if not detail:
        return job
    try:
        r = requests.get(detail, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return job
        info = (r.json() or {}).get("jobPostingInfo", {}) or {}
    except Exception:
        return job
    desc = re.sub("<[^>]+>", " ", info.get("jobDescription", "") or "")
    desc = re.sub(r"\s+", " ", desc).strip()
    job = {**job}
    job["description"] = desc[:8000]
    job["location"] = info.get("location") or job.get("location")
    job["employment_type"] = info.get("timeType") or job.get("employment_type")
    job["remote_type"] = ("Remote" if info.get("remoteType") and "remote" in
                          str(info.get("remoteType")).lower() else job.get("remote_type"))
    job["date_posted"] = info.get("startDate") or job.get("date_posted")
    # salary sometimes in description or a dedicated field
    pay = info.get("payRange") or {}
    if pay:
        job["salary_text"] = f"{pay.get('minimum','')}-{pay.get('maximum','')} {pay.get('currency','')}"
    return job


def main():
    raw = json.loads(RAW.read_text())
    relevant_idx = [i for i, j in enumerate(raw)
                    if j.get("title") and title_relevant(j["title"])]
    print(f"Total raw: {len(raw)} | title-relevant to enrich: {len(relevant_idx)}")

    enriched = list(raw)
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(enrich_one, raw[i]): i for i in relevant_idx}
        done = 0
        for fut in as_completed(futs):
            i = futs[fut]
            enriched[i] = fut.result()
            done += 1
            if done % 20 == 0:
                print(f"  ...enriched {done}/{len(relevant_idx)}")

    # keep only the relevant ones for downstream (the rest are noise from broad queries)
    out = [enriched[i] for i in relevant_idx]
    OUT.write_text(json.dumps(out, indent=2))
    got = sum(1 for j in out if j.get("description"))
    print(f"Wrote {OUT}: {len(out)} relevant jobs, {got} with descriptions")


if __name__ == "__main__":
    main()
