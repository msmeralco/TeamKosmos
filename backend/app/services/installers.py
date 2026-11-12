"""Solar installers registered with the DOE (data/doe_installers.json, built by scripts/build_installers.py).

Registered is not recommended: the DOE publishes the registry as a reference for government buyers and states it
does not endorse any firm. Everything shown to a customer says so. The table is built here from the data file,
never written by the model, so names and contacts cannot be invented.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..config import BACKEND_DIR

DATA = Path(BACKEND_DIR) / "data" / "doe_installers.json"
PAGE = 12  # rows shown before "show all"
SOURCE_URL = "https://doe.gov.ph/official-doe-solar-pv-installer-registry-updated-as-of-july-13-2026"

REGION_NAMES = {
    "NCR": "Metro Manila (NCR)", "III": "Central Luzon (Region III)", "IV-A": "CALABARZON (Region IV-A)", "IV-B": "MIMAROPA (Region IV-B)",
    "I": "Ilocos Region (Region I)", "II": "Cagayan Valley (Region II)", "V": "Bicol Region (Region V)", "VI": "Western Visayas (Region VI)",
    "VII": "Central Visayas (Region VII)", "VIII": "Eastern Visayas (Region VIII)", "IX": "Zamboanga Peninsula (Region IX)",
    "X": "Northern Mindanao (Region X)", "XI": "Davao Region (Region XI)", "XII": "SOCCSKSARGEN (Region XII)", "XIII": "Caraga (Region XIII)",
    "CAR": "Cordillera (CAR)", "BARMM": "Bangsamoro (BARMM)",
}
# First match wins, so NCR (which holds "Quezon City") is tried before CALABARZON (which holds "Quezon" province).
PLACES: list[tuple[str, str]] = [
    ("NCR", r"metro manila|\bncr\b|national capital|\bmanila\b|quezon city|makati|pasig|taguig|mandaluyong|san juan city|marikina|pasay|para[nñ]aque|las pi[nñ]as|muntinlupa|caloocan|malabon|navotas|valenzuela|pateros|\bbgc\b|ortigas|cubao|alabang|fairview|novaliches"),
    ("III", r"central luzon|region (?:iii|3)\b|bulacan|pampanga|bataan|tarlac|nueva ecija|zambales|aurora|angeles|san fernando|olongapo|malolos|meycauayan|balanga|cabanatuan|baliuag|guiguinto"),
    ("IV-A", r"calabarzon|region (?:iv-a|4a)|cavite|laguna|batangas|rizal|\bquezon\b|lucena|antipolo|bacoor|dasmari|\bimus\b|calamba|santa rosa|bi[nñ]an|lipa|tanauan|cainta|taytay|san pedro|general trias|silang|tagaytay"),
    ("IV-B", r"mimaropa|region (?:iv-b|4b)|mindoro|palawan|marinduque|romblon|puerto princesa|calapan"),
    ("I", r"ilocos|region (?:i|1)\b|pangasinan|la union|dagupan|laoag|vigan"),
    ("II", r"cagayan valley|region (?:ii|2)\b|cagayan|isabela|nueva vizcaya|quirino|tuguegarao|bayombong"),
    ("V", r"bicol|region (?:v|5)\b|albay|camarines|sorsogon|catanduanes|masbate|legazpi|\bnaga\b"),
    ("VI", r"western visayas|region (?:vi|6)\b|iloilo|bacolod|negros occidental|capiz|antique|aklan|guimaras|roxas city|boracay"),
    ("VII", r"central visayas|region (?:vii|7)\b|cebu|bohol|negros oriental|siquijor|mandaue|lapu-?lapu|talisay|dumaguete|tagbilaran"),
    ("VIII", r"eastern visayas|region (?:viii|8)\b|leyte|samar|biliran|tacloban|ormoc"),
    ("IX", r"zamboanga|region (?:ix|9)\b"),
    ("X", r"northern mindanao|region (?:x|10)\b|cagayan de oro|misamis|bukidnon|iligan|camiguin"),
    ("XI", r"davao|region (?:xi|11)\b|tagum|digos"),
    ("XII", r"soccsksargen|region (?:xii|12)\b|cotabato|sultan kudarat|sarangani|general santos|koronadal|kidapawan"),
    ("XIII", r"caraga|region (?:xiii|13)\b|surigao|butuan|agusan"),
    ("CAR", r"cordillera|\bcar\b|baguio|benguet|ifugao|kalinga|apayao|abra\b|mountain province"),
    ("BARMM", r"bangsamoro|barmm|maguindanao|lanao del sur|basilan|sulu|tawi-?tawi|marawi"),
]
RESET = re.compile(r"another|different|other area|elsewhere|somewhere else|change (?:my )?(?:area|location)", re.I)


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def region_for(text: str) -> str | None:
    t = (text or "").lower()
    for code, pat in PLACES:
        if re.search(pat, t):
            return code
    return None


def _rank(f: dict) -> tuple:
    lists = f["lists"]
    return (-(len(lists) == 2), -("Jul 13, 2026" in lists), -bool(f["website"]), f["name"].lower())


def near_term(text: str) -> str:
    """The city the user named ("I'm in Pasig City" -> "pasig"), or "" when they only gave a region or province."""
    t = re.sub(r"^\W*(?:i'?m|i am|we'?re|we are|my home is|located)?\s*(?:in|at|near|around|from)?\s+", "", (text or "").strip(), flags=re.I)
    t = re.sub(r"\s*(?:city|,.*)$", "", t, flags=re.I).strip().lower()
    return t if len(t) >= 4 and not re.fullmatch(r"(?:metro manila|ncr|central luzon|calabarzon|somewhere else|manila)", t) else ""


def find(region: str, show_all: bool = False, near: str = "") -> dict:
    d = _data()
    term = near_term(near)
    firms = sorted((f for f in d["firms"] if f["region"] == region), key=lambda f: (-bool(term and term in f["address"].lower()), *_rank(f)))
    nearby = sum(1 for f in firms if term and term in f["address"].lower())
    rows = firms if show_all else firms[:PAGE]
    return {"region": region, "region_name": REGION_NAMES.get(region, region), "total": len(firms), "shown": len(rows),
            "near": term.title() if nearby else "", "nearby": nearby, "rows": [_row(f) for f in rows], "lists": [x["label"] for x in d["lists"]], "disclaimer": d["disclaimer"], "source_url": SOURCE_URL}


def _area(address: str) -> str:
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return ", ".join(parts[-2:]) if len(parts) > 1 else address


def _name(n: str) -> str:
    """Registry names are legal names; "X doing business under the name and style of Y" reads better as "Y (X)"."""
    m = re.match(r"(.+?),?\s+doing business under the name and style of\s+(.+)", n, flags=re.I)
    return f"{m.group(2)} ({m.group(1)})" if m else n


def _row(f: dict) -> dict:
    return {"name": _name(f["name"]), "esco": f.get("esco", False), "area": _area(f["address"]), "address": f["address"],
            "phone": f["phones"][0] if f["phones"] else "", "email": f["emails"][0] if f["emails"] else "",
            "website": f["website"], "lists": f["lists"]}


def _site(url: str) -> str:
    if not url:
        return "–"
    full = url if url.startswith("http") else "https://" + url
    if re.search(r"[\s()|]", full):
        return url.replace("|", "")
    host = re.sub(r"^https?://(www\.)?", "", full).split("/")[0]
    label = "Facebook" if "facebook.com" in host or host == "fb.com" else "LinkedIn" if "linkedin.com" in host else host
    return f"[{label}]({full})"


def _on(lists: list[str]) -> str:
    return "Both lists" if len(lists) == 2 else ("Jul 2026 only" if "Jul 13, 2026" in lists else "Jan 2026 only")


def table_markdown(r: dict) -> str:
    """Customer-facing installer table, built only from the data file."""
    more = r["total"] - r["shown"]
    head = f"### Solar installers registered with the DOE in {r['region_name']}"
    order = f"{r['nearby']} with an address in {r['near']} come first, then firms on both DOE lists." if r.get("near") else "Firms on both DOE lists come first."
    sub = f"Showing {r['shown']} of {r['total']}. {order}" if more else f"{r['total']} firm{'s' if r['total'] != 1 else ''}. {order}"
    if not r["rows"]:
        return f"{head}\n\nThe DOE registry has no solar installers listed for this region."
    out = [head, "", sub, "", "| Installer | Area | Phone | Email | Website | DOE lists |", "|---|---|---|---|---|---|"]
    for x in r["rows"]:
        name = x["name"].replace("|", "")
        name = f"**{name}**" + (" (ESCO)" if x["esco"] else "")
        out.append(f"| {name} | {x['area'].replace('|', '')} | {x['phone'] or '–'} | {x['email'] or '–'} | {_site(x['website'])} | {_on(x['lists'])} |")
    out += ["", f"> The DOE lists these firms as registered and does not endorse any of them. Sol has not checked their prices, quality or service. "
                f"Confirm each firm's current registration and get at least two written quotes. ESCO means energy service company. "
                f"Only the first phone and email in the registry are shown. Source: [DOE Official Solar PV Installer Registry]({r['source_url']}) "
                f"({' and '.join(r['lists'])} lists)."]
    return "\n".join(out)
