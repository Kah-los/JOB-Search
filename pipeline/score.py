#!/usr/bin/env python3
"""
Scoring + filtering for scraped jobs against profile.json.

score_job(job, profile) -> dict with:
  fit_score (0-10), priority (sort key), components, reasons[], flags{},
  passes_filters (bool)

A job dict is expected to have at least:
  title, location, description (may be ""), employment_type, salary_text,
  remote_type, url, date_posted, employer, employer_state

Scoring components (weighted, 0-10 overall):
  - title_fit        35%  title matches synonyms / domain terms
  - skills_match     30%  profile skills/keywords present in title+description
  - domain_relevance 15%  domain keywords present
  - seniority_align  10%  mid-career (3-5+ yrs) alignment
  - location_compat  10%  remote > hybrid > onsite

Candidate preferences (the user, 10 yrs experience) bias the *priority* ranking
on top of fit_score:
  + non-technical roles preferred over technical
  + roles in U.S. states with no personal income tax preferred
  + large health-informatics employers preferred
  + roles disclosing 401(k)/pension/strong benefits preferred
  + mid-career (3-5+ years required) preferred

Hard filters: U.S. + full-time, salary >= min (when disclosed), posted within the
last N days (when a post date is known), NOT entry-level/intern/junior, excludes
clinical licensure, excludes pure software engineering, must connect to
healthcare information. Visa-sponsorship + onsite remain *flags*, not exclusions.
"""
import re
from datetime import datetime, date

# Requirement-anchored: only fires when a clinical license/credential is
# genuinely REQUIRED, not merely mentioned in passing.
CLINICAL_LICENSE_RE = re.compile(
    r"("
    r"\(rn\)|registered nurse (required|license)|"
    r"(current|active|valid|unencumbered)[^.]{0,30}(rn|nursing|lpn|registered nurse) licens|"
    r"(rn|lpn|bsn|registered nurse)[^.]{0,25}(required|licensure required)|"
    r"licensed (registered nurse|practical nurse)|"
    r"requires?[^.]{0,30}(rn|nursing|nurse practitioner|pharmd|physician assistant) licens|"
    r"must be a (registered nurse|licensed)|"
    r"nurse practitioner|pharmd|physician assistant certification|"
    r"current.{0,15}(pharmacist|respiratory therapist|physical therapist) license"
    r")",
    re.I,
)
# Title-level clinical role markers (strong signal the role IS a clinician)
CLINICAL_TITLE_RE = re.compile(
    r"\((rn|np|aprn|lpn)\)|\b(registered nurse|nurse practitioner|staff nurse|"
    r"physician|pharmacist|respiratory therapist|physical therapist|"
    r"social worker|dietitian)\b", re.I)
VISA_RE = re.compile(
    r"(visa sponsor|sponsorship|h-?1b|will sponsor|work authorization|"
    r"authorized to work|employment authorization|green card)", re.I)
# Pure software engineering / infra (excluded) — but NOT analyst/BI/data roles
SOFTWARE_ENG_RE = re.compile(
    r"\b(software engineer|software developer|backend developer|back-end developer|"
    r"front-end developer|frontend developer|full[\s-]?stack|web developer|"
    r"mobile developer|devops|site reliability|\bsre\b|infrastructure engineer|"
    r"network engineer|cloud engineer|platform engineer|systems administrator|"
    r"database administrator|\bdba\b|security engineer|embedded engineer|"
    r"qa engineer|test engineer|firmware)\b", re.I)
# Technical (kept, but de-prioritized vs non-technical) — hands-on build/config roles
TECHNICAL_TITLE_RE = re.compile(
    r"\b(developer|engineer|programmer|architect|administrator|sysadmin|"
    r"data engineer|etl|integration (analyst|engineer|developer)|"
    r"application (analyst|developer|engineer)|systems analyst|sql|"
    r"technical (analyst|lead|specialist)|software|devops|automation engineer|"
    r"network|infrastructure|cybersecurity|security analyst)\b", re.I)
# Non-technical / business-functional role markers (PREFERRED)
NON_TECH_TITLE_RE = re.compile(
    r"\b(manager|director|coordinator|specialist|consultant|advisor|advisory|"
    r"officer|lead|supervisor|administrator of|program|project manager|"
    r"compliance|privacy|governance|policy|auditor|audit|quality|"
    r"documentation|cdi|him|health information|revenue cycle|revenue integrity|"
    r"reimbursement|coding|operations|education|educator|trainer|training|"
    r"liaison|population health|case management|care coordination|"
    r"accreditation|regulatory|utilization|business analyst|data analyst|"
    r"reporting analyst|healthcare analyst)\b", re.I)
