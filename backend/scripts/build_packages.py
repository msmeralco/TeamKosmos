"""Build data/solar_packages.json: ready-made home solar packages that installers publish on their own websites.

Usage (from backend/):  python scripts/build_packages.py
Every price is checked against the live page text (robots.txt respected, 1 request/second per site), and every
photo URL is checked to return an image. A mismatch stops the run, so the file cannot drift from its sources.
The details below were read from each page by hand. Photos are linked from the installer's site, not copied.
Packages without a real photo get a drawn illustration (frontend/public/packages/*.svg). A few made-up "sample" packages fill
gaps the real market data does not cover (grid-tied sizes, off-grid). They are flagged synthetic everywhere they appear.
shortcut: packages are curated by hand, so re-read the pages and edit this file when an installer changes its prices.
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.scraper import fetch  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "solar_packages.json"
ART = Path(__file__).resolve().parents[2] / "frontend" / "public" / "packages"

# Regions use the DOE registry codes: NCR = Metro Manila, III = Central Luzon, IV-A = CALABARZON.
# contact: published on the installer's own page. Every value is checked against that page when this script runs.
INSTALLERS = {
    "ptg": {"name": "PTG Solar", "site": "https://ptgsolarph.com/", "area": "Quezon City and Metro Manila", "regions": ["NCR"],
            "price_note": "Example price, full install", "photo": None,
            "contact": {"phones": ["+63 966 552 5258", "+63 998 810 6084"], "emails": ["quotes@ptgsolarph.com"],
                        "facebook": "https://www.facebook.com/profile.php?id=61590637263615", "messenger": "https://m.me/61590637263615", "whatsapp": "https://wa.me/639988106084"}},
    "devsolutions": {"name": "DevSolutions Solar", "site": "https://www.devsolutions.com.ph/", "area": "Cavite, Luzon and Palawan", "regions": ["IV-A", "NCR", "III"],
                     "price_note": "Starts at, all-in", "photo": "https://www.devsolutions.com.ph/og/home.jpg",
                     "contact": {"phones": ["+63 997 399 4613"], "facebook": "https://www.facebook.com/devsolutions.palawan",
                                 "office": "Silang, Cavite (Monday to Saturday, 9:00 AM to 6:00 PM)"}},
    "skyelight": {"name": "Skyelight Solar", "site": "https://skyelightsolar.com/", "area": "Bulacan and Metro Manila", "regions": ["III", "NCR"],
                  "price_note": "All-in package with installation", "photo": "https://skyelightsolar.com/images/hero-solar-1600.jpg",
                  "contact": {"phones": ["0917 631 6749", "0945 210 9890", "0952 459 4387"], "emails": ["business.skyelight.solar@gmail.com"],
                              "facebook": "https://www.facebook.com/skyelightsolar"}},
    "achiv": {"name": "Achiv Solar", "site": "https://achivsolar.com/", "area": "Metro Manila, Bulacan and Cebu", "regions": ["NCR", "III"],
              "price_note": "All-in, non-VAT", "photo": "https://achivsolar.com/metro-manila-hybrid-roof-array-aerial-2026.jpg",
              "contact": {"phones": ["+63 945 850 7938"], "viber": "+63 945 850 7938"}},
    "beyondpower": {"name": "Beyond Power Asia", "site": "https://beyondpower.asia/", "area": "Metro Manila", "regions": ["NCR"],
                    "price_note": "Fixed price installed, 50% down", "photo": "https://beyondpower.asia/wp-content/themes/beyondpower-child/assets/img/img-02.jpg",
                    "contact": {"phones": ["0927-433-4555"]}},
    "triple30": {"name": "Triple30 Renewables", "site": "https://triple30renewables.com/", "area": "Metro Manila and beyond", "regions": ["NCR"],
                 "price_note": "From, final price after a site survey", "photo": None,
                 "contact": {"phones": ["09955490515"], "emails": ["account@twinqophil.com"]}},
}

INSTALLERS["sample"] = {"name": "Sample installer (made-up)", "site": None, "area": "Metro Manila, Central Luzon and CALABARZON", "regions": ["NCR", "III", "IV-A"],
                        "price_note": "Made-up example price", "photo": None, "contact": None}

# Made-up packages for gaps. Prices follow the range of the real ones (about ₱50,000 to ₱60,000 per kWp grid-tied; batteries add the rest).
SAMPLES = [
    ("Sample grid-tied 4 kWp", 4.0, "stated", "7 × 580 W", "4 kW grid-tied inverter", None, 215000, "grid-tied"),
    ("Sample grid-tied 6.6 kWp", 6.6, "stated", "11 × 600 W", "6 kW grid-tied inverter", None, 335000, "grid-tied"),
    ("Sample grid-tied 8.4 kWp", 8.4, "stated", "14 × 600 W", "8 kW grid-tied inverter", None, 425000, "grid-tied"),
    ("Sample off-grid 3 kWp", 3.0, "stated", "5 × 600 W", "3 kW off-grid inverter", 10, 330000, "off-grid"),
    ("Sample off-grid 5 kWp", 5.0, "stated", "8 × 620 W", "5 kW off-grid inverter", 15, 470000, "off-grid"),
    ("Sample off-grid 8 kWp", 8.0, "stated", "13 × 620 W", "8 kW off-grid inverter", 20, 680000, "off-grid"),
]

# (installer, package name, kWp, kWp basis, panels, inverter, battery kWh or None, price)
P = [
    ("ptg", "Lowest We Install", 5.0, "stated", "8 panels", "Top One 5.6 kW inverter", None, 177700),
    ("ptg", "6kW System", 6.2, "stated", "10 panels", "Top One 6.2 kW inverter", 5, 237912),
    ("ptg", "Most Popular", 8.1, "stated", "13 panels", "Solis 8 kW inverter", 5, 313924),
    ("ptg", "10kW System", 9.9, "stated", "16 panels", "Solis 10 kW inverter", 10, 398795),
    ("ptg", "Whole-Home", 9.9, "stated", "16 panels", "GoodWe 10 kW inverter", 14.3, 458295),
    ("devsolutions", "5KW Hybrid System", 4.96, "stated", "8 × 620 W bifacial", "Hybrid inverter", 16, 337000),
    ("devsolutions", "6KW Hybrid System", 6.2, "stated", "10 × 620 W bifacial", "Hybrid inverter", 16, 378000),
    ("devsolutions", "8KW Hybrid System", 8.68, "stated", "14 × 620 W bifacial", "Hybrid inverter", 16, 467000),
    ("devsolutions", "10KW Hybrid System", 9.92, "stated", "16 × 620 W bifacial", "Hybrid inverter", 16, 533000),
    ("devsolutions", "12KW Hybrid System", 12.4, "stated", "20 × 620 W bifacial", "Hybrid inverter", 16, 614000),
    ("devsolutions", "16KW Hybrid System", 16.12, "stated", "26 × 620 W bifacial", "Hybrid inverter", 16, 760000),
    ("skyelight", "5 KW Hybrid (Option 1)", 2.5, "stated", "4 × 620 W bifacial", "5 kW hybrid inverter", 5.12, 245000),
    ("skyelight", "6 KW Hybrid", 6.2, "stated", "10 × 620 W bifacial", "6 kW hybrid inverter", 16.09, 355000),
    ("skyelight", "18 KW Hybrid", 18.6, "stated", "30 × 620 W bifacial", "18 kW hybrid inverter", 16.09, 815000),
    ("achiv", "Starter (Hybrid 5 kW)", 4.96, "panels × watts", "8 × 620 W", "5 kW inverter", 5.12, 290000),
    ("achiv", "Lite (Hybrid 6 kW)", 6.2, "panels × watts", "10 × 620 W", "6 kW inverter", 5.12, 340000),
    ("achiv", "Home (Hybrid 8 kW)", 9.92, "panels × watts", "16 × 620 W", "8 kW inverter", 10.24, 410000),
    ("achiv", "Max (Hybrid 12 kW)", 14.88, "panels × watts", "24 × 620 W", "12 kW inverter", 16, 600000),
    ("beyondpower", "6kW Hybrid Package", 6.25, "panels × watts", "10 × Trina 625 W", "Deye 6 kW hybrid", 16, 374000),
    ("beyondpower", "8kW Hybrid Package", 8.75, "panels × watts", "14 × Trina 625 W", "Deye 8 kW hybrid", 16, 441400),
    ("beyondpower", "12kW Hybrid Package", 12.5, "panels × watts", "20 × Trina 625 W", "Deye 12 kW hybrid", 16, 596900),
    ("beyondpower", "16kW Hybrid Package", 16.88, "panels × watts", "27 × Trina 625 W", "Deye 16 kW hybrid", 16, 731300),
    ("triple30", "Starter 3 kWp", 3.0, "stated", "6 × 550 W Tier-1", "3 kW hybrid-ready inverter", None, 180000),
    ("triple30", "Home 5 kWp", 5.0, "stated", "9 × 550 W Tier-1", "5 kW hybrid inverter", None, 285000),
    ("triple30", "Premium 10 kWp", 10.0, "stated", "18 × 550 W Tier-1", "10 kW three-phase inverter (battery-ready)", None, 520000),
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def panel_count(panels: str, kwp: float) -> int:
    m = re.match(r"\s*(\d+)", panels)
    return int(m.group(1)) if m else max(1, round(kwp * 1000 / 600))


def svg(p: dict) -> str:
    """A simple drawing of the package: a roof with its panels, the inverter, and the battery if it has one."""
    n = min(panel_count(p["panels"], p["kwp"]), 32)
    rows = 2 if n <= 12 else 3 if n <= 24 else 4
    cols = math.ceil(n / rows)
    cw = min(40.0, 224.0 / cols)
    ch = cw * 0.62
    gw, gh = cols * cw, rows * ch
    x0, y0 = 44 + (232 - gw) / 2, 112 + (92 - gh) / 2
    cells = []
    for i in range(n):
        r, c = divmod(i, cols)
        cells.append(f'<rect x="{x0 + c * cw + 1.5:.1f}" y="{y0 + r * ch + 1.5:.1f}" width="{cw - 3:.1f}" height="{ch - 3:.1f}" rx="2" fill="url(#pv)" stroke="#dbe6f5" stroke-width="1"/>')
    off = p["type"] == "off-grid"
    inv_label = re.search(r"(\d+(?:\.\d+)?)\s*kW", p["inverter"])
    inv_label = f"{inv_label.group(1)} kW" if inv_label else "Inverter"
    battery = ""
    if p.get("battery_kwh"):
        bars = "".join(f'<rect x="344" y="{204 - 17 * k}" width="30" height="11" rx="2" fill="#7bd389"/>' for k in range(min(4, max(1, round(p["battery_kwh"] / 5)))))
        battery = (f'<rect x="334" y="140" width="50" height="86" rx="7" fill="#eef2f0" stroke="#9fb3a8" stroke-width="2"/>{bars}'
                   f'<rect x="352" y="134" width="14" height="7" rx="2" fill="#9fb3a8"/>'
                   f'<text x="359" y="244" text-anchor="middle" font-size="12" font-weight="600" fill="#33443b">{p["battery_kwh"]:g} kWh</text>')
    grid = "" if off else ('<path d="M414 150 L414 70 M402 82 L426 82 M405 94 L423 94" stroke="#8a93a0" stroke-width="3" fill="none"/>'
                           '<path d="M316 132 C 330 92, 392 96, 414 108" stroke="#f0b323" stroke-width="2.5" fill="none" stroke-dasharray="5 4"/>')
    tag = "Sample" if p.get("synthetic") else "Illustration"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 300" width="440" height="300" role="img" aria-label="Drawing of {p['name']}">
<defs>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cfe6ff"/><stop offset="1" stop-color="#fff4dc"/></linearGradient>
<linearGradient id="pv" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2c4f8f"/><stop offset="1" stop-color="#16294f"/></linearGradient>
</defs>
<rect width="440" height="300" fill="url(#sky)"/>
<circle cx="378" cy="48" r="26" fill="#ffd34d"/>
<g stroke="#ffd34d" stroke-width="3" stroke-linecap="round">{''.join(f'<path d="M378 48 L{378 + 38 * math.cos(a):.1f} {48 + 38 * math.sin(a):.1f}" transform="translate(0 0)" stroke-opacity="0.55"/>' for a in [k * math.pi / 4 for k in range(8)])}</g>
<rect x="0" y="262" width="440" height="38" fill="#d9e6cf"/>
<path d="M30 214 L160 96 L290 214 Z" fill="#c9553d" opacity="0"/>
<rect x="40" y="108" width="240" height="100" rx="4" fill="#e9d9c3"/>
<rect x="40" y="108" width="240" height="100" rx="4" fill="none" stroke="#b79d7c" stroke-width="2"/>
<rect x="40" y="208" width="240" height="54" fill="#f6efe4" stroke="#b79d7c" stroke-width="2"/>
<rect x="64" y="226" width="30" height="36" fill="#9bb7d4"/><rect x="226" y="226" width="30" height="36" fill="#9bb7d4"/>
<rect x="150" y="230" width="20" height="32" fill="#8c6a47"/>
{''.join(cells)}
<path d="M280 160 L320 160" stroke="#f0b323" stroke-width="2.5" stroke-dasharray="5 4"/>
<rect x="300" y="132" width="32" height="46" rx="6" fill="#dfe4ea" stroke="#8a93a0" stroke-width="2"/>
<rect x="306" y="139" width="20" height="12" rx="2" fill="#2d3b4d"/><circle cx="312" cy="164" r="2.6" fill="#7bd389"/><circle cx="320" cy="164" r="2.6" fill="#f0b323"/>
<text x="316" y="196" text-anchor="middle" font-size="11" font-weight="600" fill="#3b4656">{inv_label}</text>
{battery}{grid}
<rect x="{426 - (82 if p.get('synthetic') else 92)}" y="266" width="{82 if p.get('synthetic') else 92}" height="24" rx="12" fill="#ffffff" opacity="0.92"/>
<text x="{426 - (82 if p.get('synthetic') else 92) / 2}" y="282" text-anchor="middle" font-size="12" font-weight="700" fill="#b45309">{tag}</text>
<rect x="14" y="266" width="{110 if off else 92}" height="24" rx="12" fill="#16294f"/>
<text x="{14 + (110 if off else 92) / 2}" y="282" text-anchor="middle" font-size="12" font-weight="700" fill="#ffffff">{p['kwp']:g} kWp{' off-grid' if off else ''}</text>
</svg>
"""


