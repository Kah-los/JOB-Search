#!/usr/bin/env python3
"""
Merge web-discovered career URLs (data/discovered_urls.json) back into
data/facilities_resolved.json: sets resolved_url, ats, clears still_blank.
Re-runnable; safe to call after each discovery batch.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACS = ROOT / "data" / "facilities_resolved.json"
DISC = ROOT / "data" / "discovered_urls.json"


def detect_ats(url):
    low = (url or "").lower()
    table = {"myworkdayjobs.com": "Workday", "oraclecloud.com": "OracleORC",
             "icims.com": "iCIMS", "taleo.net": "Taleo", "ultipro.com": "UltiPro",
             "ukg.com": "UltiPro", "silkroad.com": "SilkRoad",
             "greenhouse.io": "Greenhouse", "lever.co": "Lever",
             "smartrecruiters.com": "SmartRecruiters"}
    for frag, name in table.items():
        if frag in low:
            return name
    return None


def main():
    facs = json.loads(FACS.read_text())
    disc = json.loads(DISC.read_text())
    by_id = {f["id"]: f for f in facs}
    n = 0
    for k, v in disc.items():
        if k.startswith("_"):
            continue
        fid = int(k)
        f = by_id.get(fid)
        if not f:
            continue
        f["resolved_url"] = v["url"]
        f["ats"] = v.get("ats") or detect_ats(v["url"])
        f["resolve_method"] = "web-discovered"
        f["still_blank"] = False
        n += 1
    FACS.write_text(json.dumps(facs, indent=2))
    blanks = sum(1 for f in facs if f.get("still_blank"))
    resolved = sum(1 for f in facs if f.get("resolved_url"))
    print(f"Merged {n} discovered URLs")
    print(f"Now resolved: {resolved}/{len(facs)} | still blank: {blanks}")


if __name__ == "__main__":
    main()