# Healthcare-information relevance signal (must connect to healthcare info/data/ops)
HEALTH_CONTEXT_RE = re.compile(
    r"(health|clinical|patient|medical|hospital|care|ehr|emr|epic|hipaa|hl7|fhir|"
    r"revenue cycle|coding|him|cdi|population health|provider|payer|claims|"
    r"physician|nursing|pharmacy|interoperab|phi|hcc|icd|cpt|snomed)", re.I)
FULLTIME_RE = re.compile(r"\b(full[\s-]?time|full time|regular full)\b", re.I)
PARTTIME_RE = re.compile(r"\b(part[\s-]?time|per diem|prn|temporary|contract|intern)\b", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|telework|telecommute|virtual)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)

# Entry-level markers (EXCLUDED — candidate has 10 yrs, targets 3-5+ yrs roles)
ENTRY_TITLE_RE = re.compile(
    r"\b(intern|internship|trainee|apprentice|entry[\s-]?level|new grad|"
    r"graduate (program|trainee)|junior|jr\.?)\b|\b(analyst|"
    r"specialist|coordinator|technician)\s+(i|1)\b", re.I)
ENTRY_DESC_RE = re.compile(
    r"\b(entry[\s-]?level|no (prior )?experience (required|necessary)|"
    r"recent graduate|new graduate)\b", re.I)
SENIOR_TITLE_RE = re.compile(
    r"\b(senior|sr\.?|lead|principal|manager|director|supervisor|head of)\b", re.I)
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(\d{1,2})?\s*\+?\s*years?", re.I)

# Benefits signals (PREFERRED)
RETIRE_401K_RE = re.compile(r"\b(401\s?\(?k\)?|403\s?\(?b\)?|retirement (plan|savings)|"
                            r"employer match|company match)\b", re.I)
PENSION_RE = re.compile(r"\b(pension|defined benefit|state retirement|\bcalpers\b|"
                        r"\bpers\b|\bters\b|\bsers\b)\b", re.I)

# U.S. states with NO personal income tax (PREFERRED). NH/WA tax some investment
# income but levy no tax on wages, so they are included.
NO_TAX_STATES = {"AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"}

STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_ABBR_SET = set(STATE_ABBR.values())
STATE_CODE_RE = re.compile(r",\s*([A-Z]{2})\b")

# Large health-informatics / health-IT employers and major health systems
# (PREFERRED — "target large health informatics employers first"). Lowercase
# substrings matched against the employer name.
BIG_HEALTH_INFORMATICS = [
    # Health-IT vendors / informatics-first
    "oracle", "cerner", "epic systems", "athenahealth", "veradigm", "allscripts",
    "meditech", "nextgen", "ge healthcare", "philips", "medtronic", "mckesson",
    "cardinal health", "iqvia", "health catalyst", "innovaccer", "datavant",
    "komodo", "waystar", "r1 rcm", "change healthcare", "press ganey",
    "cognizant", "deloitte", "accenture", "leidos", "gdit", "booz allen",
    "optum", "unitedhealth", "humana", "elevance", "cvs health", "aetna",
    "cohere", "phenom", "premier inc", "nuance", "3m health",
    # Large health systems with mature informatics functions
    "mayo clinic", "cleveland clinic", "kaiser", "hca healthcare", "commonspirit",
    "ascension", "providence", "sutter", "baptist health", "mount sinai",
    "adventhealth", "trinity health", "tenet", "banner health", "intermountain",
    "geisinger", "northwell", "advocate", "memorial hermann", "uchealth",
    "ucla health", "nyu langone", "johns hopkins", "mass general", "cedars-sinai",
    "stanford health", "duke health", "vanderbilt", "houston methodist",
]

SENIORITY_RE = {
    "director": 3, "vp": 3, "head of": 3, "chief": 3,
    "manager": 2, "lead": 2, "principal": 2, "senior": 2, "sr.": 2, "supervisor": 2,
    "analyst": 1, "specialist": 1, "coordinator": 1, "associate": 1,
    "intern": 0, "assistant": 0, "entry": 0, "junior": 0, "jr.": 0,
}

TODAY = date.today()


def _norm(s):
    return (s or "").lower()


def _all_skills(profile):
    out = []
    for grp in profile["skills"].values():
        out.extend(grp)
    return out


