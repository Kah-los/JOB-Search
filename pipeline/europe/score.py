"""Europe job scoring, filtering, and language-based ranking."""

import re
from datetime import datetime, date

from .config import LANGUAGE_POINTS, ALL_TARGET_TITLES
from .employer_signals import score_foreigner_friendly
from .language import (
    extract_languages, score_language, requires_c1_c2_local, summarize,
)

TODAY = date.today()

# Strong health-informatics signals (title alone is enough)
HEALTH_STRONG_RE = re.compile(
    r"(health informatics|clinical informatics|health information management|"
    r"health information|informatics analyst|informatics specialist|informatics officer|"
    r"informatics manager|informatics consultant|informatics researcher|"
    r"\bhim\b|health information manager|medical records|journalsystem|"
    r"\behr\b|\bemr\b|\bepic\b|openEHR|snomed|"
    r"\bhl7\b|\bfhir\b|interoperab|clinical documentation|\bcdi\b|"
    r"healthcare it|health it|healthcare data|health data analyst|clinical data analyst|"
    r"digital health|ehealth|e-health|ehälsa|e-hälsa|ehelse|esalud|esaúde|"
    r"klinisk it|clinical systems|clinical application|hospital information|"
    r"nhs digital|digital systems analyst|clinical informatics|"
    r"gesundheitsinformatik|santé numérique|informatique médicale|"
    r"implementation consultant.{0,20}health|health.{0,20}implementation|"
    r"integration (specialist|analyst|engineer).{0,30}(health|clinical|fhir|hl7)|"
    r"(fhir|hl7).{0,30}integration|"
    r"vårdnära digital|vård.{0,15}digital|digital.{0,15}vård|"
    r"affärsanalytiker.{0,20}(ehälsa|e-hälsa|vård|hälsa)|"
    r"systemanalytiker.{0,20}(ehälsa|e-hälsa|vård|hälsa|health)|"
    r"hälsoinformatik|ehälso|ehelse ikt|"
    r"bioinformatik|bioinformatics)",
    re.I,
)

# Healthcare setting / domain (must pair with role or strong term for generic titles)
HEALTH_CONTEXT_RE = re.compile(
    r"(healthcare|health care|health system|hospital|clinical|patient|medical record|"
    r"primary care|mental health|nhs\b|gp practice|care home|"
    r"\binera\b|1177|"
    r"sjukhus|vård|vården|hälsa|hälso|patientjournal|journalhantering|"
    r"ehälsa|e-hälsa|ehelse|region.{0,10}(vård|hälsa)|"
    r"revenue cycle|billing.{0,15}(health|hospital)|"
    r"physician|nursing informatics|pharmacy system)",
    re.I,
)

# Generic role nouns — only pass with health-informatics context
GENERIC_ROLE_RE = re.compile(
    r"\b(business analyst|systems? analyst|system analyst|data analyst|"
    r"project manager|programme manager|program manager|product owner|"
    r"scrum master|bi[\s-]?(specialist|konsult|developer)|"
    r"verksamhetsutvecklare|kravanalytiker|testledare|test analyst|"
    r"compliance officer|digital product|change manager|"
    r"data governance|transformation manager|capital project)\b",
    re.I,
)

# Obvious non-health-informatics roles
OFF_TOPIC_RE = re.compile(
    r"\b(cyber\s*security|cybersecurity|signalskydd|säkerhetsstaben|"
    r"\bsaab\b|defence|defense|military|försvar|"
    r"calypso|erp.{0,10}(accounting|visualisering)|"
    r"\bica\b.{0,10}(butik|handel|krav)|"
    r"assistant professor|postdoktor|postdoc|neurodegenerativ|"
    r"intensivvårdssjuksköterska|bolničar|negovalec|"
    r"assistente di negozio|rakodómunkás|komissiózó|"
    r"tecnico dei macchinari|warehouse|lager|retail|shop assistant|"
    r"miljö och klimat|va-ekonomi|körkortsbehörighet|"
    r"contract management(?!.{0,40}health)|"
    r"capital project manager|people systems project|"
    r"medical records clerk|healthcare assistant|healthcare science associate|"
    r"people.{0,10}project manager|"
    r"psykolog|tandhygienist|fysioterapeut|dialys|"
    r"sommarjobb|lss-boende|receptionist|administratör/receptionist|"
    r"annsam söker|sjukskötersk|allmänsjukskötersk|"
    r"\bit-tekniker\b|systemarkitekt|mjukvaruingenjör|"
    r"delförvaltningsledare|kommunal digital|högre körkort|finspångs kommun)\b",
    re.I,
)

CLINICAL_ROLE_RE = re.compile(
    r"\b(surgeon|physician|doctor|nurse|nursing|midwife|dentist|pharmacist|"
    r"radiologist|radiology career|orthopaedic specialist|pediatric spine|"
    r"undersköterska|sjuksköterska|läkare|tandläkare|"
    r"staff nurse|registered nurse|healthcare assistant)\b", re.I,
)

# Legacy alias used in a few imports/tests
HEALTH_RE = HEALTH_STRONG_RE


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


def _target_in_title(title: str, target: str) -> bool:
    """Match listed target titles without letting bare Swedish role words slip through."""
    t = (title or "").lower()
    tl = target.lower().strip()
    if not t or not tl:
        return False
    if tl in t:
        return True
    # "Verksamhetsutvecklare, IT" → require IT/informatics/digital in title too
    if "verksamhetsutvecklare" in tl and "verksamhetsutvecklare" in t:
        has_it = bool(re.search(
            r"\b(it|informatic|digital|ehälsa|e-hälsa|system|journalsystem)\b", t))
        has_health = bool(HEALTH_STRONG_RE.search(t) or HEALTH_CONTEXT_RE.search(t))
        return has_it and has_health
    if "business analyst" in tl or "affärsanalytiker" in tl:
        if "business analyst" in t or "affärsanalytiker" in t:
            return bool(HEALTH_STRONG_RE.search(t) or HEALTH_CONTEXT_RE.search(t))
    return False


