"""Europe Jobs pipeline configuration — fully separate from U.S. pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data" / "europe"
JOBS_RAW = DATA / "jobs_raw.json"
JOBS_ENRICHED = DATA / "jobs_enriched.json"
MATCHES = DATA / "matches.json"
NEW_TODAY = DATA / "new_today.json"
SEEN = DATA / "seen.json"
EMPLOYERS_SEED = DATA / "employers_seed.json"
PROFILE_PATH = ROOT / "pipeline" / "profile_europe.json"
DASH = ROOT / "dashboard" / "europe" / "index.html"
DOCS_SEG_PATH = ROOT / "pipeline" / "dashboard_path_europe.txt"
DOCS_SEG_DEFAULT = "europe-jobs"

# Geographic scope — EU/EEA + UK + Switzerland + other European nations
EU_COUNTRY_CODES = {
    "at", "be", "bg", "hr", "cy", "cz", "dk", "ee", "fi", "fr", "de", "gr", "hu",
    "ie", "it", "lv", "lt", "lu", "mt", "nl", "no", "pl", "pt", "ro", "sk", "si",
    "es", "se", "ch", "is", "li", "uk", "gb",
}

EU_COUNTRY_NAMES = {
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic", "czechia",
    "denmark", "estonia", "finland", "france", "germany", "greece", "hungary",
    "ireland", "italy", "latvia", "lithuania", "luxembourg", "malta", "netherlands",
    "norway", "poland", "portugal", "romania", "slovakia", "slovenia", "spain",
    "sweden", "switzerland", "iceland", "liechtenstein", "united kingdom", "uk",
    "u.k", "great britain", "england", "scotland", "wales", "northern ireland",
}

# Forbidden aggregators / scam-prone boards
FORBIDDEN_SOURCES = {
    "glassdoor", "indeed", "jooble", "ziprecruiter", "monster", "careerbuilder",
    "simplyhired", "talent.com", "adzuna",
}

APPROVED_BOARDS = {
    "jobtech": "Arbetsförmedlingen (Sweden)",
    "eures": "EURES",
    "employer": "Employer career page",
    "nhs_jobs": "NHS Jobs (UK)",
    "varbi": "Varbi (Nordic regions)",
    "jobindex": "Jobindex.dk",
    "finn": "Finn.no",
    "jobbsafari": "Jobbsafari",
    "stepstone": "StepStone",
}

# Search terms aligned with health informatics CV
SEARCH_QUERIES = [
    "health informatics", "health information", "clinical informatics",
    "informatics", "EHR", "EMR", "Epic", "medical records", "HIM",
    "clinical documentation", "CDI", "data analyst healthcare",
    "healthcare data", "interoperability", "FHIR", "HL7",
    "quality improvement healthcare", "compliance healthcare",
    "digital health", "health IT", "information management",
]

# EURES location codes (country-level NUTS)
EURES_LOCATIONS = [
    "se", "dk", "no", "fi", "de", "nl", "be", "fr", "ie", "uk", "at", "ch",
    "es", "it", "pl", "pt", "cz", "gr", "hu", "ro", "bg", "hr", "si", "sk",
    "lt", "lv", "ee", "lu", "mt", "cy", "is", "li",
]

# Language scoring weights
LANGUAGE_POINTS = {
    "english_required": 10,
    "english_preferred": 8,
    "english_description": 7,
    "english_optional": 4,
    "english_environment": 9,
    "remote_europe": 3,
}

# US location signals to reject
US_LOCATION_RE_PATTERNS = [
    r"\b(united states|u\.s\.a?|usa)\b",
    r",\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b",
]
