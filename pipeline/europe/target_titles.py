"""European health-informatics job titles by country — search + scoring source of truth."""

from __future__ import annotations

# Full titles grouped by primary market (used for scoring / dashboard reference)
TARGET_TITLES_BY_COUNTRY: dict[str, list[str]] = {
    "sweden": [
        "eHälsa-konsult",
        "Systemanalytiker inom eHälsa",
        "Affärsanalytiker inom e-hälsa",
        "Projektledare, eHälsa",
        "Verksamhetsutvecklare, IT",
        "Klinisk IT-specialist",
        "Informationshantering-specialist",
        "Journalsystem-analytiker",
        "Clinical Systems Specialist",
        "Healthcare IT Analyst",
        "Clinical Application Support Specialist",
        "Hospital Information Systems Analyst",
        "Medical Records Information Specialist",
        "Quality Assurance Engineer (Healthcare)",
        "Implementation Consultant (Healthcare IT)",
        "Test Analyst (Healthcare Systems)",
        "Healthcare IT Project Manager",
        "Health Data Analyst",
        "FHIR / HL7 Integration Specialist",
        "Clinical Data Integration Specialist",
        "Healthcare Interoperability Consultant",
        "Health Information Systems Developer",
    ],
    "denmark": [
        "eHealth Consultant",
        "Clinical Systems Analyst",
        "Health IT Analyst",
        "Healthcare Systems Analyst",
        "Digital Health Specialist",
        "Healthcare IT Project Manager",
        "HL7/FHIR Integration Specialist",
        "Healthcare IT Analyst",
        "eHealth Analyst",
        "Clinical Informatics Specialist",
        "Hospital Information Systems Analyst",
    ],
    "norway": [
        "eHealth Consultant",
        "Clinical Informatics Analyst",
        "Healthcare Systems Analyst",
        "Health IT Project Manager",
        "Clinical IT Specialist",
        "HIM (Health Information Management) Specialist",
        "Hospital Information Systems Analyst",
        "Healthcare IT Analyst",
        "Digital Health Specialist",
        "HL7/FHIR Integration Engineer",
    ],
    "finland": [
        "eHealth Specialist",
        "Clinical Systems Analyst",
        "Health IT Consultant",
        "Healthcare Data Analyst",
        "HL7/FHIR Integration Specialist",
        "Clinical Informatics Analyst",
        "Healthcare Systems Analyst",
        "Digital Health Specialist",
        "Health Information Systems Analyst",
    ],
    "uk": [
        "Clinical Systems Analyst",
        "Clinical Informatics Specialist",
        "Health IT Analyst",
        "NHS Digital Systems Analyst",
        "Healthcare Interoperability Specialist",
        "HL7/FHIR Integration Engineer",
        "Clinical Decision Support Specialist",
        "eHealth Solutions Analyst",
        "Healthcare IT Consultant",
        "Clinical Systems Consultant",
        "Health Informatics Specialist",
        "Healthcare Project Manager",
        "Digital Health Analyst",
        "Health Data Analyst",
    ],
    "netherlands": [
        "Clinical Systems Analyst",
        "eHealth Consultant",
        "Healthcare IT Specialist",
        "Health Informatics Analyst",
        "HL7/FHIR Integration Specialist",
        "Healthcare Data Analyst",
        "Healthcare Project Manager",
        "Clinical Decision Support Specialist",
        "Healthcare Systems Analyst",
        "Digital Health Specialist",
    ],
    "germany": [
        "eHealth-Consultant",
        "Klinischer Informatiker",
        "Systemanalytiker (Healthcare)",
        "Health-IT-Spezialist",
        "HL7/FHIR-Integrationsingenieur",
        "Gesundheitsinformations-Managementspezialist",
        "Healthcare IT Specialist",
        "Clinical Systems Analyst",
        "eHealth Solutions Consultant",
        "Health Data Analyst",
        "Healthcare Interoperability Specialist",
    ],
    "france": [
        "Consultant en eHealth / Santé Numérique",
        "Analyste Systèmes Cliniques",
        "Spécialiste Informatique Médicale",
        "Gestionnaire de l'Information Santé",
        "Ingénieur HL7/FHIR",
        "Healthcare IT Consultant",
        "Health Informatics Specialist",
        "Clinical Systems Analyst",
    ],
    "ireland": [
        "Clinical Systems Analyst",
        "Healthcare IT Consultant",
        "eHealth Specialist",
        "Health Informatics Analyst",
        "Healthcare Data Analyst",
        "Clinical Decision Support Specialist",
        "Healthcare Project Manager",
    ],
    "spain": [
        "Especialista en eSalud",
        "Analista de Sistemas Clínicos",
        "Consultor de Informática Médica",
        "Gestor de Información Sanitaria",
        "Especialista en Interoperabilidad HL7/FHIR",
        "Healthcare IT Specialist",
        "eHealth Consultant",
        "Health Data Analyst",
    ],
    "portugal": [
        "Especialista em eSaúde",
        "Analista de Sistemas Clínicos",
        "Consultor de Informática Médica",
        "Gestor de Informação Sanitária",
        "Especialista em Interoperabilidade HL7/FHIR",
        "Healthcare IT Specialist",
        "eHealth Consultant",
    ],
    "multinational": [
        "Healthcare IT Consultant",
        "Clinical Systems Consultant",
        "eHealth Solutions Consultant",
        "Digital Health Strategist",
        "Health Informatics Specialist",
        "Healthcare Data Analyst",
        "Solutions Architect (Healthcare)",
        "Healthcare Systems Specialist",
        "eHealth Solutions Manager",
        "Health Informatics Officer",
        "Healthcare Systems Analyst",
        "Clinical Informatics Analyst",
        "Healthcare Project Manager",
        "HL7/FHIR Integration Specialist",
        "Hospital Information Systems Analyst",
        "Medical Records Information Specialist",
        "Healthcare Interoperability Specialist",
        "Clinical Decision Support Specialist",
    ],
}