def is_health_informatics_role(title: str, description: str = "") -> bool:
    """True only for health-informatics / digital-health IT roles."""
    title = title or ""
    if CLINICAL_ROLE_RE.search(title) or OFF_TOPIC_RE.search(title):
        return False

    if HEALTH_STRONG_RE.search(title):
        return True

    for target in ALL_TARGET_TITLES:
        if _target_in_title(title, target):
            return True

    blob = f"{title} {description[:1500]}"
    if GENERIC_ROLE_RE.search(title):
        if HEALTH_STRONG_RE.search(blob):
            return True
        if HEALTH_CONTEXT_RE.search(blob) and re.search(
            r"(informatics|ehr|emr|ehälsa|e-hälsa|health it|digital health|"
            r"journalsystem|klinisk it|cdi|him|fhir|hl7|medical record|patientdata|"
            r"digital.{0,10}system|transformation.{0,15}(health|nhs|vård))",
            blob, re.I,
        ):
            return True
        return False

    # Title not generic — description must carry a strong informatics signal
    if HEALTH_STRONG_RE.search(description[:1500]):
        if re.search(
            r"sjuksköterska|psykolog|tand|fysio|dialys|läkare|undersköterska|"
            r"receptionist|administratör(?!.{0,20}medical record)",
            title, re.I,
        ):
            return False
        return True

    return False


def title_relevant(title: str, description: str = "") -> bool:
    return is_health_informatics_role(title, description)


def _title_hits(title: str, profile: dict) -> int:
    t_lower = (title or "").lower()
    hits = 0
    seen = set()
    for source in (profile.get("title_synonyms", []), ALL_TARGET_TITLES):
        for t in source:
            key = t.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            if _target_in_title(title, t) or key in t_lower:
                hits += 1
    return hits


def score_job(job: dict, profile: dict) -> dict:
    title = job.get("title") or ""
    desc = job.get("description") or ""
    country = job.get("country") or ""
    blob = f"{title} {desc}"

    reasons = []
    flags = {}

    if CLINICAL_ROLE_RE.search(title) or OFF_TOPIC_RE.search(title):
        return {"passes_filters": False, "fit_score": 0, "priority": 0,
                "reasons": ["Off-topic or clinical role"], "flags": {}}

    if not is_health_informatics_role(title, desc):
        return {"passes_filters": False, "fit_score": 0, "priority": 0,
                "reasons": ["Not health-informatics related"], "flags": {}}

    if requires_c1_c2_local(title, desc):
        return {"passes_filters": False, "fit_score": 0, "priority": 0,
                "reasons": ["Requires C1/C2 local language without English"], "flags": {}}

    langs = extract_languages(title, desc, country)
    lang_info = score_language(title, desc, country, langs)
    flags.update(lang_info)
    flags["summary"] = summarize(desc)

    skill_hits = 0
    for grp in profile.get("skills", {}).values():
        for s in grp:
            if s.lower() in blob.lower():
                skill_hits += 1
    title_hits = _title_hits(title, profile)

    fit = min(10, 4 + skill_hits * 0.4 + title_hits * 1.2)
    reasons.append(f"Skill/title match ({skill_hits} skills, {title_hits} title hits)")

    lang_pts = lang_info["language_score"]
    priority = lang_pts * 10 + fit

    emp_info = score_foreigner_friendly(
        job.get("employer") or "",
        title,
        desc,
        country=country,
        work_mode=job.get("work_mode") or job.get("remote_type") or "",
    )
    flags.update(emp_info)
    flags["employer_type"] = emp_info["employer_type"]

    prefs = profile.get("employer_preferences", {})
    if prefs.get("prefer_startups_private"):
        if emp_info["employer_type"] in ("startup", "scaleup", "private", "consulting"):
            priority += 4
            reasons.append(f"Preferred employer type: {emp_info['employer_type']}")
        elif emp_info["employer_type"] in ("public_sector", "hospital"):
            priority -= 3
            reasons.append("Public-sector/hospital employer (lower priority)")

    if prefs.get("prefer_foreigner_friendly"):
        fs = emp_info["foreigner_score"]
        if fs >= 6:
            priority += 5
            reasons.append("Foreigner-friendly signals")
        elif fs >= 3:
            priority += 2
        elif fs < 0:
            priority -= 4
            reasons.append("Local-only hiring signals")

    if emp_info.get("startup_match"):
        priority += 3
        reasons.append(f"Health-tech startup match ({emp_info.get('startup_name')})")

    mode = (job.get("work_mode") or job.get("remote_type") or "").lower()
    if "remote" in mode:
        priority += LANGUAGE_POINTS["remote_europe"]
        flags["remote_europe"] = True
        reasons.append("Remote-friendly Europe")

    days = days_old(job)
    flags["days_old"] = days
    if days is not None and days <= 14:
        priority += 2
    elif days is not None and days <= 30:
        priority += 1

    flags["experience_level"] = job.get("experience_level") or "Not specified"
    flags["work_mode"] = job.get("work_mode") or job.get("remote_type") or "On-site"
    flags["country"] = country
    flags["city"] = job.get("city") or ""

    return {
        "passes_filters": True,
        "fit_score": round(fit, 1),
        "priority": round(priority, 1),
        "reasons": reasons,
        "flags": flags,
    }