def page(url: str) -> tuple[str, str]:
    """(visible text, raw html) of one page."""
    u = urlparse(url)
    if not fetch.allowed_by_robots(f"{u.scheme}://{u.netloc}", u.path or "/"):
        raise SystemExit(f"robots.txt does not allow {url}")
    html = fetch.fetch_html(url)
    return BeautifulSoup(html, "html.parser").get_text(" "), html


def contact_problems(i: dict, html: str) -> list[str]:
    """Every published contact must appear on the installer's own page."""
    c, digits, low, bad = i.get("contact") or {}, re.sub(r"\D", "", html), html.lower(), []
    for ph in [*c.get("phones", []), c.get("viber")]:
        if ph and re.sub(r"\D", "", ph)[-10:] not in digits:
            bad.append(f"{i['name']}: phone {ph} not found on {i['site']}")
    for em in c.get("emails", []):
        if em.lower() not in low:
            bad.append(f"{i['name']}: email {em} not found on {i['site']}")
    for key in ("facebook", "messenger", "whatsapp"):
        if c.get(key) and c[key].lower().replace("&", "&amp;") not in low and c[key].lower() not in low:
            bad.append(f"{i['name']}: {key} link {c[key]} not found on {i['site']}")
    if c.get("office") and c["office"].split(",")[0].lower() not in low:
        bad.append(f"{i['name']}: office {c['office']} not found on {i['site']}")
    return bad