ALL_TARGET_TITLES: list[str] = []
_seen: set[str] = set()
for _titles in TARGET_TITLES_BY_COUNTRY.values():
    for t in _titles:
        key = t.lower().strip()
        if key not in _seen:
            _seen.add(key)
            ALL_TARGET_TITLES.append(t)

# API-friendly search terms (deduplicated) — used by board scrapers
SEARCH_QUERIES: list[str] = [
    # English / multinational
    "health informatics", "clinical informatics", "health information management",
    "health IT", "healthcare IT", "digital health", "eHealth", "e-health",
    "clinical systems", "hospital information systems", "health data analyst",
    "healthcare data analyst", "health informatics specialist",
    "clinical systems analyst", "healthcare systems analyst",
    "clinical decision support", "healthcare interoperability",
    "HL7", "FHIR", "integration specialist", "integration engineer",
    "medical records", "HIM", "EHR", "EMR", "Epic", "journalsystem",
    "implementation consultant healthcare", "healthcare project manager",
    "solutions architect healthcare", "clinical application support",
    "informatics officer", "digital health strategist",
    # Sweden
    "ehälsa", "e-hälsa", "systemanalytiker ehälsa", "affärsanalytiker ehälsa",
    "klinisk IT", "hälsoinformatik", "informationshantering vård",
    # Denmark / Norway
    "ehelse", "klinisk informatik",
    # Germany
    "klinischer informatiker", "gesundheitsinformatik", "health-IT",
    "gesundheitsinformation", "medizinische informatik",
    # France
    "santé numérique", "informatique médicale",
    # Spain / Portugal
    "esalud", "eSaúde", "informática médica", "informação sanitária",
]

SEARCH_QUERIES_BY_BOARD: dict[str, list[str]] = {
    "jobtech": [
        "ehälsa", "e-hälsa", "systemanalytiker inom ehälsa", "affärsanalytiker ehälsa",
        "projektledare ehälsa", "klinisk IT", "journalsystem", "hälsoinformatik",
        "health informatics", "FHIR", "HL7", "healthcare IT", "clinical informatics",
        "informationshantering vård", "digital health", "vårdnära digital",
    ],
    "jobindex": [
        "eHealth", "clinical systems analyst", "health IT", "digital health",
        "clinical informatics", "healthcare systems", "HL7", "FHIR",
        "hospital information systems", "health data analyst",
    ],
    "finn": [
        "ehelse", "eHealth", "clinical informatics", "health IT",
        "healthcare systems", "HIM", "HL7", "FHIR", "digital health",
        "klinisk IT", "hospital information systems",
    ],
    "jobbsafari": [
        "ehälsa", "e-hälsa", "systemanalytiker ehälsa", "klinisk IT", "journalsystem",
        "health informatics", "healthcare IT", "FHIR", "HL7", "digital health",
        "hälsoinformatik", "clinical informatics",
    ],
    "stepstone": [
        "eHealth", "klinischer informatiker", "gesundheitsinformatik",
        "health-IT", "medizinische informatik", "gesundheitsinformation",
        "HL7", "FHIR", "clinical systems", "healthcare IT", "health data analyst",
    ],
    "eures": SEARCH_QUERIES[:20],
    "employers": SEARCH_QUERIES[:12],
    "flexjobs": [
        "health informatics", "clinical informatics", "health IT", "healthcare IT",
        "digital health", "EHR", "medical records", "HIM", "FHIR", "HL7",
    ],
}
