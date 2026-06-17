"""Language detection, scoring, and C1/C2 exclusion for Europe jobs."""

import re

# Languages we detect in postings
LANG_PATTERNS = {
    "english": re.compile(
        r"\b(english|engelska|fluent english|native english|english.?speaking|"
        r"english.?speaking environment|business english)\b", re.I),
    "swedish": re.compile(r"\b(swedish|svenska|flytande svenska|modersmål svenska)\b", re.I),
    "german": re.compile(r"\b(german|deutsch|fließend deutsch|muttersprache deutsch)\b", re.I),
    "french": re.compile(r"\b(french|français|francais|courant en français)\b", re.I),
    "danish": re.compile(r"\b(danish|dansk|flydende dansk)\b", re.I),
    "norwegian": re.compile(r"\b(norwegian|norsk|flytende norsk)\b", re.I),
    "finnish": re.compile(r"\b(finnish|suomi|suomen kieli)\b", re.I),
    "dutch": re.compile(r"\b(dutch|nederlands|vloeiend nederlands)\b", re.I),
    "spanish": re.compile(r"\b(spanish|español|espanol|castellano)\b", re.I),
    "italian": re.compile(r"\b(italian|italiano)\b", re.I),
}

REQUIRED_RE = re.compile(r"\b(required|mandatory|must|necessary|krav|erforderlich|obligatoire)\b", re.I)
PREFERRED_RE = re.compile(r"\b(preferred|meritorious|meriterande|wünschenswert|souhaité|plus)\b", re.I)
C1C2_RE = re.compile(
    r"\b(C1|C2|CEFR\s*C[12]|native\s+(?:swedish|german|french|danish|norwegian|finnish|dutch)|"
    r"modersmål|muttersprache|langue maternelle|flytande\s+(?:svenska|danska|norska)(?:\s+och)?(?:\s+engelska)?)\b",
    re.I)
ENGLISH_ENV_RE = re.compile(r"\benglish.?speaking\s+(?:environment|workplace|office|team)\b", re.I)

# Rough heuristic: is description predominantly English?
ENGLISH_WORDS = re.compile(
    r"\b(the|and|with|experience|healthcare|clinical|patient|management|"
    r"information|analyst|specialist|team|role|skills|requirements)\b", re.I)


def _country_default_languages(country: str) -> list[str]:
    c = (country or "").lower()
    defaults = {
        "sweden": ["Swedish", "English"],
        "se": ["Swedish", "English"],
        "denmark": ["Danish", "English"],
        "dk": ["Danish", "English"],
        "norway": ["Norwegian", "English"],
        "no": ["Norwegian", "English"],
        "finland": ["Finnish", "English"],
        "fi": ["Finnish", "English"],
        "germany": ["German", "English"],
        "de": ["German", "English"],
        "france": ["French", "English"],
        "fr": ["French", "English"],
        "netherlands": ["Dutch", "English"],
        "nl": ["Dutch", "English"],
        "ireland": ["English"],
        "ie": ["English"],
        "united kingdom": ["English"],
        "uk": ["English"],
        "u.k": ["English"],
        "switzerland": ["German", "French", "English"],
        "ch": ["German", "French", "English"],
    }
    for key, langs in defaults.items():
        if key in c:
            return langs
    return ["English"]


def extract_languages(title: str, description: str, country: str = "") -> list[str]:
    blob = f"{title} {description}"
    found = []
    for lang, pat in LANG_PATTERNS.items():
        if pat.search(blob):
            found.append(lang.capitalize() if lang != "english" else "English")
    if not found:
        return _country_default_languages(country)
    if "English" not in found and ENGLISH_WORDS.search(blob):
        found.append("English (inferred from description)")
    return found


def requires_c1_c2_local(title: str, description: str) -> bool:
    """Exclude jobs requiring C1/C2 native-level local language without English."""
    blob = f"{title} {description}"
    if not C1C2_RE.search(blob):
        return False
    # C1/C2 Swedish/German only without English mention → exclude
    has_local_c = bool(re.search(
        r"\b(C1|C2|native|modersmål|muttersprache)\b.*\b(swedish|german|french|danish|norwegian|finnish|dutch|svenska|deutsch)\b",
        blob, re.I))
    has_english = bool(LANG_PATTERNS["english"].search(blob)) or ENGLISH_ENV_RE.search(blob)
    return has_local_c and not has_english


def score_language(title: str, description: str, country: str, languages: list[str]) -> dict:
    blob = f"{title} {description}".lower()
    langs_lower = [l.lower() for l in languages]

    # Priority tier
    if ENGLISH_ENV_RE.search(blob):
        tier, pts = "high", 9
        flag = "English-speaking environment"
    elif re.search(r"english.*(required|mandatory|must)", blob, re.I):
        tier, pts = "high", 10
        flag = "English required"
    elif "english" in langs_lower and REQUIRED_RE.search(blob):
        tier, pts = "high", 10
        flag = "English required"
    elif re.search(r"english.*(preferred|meritorious|plus)", blob, re.I) or PREFERRED_RE.search(blob) and "english" in blob:
        tier, pts = "medium", 8
        flag = "English preferred"
    elif ENGLISH_WORDS.search(blob) and len(blob) > 100:
        tier, pts = "high", 7
        flag = "English description"
    elif "english" in langs_lower:
        tier, pts = "medium", 4
        flag = "English optional"
    elif any(l in langs_lower for l in ("swedish", "german", "french", "danish", "norwegian", "finnish", "dutch")):
        tier, pts = "low", 0
        flag = "Local language focus"
    else:
        tier, pts = "medium", 4
        flag = "English likely"

    return {
        "languages": languages,
        "english_priority": tier,
        "english_flag": flag,
        "language_score": pts,
    }


def summarize(description: str, max_len: int = 220) -> str:
    if not description:
        return ""
    text = re.sub(r"\s+", " ", description.strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"