def parse_salary_usd(text):
    """Return the max disclosed salary in USD as int, or None."""
    if not text:
        return None
    vals = []
    for m in re.finditer(r"\$?\s?(\d{2,3})(?:,(\d{3}))?\s?(k|,000)?", text, re.I):
        whole, thousands, k = m.group(1), m.group(2), m.group(3)
        n = int(whole)
        if thousands:
            n = int(whole + thousands)
        elif k:
            n = n * 1000
        else:
            continue
        if 20000 <= n <= 600000:
            vals.append(n)
    return max(vals) if vals else None


def parse_date_posted(value):
    """Parse a variety of ISO-ish date strings -> datetime.date, or None."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def days_since_posted(job):
    d = parse_date_posted(job.get("date_posted"))
    if d is None:
        return None
    return (TODAY - d).days


def extract_state(job):
    """Best-effort 2-letter U.S. state for the *job*, preferring its location,
    then the employer's home state. Returns a code (e.g. 'TX') or ''."""
    loc = job.get("location") or ""
    m = STATE_CODE_RE.search(loc)
    if m and m.group(1) in _ABBR_SET:
        return m.group(1)
    low = loc.lower()
    for name, code in STATE_ABBR.items():
        if name in low:
            return code
    est = (job.get("employer_state") or "").strip()
    if not est:
        return ""
    if est.upper() in _ABBR_SET:
        return est.upper()
    return STATE_ABBR.get(est.lower(), "")


def detect_remote_type(job):
    blob = " ".join([_norm(job.get("title")), _norm(job.get("location")),
                     _norm(job.get("remote_type")), _norm(job.get("description"))])
    if REMOTE_RE.search(blob) and "remote" in blob:
        return "Remote"
    if HYBRID_RE.search(blob):
        return "Hybrid"
    return "On-site"


def required_years(desc):
    """Smallest 'N years' figure mentioned, as a rough required-experience proxy."""
    yrs = []
    for m in YEARS_RE.finditer(desc or ""):
        lo = int(m.group(1))
        if 0 <= lo <= 25:
            yrs.append(lo)
    return min(yrs) if yrs else None


def is_big_employer(employer):
    e = _norm(employer)
    return any(k in e for k in BIG_HEALTH_INFORMATICS)


