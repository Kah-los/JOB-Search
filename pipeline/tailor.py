#!/usr/bin/env python3
"""
Step 5: For every matching job, generate a tailored CV + cover letter and save
the bundle (job posting JSON + CV.md + CoverLetter.md) under applications/.

These are template-driven, ATS-keyword-optimized drafts built from profile.json
and the specific job. They are strong first drafts; the top-scoring roles are
worth a hand polish.

Folder layout:
  applications/<state>/<Employer>__<job-slug>/
      job.json
      CV-<role-slug>.md
      Cover-Letter-<role-slug>.md
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "pipeline" / "profile.json").read_text())
APPS = ROOT / "applications"


def slug(s, n=50):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").strip()).strip("-").lower()
    return s[:n] or "role"


def matched_skills(job):
    blob = (job.get("title", "") + " " + job.get("description", "")).lower()
    hits = []
    for grp in PROFILE["skills"].values():
        for s in grp:
            if s.lower() in blob and s not in hits:
                hits.append(s)
    return hits


def _format_experience():
    blocks = []
    for role in PROFILE.get("experience", []):
        ctx = f" ({role['context']})" if role.get("context") else ""
        loc = f" – {role['location']}" if role.get("location") else ""
        blocks.append(
            f"**{role['title']}**\n"
            f"{role['employer']}{loc}{ctx} | {role['dates']}\n"
            + "\n".join(f"- {b}" for b in role.get("bullets", []))
        )
    return "\n\n".join(blocks)


def _format_education():
    lines = []
    for ed in PROFILE.get("education", []):
        loc = f", {ed['location']}" if ed.get("location") else ""
        lines.append(f"- {ed['degree']} — {ed['school']}{loc} ({ed['dates']})")
        for note in ed.get("notes", []):
            lines.append(f"  - {note}")
    return "\n".join(lines) if lines else "\n".join(f"- {c}" for c in PROFILE.get("credentials", [])[:2])


def _format_leadership():
    blocks = []
    for role in PROFILE.get("leadership", []):
        blocks.append(
            f"**{role['title']} – {role['organization']}** | {role['dates']}\n"
            + "\n".join(f"- {b}" for b in role.get("bullets", []))
        )
    return "\n\n".join(blocks)


def build_cv(job, scored):
    p = PROFILE
    role = job.get("title", "Health Informatics role")
    emp = job.get("employer", "")
    skills_hits = matched_skills(job) or sum(p["skills"].values(), [])[:8]
    keywords = ", ".join(skills_hits)
    summary = p.get("summary") or (
        f"Health Informatics Specialist with {p['years_experience']}+ years in health information "
        "management, EHR implementation, and healthcare data governance."
    )
    certs = p.get("certifications") or p.get("credentials", [])[2:]
    leadership = _format_leadership()
    leadership_block = f"\n## Leadership & Affiliations\n{leadership}\n" if leadership else ""
    return f"""# {p['name']}
**{role.upper()} — Application**

{p['location']} (open to U.S. relocation / remote) | {p['email']} | {p['phone']} | {p['linkedin']}

---

## Professional Summary
{summary} Applying for the **{role}** role at **{emp}**. Role-aligned strengths:
**{keywords}**.

## Core Competencies (prioritized for this role)
- **Health Informatics & Interoperability:** {', '.join(p['skills']['interoperability'])}
- **EHR/EMR:** {', '.join(p['skills']['ehr'])}
- **Data Analytics & BI:** {', '.join(p['skills']['analytics'])}
- **Governance & Compliance:** {', '.join(p['skills']['governance'])}
- **Leadership:** {', '.join(p['skills']['leadership'])}

## Selected Achievements
""" + "\n".join(f"- {h}" for h in p["highlights"]) + f"""

## Professional Experience
{_format_experience()}

## Education
{_format_education()}

## Certifications & Professional Development
""" + "\n".join(f"- {c}" for c in certs) + leadership_block


def build_cover_letter(job, scored):
    p = PROFILE
    role = job.get("title", "the role")
    emp = job.get("employer", "your organization")
    skills_hits = matched_skills(job)
    top = ", ".join(skills_hits[:4]) if skills_hits else "health informatics and EHR optimization"
    recent = (p.get("experience") or [{}])[0]
    recent_title = recent.get("title", "Senior Health Information Manager")
    return f"""{p['name']}
{p['email']} | {p['phone']} | {p['linkedin']}

Dear Hiring Team at {emp},

I am writing to apply for the **{role}** position. With over {p['years_experience']} years
leading health information management and health informatics initiatives, I was drawn to this
role because it sits squarely at the intersection of my experience: {top}.

As {recent_title} at Ho Teaching Hospital, I directed health information operations across
five inpatient wards and fourteen clinics, supporting more than 150 clinicians and over 105,000
annual patient visits. I served on the hospital-wide EHR implementation team where my work on
data migration, system validation, and end-user training contributed to a 30% improvement in
data integrity. I also applied Clinical Documentation Improvement practices — physician query
management, documentation audits, and clinician education — to strengthen record integrity and
coding accuracy.

What I would bring to {emp} specifically:
- Hands-on EHR/EMR implementation and optimization experience, including workflow design and go-live support.
- Healthcare data and analytics capability (SQL, Python, KPI dashboards) to turn operational data into decisions.
- A governance-first mindset grounded in HIPAA principles, patient privacy, and quality assurance.
- Proven leadership — I built and developed a team of 18 professionals and led cross-functional change.

I am completing a joint Master's in Health Informatics at Karolinska Institutet and Stockholm
University (Global Master's Scholarship recipient) and hold OpenEHR and Google Data Analytics
certifications. I would welcome the chance to discuss how my background maps to {emp}'s priorities
for this role.

Thank you for your consideration.

Sincerely,
{p['name']}
"""


def save_application(job, scored):
    state = slug(job.get("employer_state") or "us", 24) or "us"
    folder = APPS / state / f"{slug(job.get('employer'),30)}__{slug(job.get('title'),40)}"
    folder.mkdir(parents=True, exist_ok=True)
    rslug = slug(job.get("title"), 40)
    name_slug = slug(PROFILE.get("name", "candidate"), 30)
    (folder / "job.json").write_text(json.dumps({**job, "scoring": scored}, indent=2))
    (folder / f"{name_slug}-CV-{rslug}.md").write_text(build_cv(job, scored))
    (folder / f"Cover-Letter-{rslug}.md").write_text(build_cover_letter(job, scored))
    return str(folder.relative_to(ROOT))


if __name__ == "__main__":
    demo = {"employer": "Demo Health", "title": "Epic Systems Analyst",
            "description": "FHIR HL7 SQL Epic EHR HIPAA data governance", "employer_state": "Texas"}
    print(save_application(demo, {"fit_score": 8.0}))