def main() -> int:
    pages = {k: page(v["site"]) for k, v in INSTALLERS.items() if v["site"]}
    texts = {k: v[0] for k, v in pages.items()}
    rows, bad = [], []
    for k, (_text, html) in pages.items():
        bad += contact_problems(INSTALLERS[k], html)
    for inst, name, kwp, basis, panels, inverter, battery, price in P:
        if f"{price:,}" not in texts[inst]:
            bad.append(f"{INSTALLERS[inst]['name']} / {name}: ₱{price:,} not found on {INSTALLERS[inst]['site']}")
        i = INSTALLERS[inst]
        rows.append({"id": f"{inst}-{slug(name)}", "synthetic": False, "installer": i["name"], "installer_site": i["site"], "name": name, "kwp": kwp, "kwp_basis": basis,
                     "panels": panels, "inverter": inverter, "battery_kwh": battery, "type": "hybrid" if battery else "grid-tied",
                     "price_php": price, "price_note": i["price_note"], "area": i["area"], "regions": i["regions"], "link": i["site"], "photo": i["photo"],
                     "contact": i["contact"]})
    i = INSTALLERS["sample"]
    for name, kwp, basis, panels, inverter, battery, price, kind in SAMPLES:
        rows.append({"id": f"sample-{slug(name)}", "synthetic": True, "installer": i["name"], "installer_site": None, "name": name, "kwp": kwp, "kwp_basis": basis,
                     "panels": panels, "inverter": inverter, "battery_kwh": battery, "type": kind, "price_php": price, "price_note": i["price_note"],
                     "area": i["area"], "regions": i["regions"], "link": None, "photo": None, "contact": None})
    for k, i in INSTALLERS.items():
        if i["photo"]:
            r = httpx.get(i["photo"], follow_redirects=True, timeout=30, headers={"User-Agent": "Sol-Hackathon/1.0"})
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                bad.append(f"{i['name']}: photo {i['photo']} did not return an image ({r.status_code})")
    if bad:
        print("\n".join(bad))
        return 1
    ART.mkdir(parents=True, exist_ok=True)
    for old in ART.glob("*.svg"):
        old.unlink()
    for p in rows:
        if not p["photo"]:  # no real photo: draw one
            p["photo"] = f"/packages/{p['id']}.svg"
            (ART / f"{p['id']}.svg").write_text(svg(p), encoding="utf-8")
    data = {"checked_on": date.today().isoformat(),
            "note": "Prices are what each installer publishes on its own website on the date above. They are not quotes. Sol has not vetted these installers. Rows marked synthetic are made-up samples.",
            "packages": rows}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    real = sum(1 for p in rows if not p["synthetic"])
    print(f"wrote {OUT.name}: {real} real packages (every price found on its page) + {len(rows) - real} made-up samples; "
          f"{sum(1 for p in rows if p['photo'].startswith('/packages/'))} drawings in {ART.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
