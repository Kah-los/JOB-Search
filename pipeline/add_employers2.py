#!/usr/bin/env python3
"""Second employer batch: health-IT / consulting employers on scrapable ATS,
plus record-only URLs for custom sites. Scrapes, folds relevant into jobs_raw."""
import json, sys
sys.path.insert(0, "pipeline")
from scrape import scrape_workday, scrape_oracle, scrape_greenhouse
from enrich import title_relevant

FACS = "data/facilities_resolved.json"
facs = json.load(open(FACS))
by_id = {f["id"]: f for f in facs}
by_name = {f["name"].lower(): f for f in facs}
next_id = max(f["id"] for f in facs) + 1

WD, ORC, GH = scrape_workday, scrape_oracle, scrape_greenhouse
NEW = [
    ("Oracle Health (Cerner)", "Missouri", "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/jobsearch/jobs", "OracleORC", ORC),
    ("GDIT", "Virginia", "https://gdit.wd5.myworkdayjobs.com/External_Career_Site", "Workday", WD),
    ("Booz Allen Hamilton", "Virginia", "https://bah.wd1.myworkdayjobs.com/BAH_Jobs", "Workday", WD),
    ("Keck Medicine of USC", "California", "https://usc.wd5.myworkdayjobs.com/ExternalKeckUSCCareers", "Workday", WD),
    ("Cohere Health", "Massachusetts", "https://job-boards.greenhouse.io/coherehealth", "Greenhouse", GH),
]
# verified URLs for custom/non-scrapable sites (record only; need future adapters)
RECORD_NEW = [
    ("UTMB Health (Galveston)", "Texas", "https://applyjobs.utmb.edu/"),
    ("Penn State Health", "Pennsylvania", "https://www.pennstatehershey.jobs/jobs/"),
    ("Allegheny Health Network", "Pennsylvania", "https://careers.highmarkhealth.org/brands/ahn/"),
    ("Columbia University Irving Medical Center", "New York", "https://www.cuimc.columbia.edu/about-us/explore-cuimc/leadership-and-administration/administrative-offices/cuimc-human-resources/job-opportunities"),
    ("McKesson", "Texas", "https://careers.mckesson.com/en/search-jobs"),
]

all_new = []
for name, state, url, ats, fn in NEW:
    facs.append({"id": next_id, "name": name, "country": "U.S.", "state": state,
                 "resolved_url": url, "ats": ats, "still_blank": False,
                 "resolve_method": "user-supplied"})
    next_id += 1
    try:
        jobs = fn(url, name)
    except Exception as e:
        jobs = []; print(f"  [err] {name}: {e}")
    for j in jobs:
        j["employer_state"] = state
    all_new += jobs
    print(f"  scraped {name[:28]:28} +{len(jobs)}")

for name, state, url in RECORD_NEW:
    if name.lower() not in by_name:
        facs.append({"id": next_id, "name": name, "country": "U.S.", "state": state,
                     "resolved_url": url, "ats": None, "still_blank": False,
                     "resolve_method": "user-supplied-recordonly"})
        next_id += 1
        print(f"  recorded {name[:28]:28} (custom, not scraped)")

json.dump(facs, open(FACS, "w"), indent=2)

rel = [j for j in all_new if j.get("title") and title_relevant(j["title"])]
raw = json.load(open("data/jobs_raw.json")); rs = set(j["url"] for j in raw)
raw += [j for j in all_new if j["url"] not in rs]
json.dump(raw, open("data/jobs_raw.json", "w"), indent=2)
print(f"\nTotal scraped: {len(all_new)} | relevant: {len(rel)} | jobs_raw now: {len(raw)}")