def score_job(job, profile):
    title = _norm(job.get("title"))
    desc = _norm(job.get("description"))
    blob = title + "  " + desc
    reasons, flags = [], {}
    fil = profile["filters"]
    max_days = fil.get("max_days_since_posted", 30)
    min_years_target = fil.get("min_years_target", 3)

    # ---- title_fit ----
    syn_hits = [s for s in profile["title_synonyms"] if _norm(s) in title]
    if syn_hits:
        title_fit = min(1.0, 0.6 + 0.25 * (len(syn_hits) - 1))
        reasons.append(f"Title matches: {', '.join(syn_hits[:3])}")
    else:
        title_fit = 0.0
    hv = {"informatics", "health information", "him", "cdi", "documentation",
          "ehr", "emr", "epic", "interoperab", "hl7", "fhir", "privacy",
          "governance", "revenue cycle", "revenue integrity", "clinical systems",
          "decision support", "compliance", "coding", "analytics", "analyst",
          "quality", "patient safety", "population health", "regulatory",
          "data integrity", "data quality", "case management", "care coordination",
          "project manager", "program manager", "business analyst", "audit",
          "accreditation", "reimbursement", "utilization", "medical records",
          "process improvement", "performance improvement", "policy", "registry"}
    hv_hits = [w for w in hv if w in title]
    if hv_hits:
        title_fit = max(title_fit, min(1.0, 0.5 + 0.15 * len(hv_hits)))

    # ---- skills_match ----
    skills = _all_skills(profile)
    skill_hits = sorted({s for s in skills if _norm(s) in blob})
    denom = 6.0 if len(desc) > 1500 else (4.0 if len(desc) > 400 else 3.0)
    skills_match = min(1.0, len(skill_hits) / denom)
    if skill_hits:
        reasons.append(f"Skills present: {', '.join(skill_hits[:6])}")

    # ---- domain_relevance ----
    dom_hits = [d for d in profile["domains"] if any(w in blob for w in _norm(d).split() if len(w) > 4)]
    domain_relevance = min(1.0, len(dom_hits) / 3.0)

    # ---- experience / seniority ----
    min_yrs = required_years(desc)
    # Only exclude clearly entry-level titles or roles asking for ≤1 yr experience.
    if SENIOR_TITLE_RE.search(title):
        is_entry = False
    elif ENTRY_TITLE_RE.search(title) and "internal" not in title:
        is_entry = True
    elif min_yrs is not None and min_yrs <= 1:
        is_entry = True
    else:
        is_entry = False
    # mid-career fit: 3-5+ yrs target. Reward roles asking for >= target experience.
    if min_yrs is None:
        seniority_align = 0.85
    elif min_yrs >= min_years_target:
        seniority_align = 1.0
        reasons.append(f"Requires {min_yrs}+ yrs (mid-career fit)")
    elif min_yrs >= 2:
        seniority_align = 0.7
    else:
        seniority_align = 0.3

    # ---- location_compat ----
    rt = detect_remote_type(job)
    location_compat = {"Remote": 1.0, "Hybrid": 0.8, "On-site": 0.5}[rt]

    score10 = round(10 * (
        0.35 * title_fit +
        0.30 * skills_match +
        0.15 * domain_relevance +
        0.10 * seniority_align +
        0.10 * location_compat), 1)

    # ---- role technicality (non-technical preferred) ----
    is_technical = bool(TECHNICAL_TITLE_RE.search(title))
    is_non_technical = bool(NON_TECH_TITLE_RE.search(title)) and not is_technical
    role_type = "Technical" if is_technical else ("Non-technical" if is_non_technical else "Mixed")

    # ---- state / tax ----
    state = extract_state(job)
    no_tax = state in NO_TAX_STATES

    # ---- benefits ----
    has_401k = bool(RETIRE_401K_RE.search(desc))
    has_pension = bool(PENSION_RE.search(desc))

    # ---- big employer ----
    big_employer = is_big_employer(job.get("employer"))

    # ---- recency ----
    d_old = days_since_posted(job)

    # ---- flags ----
    flags["remote_type"] = rt
    flags["onsite"] = (rt == "On-site")
    flags["visa_sponsorship_mentioned"] = bool(VISA_RE.search(blob))
    flags["clinical_licensure_required"] = bool(
        CLINICAL_LICENSE_RE.search(blob) or CLINICAL_TITLE_RE.search(title))
    sal = parse_salary_usd(job.get("salary_text") or "") or parse_salary_usd(desc)
    flags["salary_usd_max"] = sal
    flags["state"] = state
    flags["no_tax_state"] = no_tax
    flags["role_type"] = role_type
    flags["technical"] = is_technical
    flags["min_years_required"] = min_yrs
    flags["entry_level"] = is_entry
    flags["benefits_401k"] = has_401k
    flags["pension"] = has_pension
    flags["big_employer"] = big_employer
    flags["days_since_posted"] = d_old
    flags["software_engineering"] = bool(SOFTWARE_ENG_RE.search(title))
    flags["healthcare_related"] = bool(HEALTH_CONTEXT_RE.search(blob))

    # ---- hard filters ----
    fails = []
    if flags["clinical_licensure_required"]:
        fails.append("requires clinical licensure")
    if flags["software_engineering"]:
        fails.append("pure software engineering role")
    if not flags["healthcare_related"]:
        fails.append("no healthcare-information connection")
    if PARTTIME_RE.search(blob) and not FULLTIME_RE.search(blob):
        fails.append("not full-time")
    if sal is not None and sal < fil["min_salary_usd"]:
        fails.append(f"salary ${sal:,} < ${fil['min_salary_usd']:,} min")
    if is_entry:
        fails.append("entry-level / below target experience")
    if d_old is not None and d_old > max_days:
        fails.append(f"posted {d_old}d ago (> {max_days}d)")

    passes_filters = (len(fails) == 0) and (score10 >= fil["min_fit_score"])

    # ---- priority (ranking on top of fit, reflecting candidate preferences) ----
    bonus = 0.0
    if is_non_technical:
        bonus += 1.2
    elif is_technical:
        bonus -= 0.8
    if no_tax:
        bonus += 1.0
    if big_employer:
        bonus += 1.0
    if has_401k:
        bonus += 0.3
    if has_pension:
        bonus += 0.3
    if min_yrs is not None and min_yrs >= min_years_target:
        bonus += 0.4
    if d_old is not None and d_old <= 7:
        bonus += 0.3
    priority = round(score10 + bonus, 2)
    flags["priority_bonus"] = round(bonus, 2)

    return {
        "fit_score": score10,
        "priority": priority,
        "components": {
            "title_fit": round(title_fit, 2), "skills_match": round(skills_match, 2),
            "domain_relevance": round(domain_relevance, 2),
            "seniority_align": round(seniority_align, 2),
            "location_compat": round(location_compat, 2),
        },
        "reasons": reasons,
        "flags": flags,
        "filter_failures": fails,
        "passes_filters": passes_filters,
    }
