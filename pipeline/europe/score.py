"""Europe job scoring, filtering, and language-based ranking."""

import re
from datetime import datetime, date

from .config import LANGUAGE_POINTS
from .language import (
    extract_languages, score_language, requires_c1_c2_local, summarize,
)

TODAY = date.today()
HEALTH_RE = re.compile(
    r"(health informatics|informatics|health information|him\b|ehr|emr|epic|hl7|fhir|"
    r"clinical documentation|cdi\b|medical records|healthcare data|data analyst|"
    r"interoperab|digital health|health it|information management|data governance|"
    r"compliance|quality improvement|population health|openEHR|snomed|"
    r"business analyst|project manager|program manager|analytics|bi\b|"
    r"health & safety manager|health safety|medical device|healthcare|hospital administration)",
    re.I)
CLINICAL_ROLE_RE = re.compile(
    r"\b(surgeon|physician|doctor|nurse|nursing|midwife|dentist|pharmacist|"
    r"radiologist|radiology career|orthopaedic specialist|pediatric spine|"
    r"undersköterska|sjuksköterska|läkare|tandläkare)\b", re.I)


def parse_date(value):
    if not value:
        return None
    s = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except Exception:
        return None


def days_old(job):
    d = parse_date(job.get("date_posted"))
    return (TODAY - d).days if d else None


def title_relevant(title: str) -> bool:
    if CLINICAL_ROLE_RE.search(title or ""):
        return False
    return bool(HEALTH_RE.search(title or ""))


def score_job(job: dict, profile: dict) -> dict:
    title = job.get("title") or ""
    desc = job.get("description") or ""
    country = job.get("country") or ""
    blob = f"{title} {desc}"

    reasons = []
    flags = {}

    # Must be healthcare-informatics related (not generic health/safety)
    if CLINICAL_ROLE_RE.search(title):
        return {"passes_filters": False, "fit_score": 0, "priority": 0,
                "reasons": ["Clinical/licensed role"], "flags": {}}
    if not title_relevant(title) and not HEALTH_RE.search(desc[:600]):
        return {"passes_filters": False, "fit_score": 0, "priority": 0,
                "reasons": ["Not health-informatics related"], "flags": {}}

    # C1/C2 local language exclusion
    if requires_c1_c2_local(title, desc):
        return {"passes_filters": False, "fit_score": 0, "priority": 0,
                "reasons": ["Requires C1/C2 local language without English"], "flags": {}}

    langs = extract_languages(title, desc, country)
    lang_info = score_language(title, desc, country, langs)
    flags.update(lang_info)
    flags["summary"] = summarize(desc)

    # Base fit from profile skills
    skill_hits = 0
    for grp in profile.get("skills", {}).values():
        for s in grp:
            if s.lower() in blob.lower():
                skill_hits += 1
    title_hits = sum(1 for t in profile.get("title_synonyms", [])
                     if t.lower() in title.lower())

    fit = min(10, 4 + skill_hits * 0.4 + title_hits * 1.2)
    reasons.append(f"Skill/title match ({skill_hits} skills, {title_hits} title hits)")

    # Language priority (main sort key)
    lang_pts = lang_info["language_score"]
    priority = lang_pts * 10 + fit

    # Remote Europe bonus
    mode = (job.get("work_mode") or "").lower()
    if "remote" in mode:
        priority += LANGUAGE_POINTS["remote_europe"]
        flags["remote_europe"] = True
        reasons.append("Remote-friendly Europe")

    # Recency bonus
    days = days_old(job)
    flags["days_old"] = days
    if days is not None and days <= 14:
        priority += 2
    elif days is not None and days <= 30:
        priority += 1

    flags["experience_level"] = job.get("experience_level") or "Not specified"
    flags["work_mode"] = job.get("work_mode") or "On-site"
    flags["country"] = country
    flags["city"] = job.get("city") or ""

    return {
        "passes_filters": True,
        "fit_score": round(fit, 1),
        "priority": round(priority, 1),
        "reasons": reasons,
        "flags": flags,
    }
