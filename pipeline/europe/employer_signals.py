"""Classify Europe employers for startup/private vs public-sector and foreigner-friendliness."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STARTUP_SEED_PATH = ROOT / "data" / "europe" / "healthtech_startups.json"

PUBLIC_SECTOR_RE = re.compile(
    r"\b(nhs\s+(trust|foundation)|foundation trust|university hospital|teaching hospital|"
    r"region\s+\w+|regions?\s+(stockholm|skåne|västra|östergötland|uppsala)|"
    r"landsting|kommun|municipality|county council|public sector|government agency|"
    r"ministry of health|statlig|offentlig|öffentlich|hôpital public|"
    r"karolinska universitetssjukhuset|sahlgrenska universitetssjukhus)\b",
    re.I,
)

HOSPITAL_RE = re.compile(
    r"\b(hospital|sjukhus|sykehus|klinikum|krankenhaus|hôpital|ospedale)\b",
    re.I,
)

STARTUP_RE = re.compile(
    r"\b(startup|scale[- ]?up|series\s+[abc]|seed\s+round|venture[- ]backed|"
    r"health\s*tech|healthtech|digital\s+health\s+(company|startup)|"
    r"fast[- ]growing|high[- ]growth|unicorn|vc[- ]backed)\b",
    re.I,
)

PRIVATE_RE = re.compile(
    r"\b(private\s+(healthcare|hospital|clinic|practice)|privatklinik|"
    r"health\s+insurtech|insurtech|telehealth|telemedicine|saas|b2b\s+saas)\b",
    re.I,
)

FOREIGNER_FRIENDLY_RE = re.compile(
    r"\b(visa\s+sponsorship|sponsor\s+visa|relocation\s+(package|assistance|support)|"
    r"relocate\s+to|open\s+to\s+international|international\s+candidates|"
    r"global\s+team|multicultural\s+team|english[- ]speaking\s+(team|environment|workplace)|"
    r"work\s+authorization\s+in\s+(the\s+)?eu|eu\s+work\s+permit|eea\s+citizen|"
    r"eligible\s+to\s+work\s+in\s+(the\s+)?eu|right\s+to\s+work\s+in\s+(the\s+)?eu|"
    r"no\s+swedish\s+required|fluent\s+english|english\s+required|"
    r"remote\s+within\s+europe|work\s+from\s+anywhere\s+in\s+europe|"
    r"distributed\s+team|international\s+applicants\s+welcome)\b",
    re.I,
)

FOREIGNER_HARD_BLOCK_RE = re.compile(
    r"\b(swedish\s+citizenship|must\s+be\s+(a\s+)?swedish\s+citizen|"
    r"norwegian\s+citizenship|danish\s+citizenship|finnish\s+citizenship|"
    r"uk\s+national|british\s+citizen|security\s+clearance\s+required|"
    r"public\s+sector\s+employment\s+requires|offentlig\s+anställning|"
    r"behörighet\s+som\s+leg\.?\s*sjuksköterska|legitimerad\s+sjuksköterska\s+krävs)\b",
    re.I,
)

_CONSULTING_FRIENDLY = {
    "netlight", "tietoevry", "capgemini invent", "accenture", "deloitte",
}


def _load_startup_seed() -> list[dict]:
    if not STARTUP_SEED_PATH.exists():
        return []
    try:
        return json.loads(STARTUP_SEED_PATH.read_text())
    except Exception:
        return []


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def match_seed_employer(employer: str) -> dict | None:
    emp = _norm(employer)
    if not emp:
        return None
    for row in _load_startup_seed():
        for alias in row.get("aliases", []) + [row.get("name", "")]:
            alias_n = _norm(alias)
            if alias_n and (alias_n in emp or emp in alias_n):
                return row
    return None


def classify_employer_type(employer: str, description: str = "") -> str:
    """startup | scaleup | private | consulting | public_sector | hospital | unknown"""
    seed = match_seed_employer(employer)
    if seed:
        return seed.get("employer_type", "startup")

    blob = f"{employer} {description[:800]}"
    if PUBLIC_SECTOR_RE.search(blob):
        return "public_sector"
    if HOSPITAL_RE.search(employer) and not PRIVATE_RE.search(blob):
        return "hospital"
    if STARTUP_RE.search(blob):
        return "startup"
    emp = _norm(employer)
    if any(c in emp for c in _CONSULTING_FRIENDLY):
        return "consulting"
    if PRIVATE_RE.search(blob) or re.search(
        r"\b(ltd|limited|gmbh|ab|aps|oy|bv|s\.a\.|sarl|inc\.?)\b", employer, re.I
    ):
        return "private"
    return "unknown"


def score_foreigner_friendly(
    employer: str,
    title: str,
    description: str,
    country: str = "",
    work_mode: str = "",
) -> dict:
    """Score how likely a role accepts international/EU-based candidates."""
    blob = f"{title} {description}"
    seed = match_seed_employer(employer)
    score = 0
    reasons: list[str] = []

    if seed and seed.get("foreigner_friendly"):
        score += 5
        reasons.append(f"Known EU health-tech employer ({seed.get('name')})")

    if FOREIGNER_FRIENDLY_RE.search(blob):
        score += 4
        reasons.append("Explicit international/relocation/English signals")

    mode = (work_mode or "").lower()
    if "remote" in mode:
        score += 3
        reasons.append("Remote role")
    elif "hybrid" in mode:
        score += 1

    etype = classify_employer_type(employer, description)
    if etype in ("startup", "scaleup", "private", "consulting"):
        score += 2
        reasons.append(f"{etype.replace('_', ' ').title()} employer")
    elif etype in ("public_sector", "hospital"):
        score -= 3
        reasons.append("Public-sector/hospital (harder for foreigners)")

    if FOREIGNER_HARD_BLOCK_RE.search(blob):
        score -= 6
        reasons.append("Local citizenship/licensure requirement")

    if re.search(r"\benglish\b", blob, re.I):
        score += 1

    tier = "high" if score >= 6 else ("medium" if score >= 3 else "low")
    return {
        "foreigner_score": score,
        "foreigner_tier": tier,
        "employer_type": etype,
        "foreigner_reasons": reasons,
        "startup_match": bool(seed),
        "startup_name": seed.get("name") if seed else "",
    }
