"""Shared top navigation for U.S. and Europe job dashboards."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_seg(filename: str, default: str) -> str:
    path = ROOT / "pipeline" / filename
    return path.read_text().strip() if path.exists() else default


def us_segment() -> str:
    return _read_seg("dashboard_path.txt", "5b49cmxred")


def europe_segment() -> str:
    return _read_seg("dashboard_path_europe.txt", "europe-jobs")


SITE_NAV_CSS = """
.site-nav{
  display:flex;gap:10px;padding:12px 22px;background:#fff;border-bottom:1px solid var(--line);
  flex-wrap:wrap;align-items:center;
}
.site-nav a{
  font-size:13px;padding:7px 14px;background:var(--surface-2,#f8fafc);border:1px solid var(--line);
  border-radius:8px;text-decoration:none;color:var(--ink,#0f172a);font-weight:500;
  transition:background 140ms ease,border-color 140ms ease,color 140ms ease;
}
.site-nav a:hover{border-color:var(--primary,#0e7490);color:var(--primary-ink,#155e75)}
.site-nav a.on{
  background:var(--primary-soft,#cffafe);border-color:var(--primary,#0e7490);
  color:var(--primary-ink,#155e75);font-weight:600;pointer-events:none;cursor:default;
}
"""


def site_nav_html(active: str) -> str:
    us_on = " on" if active == "us" else ""
    eu_on = " on" if active == "europe" else ""
    return f"""<nav class="site-nav" id="siteNav" aria-label="Job dashboards">
  <a href="#" data-nav="us" class="nav-us{us_on}">🇺🇸 U.S. Jobs</a>
  <a href="#" data-nav="europe" class="nav-eu{eu_on}">🌍 Europe Jobs</a>
</nav>"""


def site_nav_js() -> str:
    us = us_segment()
    eu = europe_segment()
    return f"""
(function(){{
  const nav=document.getElementById('siteNav');
  if(!nav) return;
  const usSeg={json.dumps(us)};
  const euSeg={json.dumps(eu)};
  const path=location.pathname.replace(/\\\\/g,'/');
  const onPages=path.includes('github.io')||path.includes('/JOB-Search/');
  const isEurope=path.includes('/'+euSeg+'/')||path.includes('/europe/')||path.endsWith('/europe');
  let usHref,euHref;
  if(onPages){{
    const base=path.match(/^(.*\\/JOB-Search)/);
    const root=base?base[1]:'/JOB-Search';
    usHref=root+'/'+usSeg+'/';
    euHref=root+'/'+euSeg+'/';
  }}else if(isEurope){{
    usHref='../index.html';
    euHref='#';
  }}else{{
    usHref='#';
    euHref='europe/index.html';
  }}
  const aUs=nav.querySelector('[data-nav="us"]');
  const aEu=nav.querySelector('[data-nav="europe"]');
  if(aUs){{aUs.href=usHref;aUs.classList.toggle('on',!isEurope);}}
  if(aEu){{aEu.href=euHref;aEu.classList.toggle('on',isEurope);}}
}})();
"""
