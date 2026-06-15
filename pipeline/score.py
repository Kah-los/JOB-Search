#!/usr/bin/env python3
"""
Scoring + filtering for scraped jobs against profile.json.

score_job(job, profile) -> dict with:
  fit_score (0-10), components, reasons[], flags{} , passes_filters (bool)

A job dict is expected to have at least:
  title, location, description (may be ""), employment_type, salary_text, remote_type, url

Scoring components (weighted, 0-10 overall):
  - title_fit        35%  title matches synonyms / domain terms
  - skills_match     30%  profile skills/keywords present in title+description
  - domain_relevance 15%  domain keywords present
  - seniority_align  10%  seniority words vs profile seniority
  - location_compat  10%  remote > hybrid > onsite

Hard filters applied separately (US, full-time, salary >= min, exclude clinical
licensure). Visa-sponsorship + onsite are *flags*, not exclusions.
"""
import re

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
# Healthcare-information relevance signal (must connect to healthcare info/data/ops)
HEALTH_CONTEXT_RE = re.compile(
    r"(health|clinical|patient|medical|hospital|care|ehr|emr|epic|hipaa|hl7|fhir|"
    r"revenue cycle|coding|him|cdi|population health|provider|payer|claims|"
    r"physician|nursing|pharmacy|interoperab|phi|hcc|icd|cpt|snomed)", re.I)
FULLTIME_RE = re.compile(r"\b(full[\s-]?time|full time|regular full)\b", re.I)
PARTTIME_RE = re.compile(r"\b(part[\s-]?time|per diem|prn|temporary|contract|intern)\b", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|telework|telecommute|virtual)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
SALARY_RE = re.compile(r"\$?\s?(\d{2,3}(?:,\d{3})|\d{2,3}\s?k)\b", re.I)
SENIORITY_RE = {
    "director": 3, "vp": 3, "head of": 3, "chief": 3,
    "manager": 2, "lead": 2, "principal": 2, "senior": 2, "sr.": 2, "supervisor": 2,
    "analyst": 1, "specialist": 1, "coordinator": 1, "associate": 1,
    "intern": 0, "assistant": 0, "entry": 0, "junior": 0, "jr.": 0,
}


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


def detect_remote_type(job):
    blob = " ".join([_norm(job.get("title")), _norm(job.get("location")),
                     _norm(job.get("remote_type")), _norm(job.get("description"))])
    if REMOTE_RE.search(blob) and "remote" in blob:
        return "Remote"
    if HYBRID_RE.search(blob):
        return "Hybrid"
    return "On-site"


def score_job(job, profile):
    title = _norm(job.get("title"))
    desc = _norm(job.get("description"))
    blob = title + "  " + desc
    reasons, flags = [], {}

    # ---- title_fit ----
    # A single strong synonym match is meaningful; extra matches add less.
    syn_hits = [s for s in profile["title_synonyms"] if _norm(s) in title]
    if syn_hits:
        title_fit = min(1.0, 0.6 + 0.25 * (len(syn_hits) - 1))
        reasons.append(f"Title matches: {', '.join(syn_hits[:3])}")
    else:
        title_fit = 0.0
    # high-value domain tokens in the title (boost even without exact synonym)
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
    # short descriptions can't surface many keywords; scale the denominator down
    denom = 6.0 if len(desc) > 1500 else (4.0 if len(desc) > 400 else 3.0)
    skills_match = min(1.0, len(skill_hits) / denom)
    if skill_hits:
        reasons.append(f"Skills present: {', '.join(skill_hits[:6])}")

    # ---- domain_relevance ----
    dom_hits = [d for d in profile["domains"] if any(w in blob for w in _norm(d).split() if len(w) > 4)]
    domain_relevance = min(1.0, len(dom_hits) / 3.0)

    # ---- seniority_align ----
    # Do NOT filter on seniority. The candidate is open to entry-to-mid through
    # director. Treat all of those as a fit; only discount actual internships.
    job_level = 1
    for k, v in SENIORITY_RE.items():
        if k in title:
            job_level = v
            break
    seniority_align = 0.6 if ("intern" in title and "internal" not in title) else 1.0

    # ---- location_compat ----
    rt = detect_remote_type(job)
    location_compat = {"Remote": 1.0, "Hybrid": 0.8, "On-site": 0.5}[rt]

    score10 = round(10 * (
        0.40 * title_fit +
        0.25 * skills_match +
        0.15 * domain_relevance +
        0.10 * seniority_align +
        0.10 * location_compat), 1)

    # ---- flags ----
    flags["remote_type"] = rt
    flags["onsite"] = (rt == "On-site")
    flags["visa_sponsorship_mentioned"] = bool(VISA_RE.search(blob))
    flags["clinical_licensure_required"] = bool(
        CLINICAL_LICENSE_RE.search(blob) or CLINICAL_TITLE_RE.search(title))
    sal = parse_salary_usd(job.get("salary_text") or "") or parse_salary_usd(desc)
    flags["salary_usd_max"] = sal

    # ---- hard filters ----
    fails = []
    flags["software_engineering"] = bool(SOFTWARE_ENG_RE.search(title))
    flags["healthcare_related"] = bool(HEALTH_CONTEXT_RE.search(blob))
    if flags["clinical_licensure_required"]:
        fails.append("requires clinical licensure")
    if flags["software_engineering"]:
        fails.append("pure software engineering role")
    if not flags["healthcare_related"]:
        fails.append("no healthcare-information connection")
    if PARTTIME_RE.search(blob) and not FULLTIME_RE.search(blob):
        fails.append("not full-time")
    if sal is not None and sal < profile["filters"]["min_salary_usd"]:
        fails.append(f"salary ${sal:,} < min")
    passes_filters = (len(fails) == 0) and (score10 >= profile["filters"]["min_fit_score"])

    return {
        "fit_score": score10,
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
