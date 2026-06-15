#!/usr/bin/env python3
"""One-off: add the user-supplied employers (new + upgrades), scrape the
scrapable ones, and fold relevant roles into jobs_enriched.json + jobs_raw.json.
Probes a few unknown sites for Phenom along the way."""
import json, sys
sys.path.insert(0, "pipeline")
from scrape import scrape_workday, scrape_oracle, scrape_phenom
from enrich import title_relevant

FACS = "data/facilities_resolved.json"
facs = json.load(open(FACS))
by_id = {f["id"]: f for f in facs}
next_id = max(f["id"] for f in facs) + 1

# ---- probe a few unknowns for Phenom ----
probes = {
    "Penn State Health": "https://www.pennstatehershey.jobs/jobs/",
    "Allegheny Health Network": "https://careers.highmarkhealth.org/brands/ahn/",
    "McKesson": "https://careers.mckesson.com/en",
}
for n, u in probes.items():
    try:
        ok = len(scrape_phenom(u, n, cap=20))
    except Exception:
        ok = 0
    print(f"  probe {n}: Phenom={ok}")

# ---- definitions: (name, state, url, ats, scraper) ----
WD, ORC, PH = scrape_workday, scrape_oracle, scrape_phenom
NEW = [
    ("Mount Nittany Health", "Pennsylvania", "https://mnh-ibosjb.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/MountNittanyHealthCareers/jobs", "OracleORC", ORC),
    ("Universal Health Services (UHS)", "Pennsylvania", "https://jobs.uhs.com/careers/jobs", "Phenom", PH),
    ("Medtronic", "Minnesota", "https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers", "Workday", WD),
    ("Humana", "Kentucky", "https://humana.wd5.myworkdayjobs.com/Humana_External_Career_Site", "Workday", WD),
    ("Leidos", "Virginia", "https://leidos.wd5.myworkdayjobs.com/External", "Workday", WD),
    ("athenahealth", "Massachusetts", "https://athenahealth.wd1.myworkdayjobs.com/External", "Workday", WD),
]
# upgrades to existing facilities (id -> url, ats)
UPGRADES = {
    10: ("https://careers.ecuhealth.org/", "Phenom"),
    69: ("https://jobs.novanthealth.org/careers-home/jobs", "Phenom"),
    583: ("https://careers.chop.edu/", "Phenom"),
}
# verified-but-not-scrapable (record URL only, no adapter yet)
RECORD_ONLY = {
    1:  "https://careers.christushealth.org/",
    36: "https://jobs.utsouthwestern.edu/job-search-results/",     # Taleo
    20: "https://jobs.hackensackmeridianhealth.org/search-jobs",   # iCIMS-redirect
    64: "https://careers.atriumhealth.org/",                        # 403
    305:"https://www.commonspirit.careers/search-jobs",            # iCIMS-redirect
}

scrapers = {WD: "Workday", ORC: "OracleORC", PH: "Phenom"}
all_new_jobs = []

# apply upgrades + record-only
for fid, (url, ats) in UPGRADES.items():
    if fid in by_id:
        by_id[fid].update(resolved_url=url, ats=ats, still_blank=False)
for fid, url in RECORD_ONLY.items():
    if fid in by_id and not by_id[fid].get("resolved_url"):
        by_id[fid].update(resolved_url=url, still_blank=False)

# add new employers
for name, state, url, ats, fn in NEW:
    facs.append({"id": next_id, "name": name, "country": "U.S.", "state": state,
                 "resolved_url": url, "ats": ats, "still_blank": False,
                 "resolve_method": "user-supplied"})
    next_id += 1

# scrape the scrapable (new + upgraded)
to_scrape = [(n, s, u, fn) for n, s, u, a, fn in NEW]
to_scrape += [(by_id[i]["name"], by_id[i].get("state"), u, PH) for i, (u, a) in UPGRADES.items()]
for name, state, url, fn in to_scrape:
    try:
        jobs = fn(url, name)
    except Exception as e:
        jobs = []
        print(f"  [err] {name}: {e}")
    for j in jobs:
        j["employer_state"] = state
    all_new_jobs += jobs
    print(f"  scraped {name[:30]:30} +{len(jobs)}")

json.dump(facs, open(FACS, "w"), indent=2)

# fold relevant into enriched + raw
rel = [j for j in all_new_jobs if j.get("title") and title_relevant(j["title"])]
enr = json.load(open("data/jobs_enriched.json")); es = set(j["url"] for j in enr)
add = [j for j in rel if j["url"] not in es]; enr += add
json.dump(enr, open("data/jobs_enriched.json", "w"), indent=2)
raw = json.load(open("data/jobs_raw.json")); rs = set(j["url"] for j in raw)
raw += [j for j in all_new_jobs if j["url"] not in rs]
json.dump(raw, open("data/jobs_raw.json", "w"), indent=2)
print(f"\nTotal scraped: {len(all_new_jobs)} | relevant: {len(rel)} | newly-added to enriched: {len(add)}")
