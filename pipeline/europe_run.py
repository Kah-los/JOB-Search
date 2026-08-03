#!/usr/bin/env python3
"""
Europe pipeline: scrape -> score -> separate Europe dashboard.

Deliberately NOT limited to Epic roles. Targets health informatics, digital
health / eHealth, health data, medical informatics and clinical IT roles across
European employers (health-IT vendors, medtech, national eHealth bodies, EU
agencies, hospitals).

Key differences from the US pipeline:
  * No USD salary floor. European postings rarely disclose salary, and when they
    do it is EUR/GBP/SEK/DKK/NOK/CHF, so a USD threshold would wrongly exclude.
  * Visa logic is inverted: the candidate lives in Stockholm, so EU/EEA roles
    need NO sponsorship (flagged as an advantage). UK/CH roles do need a permit.
  * Multilingual title matching (SV/DA/NO/NL/DE) alongside English.

Outputs: data/europe_matches.json, dashboard/europe.html, docs/<seg>/europe.html
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape import (scrape_teamtailor, scrape_workday, scrape_smartrecruiters,
                    scrape_greenhouse, scrape_lever, scrape_oracle, scrape_phenom)

ROOT = Path(__file__).resolve().parent.parent
EMPLOYERS = ROOT / "pipeline" / "europe_employers.json"
PROFILE = ROOT / "pipeline" / "profile.json"
RAW = ROOT / "data" / "europe_jobs_raw.json"
OUT = ROOT / "data" / "europe_matches.json"
SEEN = ROOT / "data" / "europe_seen.json"
DASH = ROOT / "dashboard" / "europe.html"

ADAPTERS = {
    "Teamtailor": scrape_teamtailor, "Workday": scrape_workday,
    "SmartRecruiters": scrape_smartrecruiters, "Greenhouse": scrape_greenhouse,
    "Lever": scrape_lever, "OracleORC": scrape_oracle, "Phenom": scrape_phenom,
}

# EU/EEA: no work permit needed for a Stockholm-based EU/EEA resident.
EEA = {"sweden", "denmark", "norway", "finland", "iceland", "netherlands",
       "ireland", "belgium", "germany", "france", "italy", "spain", "poland",
       "austria", "portugal", "czechia", "czech republic", "hungary", "greece",
       "romania", "bulgaria", "croatia", "slovakia", "slovenia", "estonia",
       "latvia", "lithuania", "luxembourg", "malta", "cyprus"}
# In Europe but outside EEA freedom of movement -> permit required.
NON_EEA_EUROPE = {"united kingdom", "uk", "switzerland"}
EUROPE = EEA | NON_EEA_EUROPE

# Map city / country fragments found in job location strings -> country.
CITY_COUNTRY = {
    "stockholm": "Sweden", "gothenburg": "Sweden", "göteborg": "Sweden",
    "mölndal": "Sweden", "lund": "Sweden", "malmö": "Sweden", "uppsala": "Sweden",
    "linköping": "Sweden", "södertälje": "Sweden", "solna": "Sweden",
    "copenhagen": "Denmark", "københavn": "Denmark", "aarhus": "Denmark",
    "oslo": "Norway", "trondheim": "Norway", "bergen": "Norway",
    "helsinki": "Finland", "espoo": "Finland",
    "amsterdam": "Netherlands", "eindhoven": "Netherlands", "utrecht": "Netherlands",
    "nijmegen": "Netherlands", "maastricht": "Netherlands", "groningen": "Netherlands",
    "dublin": "Ireland", "cork": "Ireland",
    "brussels": "Belgium", "ghent": "Belgium", "leuven": "Belgium",
    "basel": "Switzerland", "zurich": "Switzerland", "zürich": "Switzerland",
    "geneva": "Switzerland", "grenzach": "Germany", "rotkreuz": "Switzerland",
    "london": "United Kingdom", "cambridge": "United Kingdom",
    "macclesfield": "United Kingdom", "luton": "United Kingdom",
    "manchester": "United Kingdom", "oxford": "United Kingdom",
    "berlin": "Germany", "munich": "Germany", "münchen": "Germany",
    "hamburg": "Germany", "erlangen": "Germany", "frankfurt": "Germany",
    "paris": "France", "lyon": "France", "warsaw": "Poland", "warszawa": "Poland",
    "barcelona": "Spain", "madrid": "Spain", "milan": "Italy", "rome": "Italy",
    "budapest": "Hungary", "prague": "Czechia", "vienna": "Austria",
    "lisbon": "Portugal", "athens": "Greece",
}


def job_country(job):
    """Resolve the country of the JOB (not the employer HQ). Returns None when
    the location clearly is not in Europe, or cannot be determined."""
    loc = (job.get("location") or "").lower()
    if not loc.strip():
        # Teamtailor RSS has no location; fall back to the employer's country,
        # which for those small Nordic employers is reliable.
        c = (job.get("employer_country") or "").split("/")[0].strip()
        return c if c.lower() in EUROPE else None
    for name in EUROPE:
        if re.search(rf"\b{re.escape(name)}\b", loc):
            return name.title() if name != "uk" else "United Kingdom"
    for city, country in CITY_COUNTRY.items():
        if city in loc:
            return country
    return None  # unknown or non-European (China, Americas, India, ...)

# Relevant role vocabulary — English + Nordic/Dutch/German equivalents.
TITLE_INCLUDE = re.compile(
    r"("
    r"informatic|informatik|informatik|health data|hälsodata|vårddata|"
    r"digital health|e-?health|e-?hälsa|ehälsa|digitalisering|"
    r"medical informatics|clinical informatics|health information|"
    r"\bhim\b|medical record|patientjournal|journalsystem|"
    r"\behr\b|\bemr\b|\bepj\b|epic|cerner|cambio|cosmic|takecare|"
    r"interoperab|\bhl7\b|\bfhir\b|snomed|terminolog|"
    r"data analyst|dataanalytiker|analytiker|analyst|analytics|analys|"
    r"business intelligence|\bbi\b|data engineer|datavetare|"
    r"data quality|datakvalitet|data governance|informationssäkerhet|"
    r"compliance|regulatory|regulatorisk|kvalitet|quality|"
    r"\bgdpr\b|privacy|integritet|dataskydd|"
    r"project manager|projektledare|programledare|program manager|"
    r"product owner|produktägare|product manager|"
    r"implementation|införande|utredare|verksamhetsutvecklare|"
    r"business analyst|kravanalytiker|systemförvaltare|förvaltningsledare|"
    r"clinical systems|vårdsystem|application (analyst|specialist|consultant)|"
    r"consultant|konsult|specialist|coordinator|koordinator|"
    r"medical affairs|health econom|epidemiolog|registry|register|"
    r"standardisering|architect|arkitekt"
    r")", re.I)

# A role must be anchored in health/care/clinical data to qualify. Without this,
# generic "compliance"/"analyst" titles (travel & expense, procurement, finance)
# flood the results from large pharma employers.
HEALTH_CONTEXT = re.compile(
    r"(health|hälsa|hälso|vård|sjukvård|sundhed|helse|zorg|gesundheit|"
    r"clinical|klinisk|patient|patienter|medical|medicin|care|"
    r"\behr\b|\bemr\b|\bepj\b|journal|epic|cerner|cambio|cosmic|"
    r"\bhl7\b|\bfhir\b|snomed|\bicd\b|life science|pharma|läkemedel|"
    r"biolog|genomic|diagnost|radiolog|oncolog|epidemiolog|"
    r"medtech|e-?health|e-?hälsa|digital health|telemedicin)", re.I)

TITLE_EXCLUDE = re.compile(
    r"("
    r"travel (and|&) expense|\bt&e\b|expense (analyst|compliance)|"
    r"procurement|purchasing|payroll|accounts payable|tax |audit fee|"
    r"\bnurse\b|sjuksköterska|undersköterska|läkare|physician|surgeon|"
    r"barnmorska|fysioterapeut|physiotherap|psycholog|psykolog|"
    r"pharmacist|farmaceut|apotekare|dentist|tandläkare|veterinar|"
    r"cleaner|städ|vaktmästare|kock|chef de|driver|chaufför|"
    r"sales representative|säljare|account executive|recruiter|rekryterare|"
    r"software engineer|mjukvaruutvecklare|frontend|front-end|backend|back-end|"
    r"full.?stack|devops|\bsre\b|embedded|firmware|test engineer|"
    r"mechanical|electrical engineer|construction|internship|praktik|thesis|exjobb"
    r")", re.I)


def load(p, d):
    try:
        return json.loads(p.read_text())
    except Exception:
        return d


def title_relevant(t, job=None):
    t = t or ""
    if TITLE_EXCLUDE.search(t):
        return False
    if not TITLE_INCLUDE.search(t):
        return False
    # Require a health/care/clinical anchor in the title or description.
    if job is not None:
        blob = t + " " + (job.get("description") or "")
        if not HEALTH_CONTEXT.search(blob):
            return False
    return True


def score_job(job, profile):
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    blob = title + "  " + desc
    reasons = []

    # title fit
    hv = ["informatic", "health data", "digital health", "ehealth", "e-health",
          "ehälsa", "health information", "ehr", "epj", "interoperab", "fhir",
          "hl7", "data quality", "data governance", "analyst", "analytiker",
          "project manager", "projektledare", "business analyst", "clinical",
          "medical record", "registry", "compliance", "privacy", "gdpr",
          "product owner", "verksamhetsutvecklare", "systemförvaltare"]
    hits = [w for w in hv if w in title]
    title_fit = min(1.0, 0.55 + 0.15 * len(hits)) if hits else 0.35
    if hits:
        reasons.append("Title: " + ", ".join(hits[:3]))

    # skills
    skills = [s for grp in profile["skills"].values() for s in grp]
    sk = sorted({s for s in skills if s.lower() in blob})
    denom = 6.0 if len(desc) > 1500 else (4.0 if len(desc) > 400 else 3.0)
    skills_match = min(1.0, len(sk) / denom)
    if sk:
        reasons.append("Skills: " + ", ".join(sk[:5]))

    # domain
    dom = [d for d in profile["domains"]
           if any(w in blob for w in d.lower().split() if len(w) > 4)]
    domain_rel = min(1.0, len(dom) / 3.0)

    # location advantage, based on the JOB's country: Sweden > EEA > UK/CH
    country = (job.get("job_country") or "")
    cl = country.lower()
    if cl == "sweden":
        loc = 1.0
    elif cl in EEA:
        loc = 0.85
    else:
        loc = 0.55

    score = round(10 * (0.40 * title_fit + 0.25 * skills_match +
                        0.15 * domain_rel + 0.20 * loc), 1)

    needs_visa = cl in NON_EEA_EUROPE
    return {
        "fit_score": score,
        "reasons": reasons,
        "needs_visa": needs_visa,
        "no_visa_needed": not needs_visa,
        "passes": score >= 6.0,
    }


def main():
    profile = load(PROFILE, None)
    if not profile:
        sys.exit("profile.json missing")
    emp = load(EMPLOYERS, {}).get("employers", [])
    scrapable = [e for e in emp if e.get("ats") in ADAPTERS]
    print(f"Europe employers: {len(emp)} | scrapable now: {len(scrapable)}")

    all_jobs = []
    for e in scrapable:
        fn = ADAPTERS[e["ats"]]
        try:
            jobs = fn(e["url"], e["name"])
        except Exception as ex:
            jobs = []
            print(f"  [err] {e['name']}: {ex}")
        for j in jobs:
            j["employer_country"] = e.get("country", "")
            j["employer_city"] = e.get("city", "")
            j["employer_category"] = e.get("category", "")
            if not j.get("location"):
                j["location"] = f"{e.get('city','')}, {e.get('country','')}".strip(", ")
        all_jobs += jobs
        print(f"  {e['name'][:38]:38} {e['ats']:16} +{len(jobs)}")
    RAW.write_text(json.dumps(all_jobs, indent=2))

    # score
    seen = load(SEEN, {})
    today = date.today().isoformat()
    matches, new_today = [], []
    dropped_non_eu = 0
    for j in all_jobs:
        if not title_relevant(j.get("title"), j):
            continue
        # Resolve the country of the JOB itself. Employer HQ is not a proxy:
        # AstraZeneca (HQ Sweden/UK) posts roles in China, the US, Poland...
        c = job_country(j)
        if not c:
            dropped_non_eu += 1
            continue
        j["job_country"] = c
        s = score_job(j, profile)
        if not s["passes"]:
            continue
        url = j["url"]
        is_new = url not in seen
        rec = {
            "title": j.get("title"), "employer": j.get("employer"),
            "country": j.get("job_country"), "city": j.get("employer_city"),
            "category": j.get("employer_category"),
            "location": j.get("location"), "date_posted": j.get("date_posted", ""),
            "fit_score": s["fit_score"], "url": url,
            "needs_visa": s["needs_visa"], "remote": j.get("remote_type", ""),
            "source_platform": j.get("source_platform"),
            "reasons": s["reasons"], "first_seen": seen.get(url, today),
        }
        matches.append(rec)
        seen[url] = rec["first_seen"]
        if is_new:
            new_today.append(rec)

    matches.sort(key=lambda r: -r["fit_score"])
    OUT.write_text(json.dumps(matches, indent=2))
    SEEN.write_text(json.dumps(seen, indent=2))
    write_dashboard(matches, new_today)
    print(f"\nScraped {len(all_jobs)} jobs | dropped non-European: {dropped_non_eu} "
          f"| Europe matches (>=6): {len(matches)} | new: {len(new_today)}")
    print(f"Dashboard: {DASH}")
    return matches, new_today


def write_dashboard(matches, new_today):
    from html import escape as esc
    new_urls = {r["url"] for r in new_today}
    no_visa = sum(1 for r in matches if not r["needs_visa"])
    sweden = sum(1 for r in matches if "sweden" in (r["country"] or "").lower())
    rows = []
    for r in matches:
        cls = "is-new" if r["url"] in new_urls else ""
        sc = r["fit_score"]
        fit_cls = "fit-hi" if sc >= 8 else ("fit-mid" if sc >= 7 else "fit-lo")
        visa = ('<span class="pill-visa">Permit needed</span>' if r["needs_visa"]
                else '<span class="pill-ok">No visa needed</span>')
        newt = '<span class="new-tag">NEW</span>' if r["url"] in new_urls else ""
        rows.append(
            f'<tr class="{cls}" data-search="{esc((r["title"]+" "+r["employer"]+" "+(r["country"] or "")).lower(), quote=True)}" '
            f'data-country="{esc(r["country"] or "", quote=True)}" data-fit="{sc}">'
            f'<td class="c-title"><a href="{esc(r["url"], quote=True)}" target="_blank" rel="noopener">{esc(r["title"] or "")}</a>{newt}'
            f'<span class="src">{esc(r.get("category") or "")}</span></td>'
            f'<td class="c-emp">{esc(r["employer"] or "")}</td>'
            f'<td class="c-loc">{esc(r["location"] or "")}</td>'
            f'<td>{visa}</td>'
            f'<td class="mono" style="color:var(--muted);font-size:12.5px">{esc((r.get("date_posted") or "")[:12])}</td>'
            f'<td data-sort="{sc}"><span class="fit {fit_cls}"><b>{sc}</b>'
            f'<i style="width:{min(100, sc*10):.0f}%"></i></span></td>'
            f'</tr>')

    countries = sorted({r["country"] for r in matches if r["country"]})
    opts = "".join(f"<option>{esc(c)}</option>" for c in countries)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Carlos Adabe — Europe: Health Informatics &amp; Digital Health</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f6f7f9;--surface:#fff;--ink:#14171c;--text:#3c434f;--muted:#6b7280;
--line:#e6e8ec;--line-soft:#eef0f3;--header:#0d2436;--header-2:#12304a;
--accent:#0d7c6c;--accent-ink:#0a655a;--accent-soft:#e6f2ef;
--hi:#0a7a4d;--mid:#a9760f;--lo:#7a828f;--ease:cubic-bezier(.23,1,.32,1)}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.mono{{font-family:'JetBrains Mono',monospace;font-variant-numeric:tabular-nums}}
header{{background:linear-gradient(180deg,var(--header),var(--header-2));color:#eef0f3;padding:20px 28px 16px}}
header h1{{margin:0;font-size:19px;font-weight:600;letter-spacing:-.02em;color:#fff}}
header h1 .dot{{color:#3fd9bf}}
.meta{{color:#9fb3c4;font-size:12.5px;margin-top:3px}}
.stats{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.stat{{display:flex;flex-direction:column;padding:7px 13px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);border-radius:9px;min-width:80px}}
.stat b{{font-size:18px;color:#fff;font-weight:600}} .stat span{{font-size:11px;color:#9fb3c4}}
.stat.accent b{{color:#3fd9bf}}
.toolbar{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 28px;background:rgba(246,247,249,.94);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20;backdrop-filter:blur(8px)}}
input[type=search],select{{font:inherit;font-size:13.5px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:9px 12px;transition:border-color .14s var(--ease),box-shadow .14s var(--ease)}}
input[type=search]{{flex:1 1 260px;min-width:200px}}
input:focus,select:focus{{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}}
.toggle{{display:inline-flex;align-items:center;gap:7px;font-size:13px;padding:9px 12px;background:var(--surface);border:1px solid var(--line);border-radius:9px;cursor:pointer}}
.toggle.on{{border-color:var(--accent);background:var(--accent-soft);color:var(--accent-ink)}}
.count{{margin-left:auto;font-size:12.5px;color:var(--muted)}} .count b{{color:var(--ink)}}
.wrap{{padding:0 16px 60px}}
table{{width:100%;border-collapse:separate;border-spacing:0;background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(20,23,28,.04),0 8px 24px -16px rgba(20,23,28,.18)}}
thead th{{position:sticky;top:57px;background:#fbfcfd;color:var(--muted);font-size:11px;letter-spacing:.04em;text-transform:uppercase;text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap}}
tbody td{{padding:11px 14px;border-bottom:1px solid var(--line-soft);vertical-align:middle}}
tbody tr{{transition:background-color .13s var(--ease)}}
@media(hover:hover){{tbody tr:hover{{background:#fafbfc}}}}
tr.is-new td:first-child{{box-shadow:inset 3px 0 0 var(--accent)}}
.c-title a{{color:var(--ink);font-weight:550;text-decoration:none}}
.c-title a:hover{{color:var(--accent-ink);text-decoration:underline;text-underline-offset:2px}}
.c-title .src{{display:block;font-size:11px;color:var(--muted);margin-top:2px}}
.new-tag{{margin-left:7px;font-size:10px;font-weight:600;color:var(--accent-ink);background:var(--accent-soft);padding:1px 6px;border-radius:999px}}
.c-emp{{font-weight:500;color:var(--text)}} .c-loc{{color:var(--muted);font-size:13px}}
.pill-ok{{font-size:11px;font-weight:600;color:#0a655a;background:#e3f2ef;padding:3px 9px;border-radius:999px;white-space:nowrap}}
.pill-visa{{font-size:11px;font-weight:600;color:#9a5800;background:#fbf0dc;padding:3px 9px;border-radius:999px;white-space:nowrap}}
.fit{{display:inline-flex;flex-direction:column;gap:3px;width:46px}}
.fit b{{font-size:13.5px;font-weight:650;font-family:'JetBrains Mono',monospace}}
.fit i{{height:3px;border-radius:2px;background:currentColor;opacity:.85}}
.fit-hi{{color:var(--hi)}} .fit-mid{{color:var(--mid)}} .fit-lo{{color:var(--lo)}}
.empty{{display:none;padding:60px;text-align:center;color:var(--muted)}} .empty.show{{display:block}}
@media(prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style></head><body>
<header>
  <h1>Europe<span class="dot">.</span> Health Informatics &amp; Digital Health</h1>
  <div class="meta">Health informatics · digital health · eHealth roles across Europe · updated {date.today().isoformat()}</div>
  <div class="stats">
    <div class="stat accent"><b>{len(matches)}</b><span>Matches</span></div>
    <div class="stat"><b>{len(new_today)}</b><span>New</span></div>
    <div class="stat"><b>{no_visa}</b><span>No visa needed</span></div>
    <div class="stat"><b>{sweden}</b><span>Sweden</span></div>
    <div class="stat"><b>{len(set(r['employer'] for r in matches))}</b><span>Employers</span></div>
  </div>
</header>
<div class="toolbar">
  <input id="q" type="search" placeholder="Search role, employer, country…" aria-label="Search">
  <select id="fc" aria-label="Filter by country"><option value="">All countries</option>{opts}</select>
  <label class="toggle"><input id="tv" type="checkbox"> No visa needed only</label>
  <div class="count" id="count"><b>{len(matches)}</b> of {len(matches)}</div>
</div>
<div class="wrap">
  <table><thead><tr>
    <th>Role</th><th>Employer</th><th>Location</th><th>Work permit</th><th>Posted</th><th>Fit</th>
  </tr></thead><tbody id="tb">{''.join(rows)}</tbody></table>
  <div class="empty" id="empty">No roles match these filters.</div>
</div>
<script>
const rows=[...document.querySelectorAll('#tb tr')];
const q=document.getElementById('q'),fc=document.getElementById('fc'),
      tv=document.getElementById('tv'),count=document.getElementById('count');
function filt(){{
  const t=q.value.trim().toLowerCase(),c=fc.value,v=tv.checked;let n=0;
  rows.forEach(r=>{{
    const ok=(!t||r.dataset.search.includes(t))&&(!c||r.dataset.country===c)
      &&(!v||!r.querySelector('.pill-visa'));
    r.hidden=!ok;if(ok)n++;
  }});
  count.innerHTML='<b>'+n+'</b> of '+rows.length;
  document.getElementById('empty').classList.toggle('show',n===0);
  tv.closest('.toggle').classList.toggle('on',tv.checked);
}}
[q,fc].forEach(e=>e.addEventListener('input',filt));tv.addEventListener('change',filt);
document.querySelectorAll('thead th').forEach((th,i)=>th.addEventListener('click',()=>{{
  const tb=document.getElementById('tb'),dir=th.dataset.d==='a'?'d':'a';
  document.querySelectorAll('thead th').forEach(o=>delete o.dataset.d);th.dataset.d=dir;
  [...tb.rows].sort((a,b)=>{{
    let x=a.cells[i].dataset.sort??a.cells[i].innerText,y=b.cells[i].dataset.sort??b.cells[i].innerText;
    const nx=parseFloat(x),ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny))return dir==='a'?nx-ny:ny-nx;
    return dir==='a'?(''+x).localeCompare(y):(''+y).localeCompare(x);
  }}).forEach(r=>tb.appendChild(r));
}}));
</script></body></html>"""
    DASH.parent.mkdir(parents=True, exist_ok=True)
    DASH.write_text(html)
    seg = (ROOT / "pipeline" / "dashboard_path.txt")
    if seg.exists():
        s = seg.read_text().strip()
        pub = ROOT / "docs" / s / "europe.html"
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(html)
        print(f"Published: {pub}")


if __name__ == "__main__":
    main()
