"""Export of one chosen package as a PDF: installation area, budget, package and the numbers.

Everything comes from the saved profile and the stored analysis summary (tool results), never from model text.
plan_data() gathers the content; plan_pdf() lays it out on A4.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import BACKEND_DIR
from ..errors import ApiError
from ..models import PanelSpec, RoofModel
from . import layout, market_packages
from .agent.intake import goal_label, php
from .agent.session import Session
from .agent.summary import SYSTEM_NAMES, _pb, _range

log = logging.getLogger("sol.export")

MASCOT = Path(BACKEND_DIR).parent / "frontend" / "public" / "favicon.png"  # the yellow sun mascot
DRIVERS = {"export_credit_php_per_kwh": "the net-metering export credit", "install_cost_php_per_kw": "the installation cost per kW",
           "tariff_fixed_php_month": "fixed monthly charges (not modelled)"}
SOURCES = {"osm": "OpenStreetMap building outline", "drawn": "Drawn on the satellite map", "sketch": "Sketch on the canvas", "photo": "Photo"}

# The app's palette: warm monochrome with one orange accent.
INK, GREY, HAIR = colors.HexColor("#111111"), colors.HexColor("#787774"), colors.HexColor("#e5e5e3")
PAPER, ACCENT, GREEN, AMBER = colors.HexColor("#fafaf9"), colors.HexColor("#ea580c"), colors.HexColor("#346538"), colors.HexColor("#b45309")
PANEL = colors.HexColor("#2b4a63")


# ---- content ------------------------------------------------------------------------------------------------------------
def plan_data(s: Session, idx: int | None = None) -> dict:
    """The content of the plan for one option. idx is the option's position on the Overview page."""
    summ = s.results.get("summary")
    if not summ or "net_profit_10y_php" not in (summ["packages"][0] if summ.get("packages") else {}):
        raise ApiError("not_ready", "There is no analysis to export yet.", hint="Run the numbers in the chat first.", status=409)
    pk = summ["packages"]
    i = (s.results.get("analysis") or {}).get("selected_index", 0) if idx is None else idx
    if not 0 <= i < len(pk):
        raise ApiError("invalid_package", f"Package index must be between 0 and {len(pk) - 1}.", status=422)
    p, prof, roof = pk[i], s.profile, s.profile.roof or {}
    pf, pb = p["net_profit_10y_php"], p["payback_years"]

    area = [("How it was found", SOURCES.get(roof.get("source", ""), "n/a")),
            ("Roof area", f"{roof.get('area_m2', 0):g} m²"), ("Usable for panels", f"{roof.get('usable_area_m2', 0):g} m²"),
            ("Roof type", str(roof.get("roof_type", "n/a")).replace("_", " ")),
            ("Tilt and facing", f"{roof.get('tilt_deg', 0):g}° tilt, facing {roof.get('azimuth_deg', 0):g}° (180° is south)"),
            ("Edge setback", f"{roof.get('setback_m', 0):g} m"), ("Outline confidence", str(roof.get("confidence", "n/a")))]
    if roof.get("centroid"):
        area.append(("Location", f"{roof['centroid']['lat']:.5f}, {roof['centroid']['lon']:.5f}"))
    if p.get("roof_capacity_panels"):
        area.append(("Panel spots on the site", f"{p['roof_capacity_panels']}"))

    kwh = f"{prof.monthly_kwh:g} kWh a month" if prof.monthly_kwh else (f"about {php(prof.monthly_bill_php)} a month" if prof.monthly_bill_php else "n/a")
    budget = (f"{php(prof.budget_min_php)} to {php(prof.budget_max_php)}" if prof.budget_min_php else f"up to {php(prof.budget_max_php)}") if prof.budget_max_php else "n/a"
    inputs = [("Electricity use", kwh), ("Budget", budget), ("System type", SYSTEM_NAMES.get(prof.system_type or "", "n/a")),
              ("Goal", goal_label(prof) or "n/a"), ("Net metering", "on" if prof.net_metering else "off")]

    chosen = [("Solar panels", f"{p['panel_count']} × {p['panel']} = {p['kwp']:g} kWp"), ("Inverter", p["inverter"]),
              ("Battery", (f"{p['battery']} ({p['battery_kwh']:g} kWh)" if p.get("battery_kwh") else p["battery"]) if p.get("battery") else "none"),
              ("Installed cost", php(p["capex_php"]))]

    numbers = [("Bill today", f"about {php(p['grid_only_monthly_bill_php'])} a month"), ("Bill cut, year 1", f"about {p['bill_reduction_pct_year1']:g}%"),
               ("Savings, year 1", php(p["year1_savings_php"])),
               ("Payback", f"{_pb(pb['expected'])} (best case {_pb(pb['best_case'])}, bad weather year {_pb(pb['bad_year'])})"),
               ("10-year net profit", f"{php(pf['expected'])} (range {_range(pf['bad_year'], pf['best_case'], php)})"),
               ("Solar generation, year 1", f"{round(p['year1_generation_kwh']):,} kWh"),
               ("Cost per kWh (LCOE)", f"{p['lcoe_php_per_kwh']} ₱/kWh" if p.get("lcoe_php_per_kwh") is not None else "n/a"),
               ("CO₂ avoided, 10 years", f"{p['co2_avoided_t_10y']:g} t")]

    stats = [("Installed cost", php(p["capex_php"]), f"{p['panel_count']} panels · {p['kwp']:g} kWp"),
             ("Payback", _pb(pb["expected"]), f"best {_pb(pb['best_case'])} · bad year {_pb(pb['bad_year'])}"),
             ("10-year net profit", php(pf["expected"]), f"range {_range(pf['bad_year'], pf['best_case'], php)}"),
             ("Bill cut, year 1", f"{p['bill_reduction_pct_year1']:g}%", f"from about {php(p['grid_only_monthly_bill_php'])} a month")]

    pick = market_packages.get(s.results.get("picked_package", ""))
    picked = None
    if pick:
        who = "Made-up sample, not a real offer" if pick.get("synthetic") else pick["installer"]
        rows = [("Package", pick["name"]), ("From", who), ("Size and type", f"{pick['kwp']:g} kWp, {pick['type']}"),
                ("Published price", f"{php(pick['price_php'])} ({pick.get('price_note') or 'not a quote'})")]
        if prof.budget_max_php:
            gap = pick["price_php"] - prof.budget_max_php
            rows.append(("Against your budget", "within your budget" if gap <= 0 else f"{php(gap)} over your budget"))
        if pick.get("link") and not pick.get("synthetic"):
            rows.append(("Link", pick["link"]))
        picked = {"rows": rows, "note": "This is a price the installer published, not a quote. Ask for a written quote for your own site."}

    extra = []
    if summ.get("unverified_drivers"):
        extra.append("Unverified placeholders behind these results: " + ", ".join(DRIVERS.get(k, k) for k in summ["unverified_drivers"]) + ".")
    return {
        "name": (s.household or {}).get("name") or "Household", "date": time.strftime("%d %B %Y"), "index": i, "package": p, "caveat": summ["caveat"],
        "title": f"{p['label']}: {p['panel_count']} panels, {p['kwp']:g} kWp, {'hybrid' if p.get('battery') else 'grid-tied'}",
        "stats": stats, "area": area, "area_notes": (roof.get("notes") or []) + (roof.get("warnings") or []), "inputs": inputs, "chosen": chosen,
        "numbers": numbers, "weather": f"Weather data: {summ.get('weather_source') or 'n/a'}. Export credit assumed at about ₱{summ['export_credit_php_per_kwh']:g} per kWh.",
        "extra": extra, "picked": picked, "checks": p.get("readiness") or [],
        "passport": ((s.results["passport"]["id"], s.results["passport"]["verify_path"]) if s.results.get("passport") else None),
    }


# ---- layout -------------------------------------------------------------------------------------------------------------
def _t(text) -> str:
    """The built-in PDF fonts have no peso sign or subscript two, so spell them out. Anything else outside Latin-1 becomes '?'."""
    out = str(text).replace("₱/", "PHP/").replace("₱", "PHP ").replace("₂", "2").replace("→", "to")
    return out.encode("cp1252", "replace").decode("cp1252")


def _p(text, style) -> Paragraph:
    return Paragraph(escape(_t(text)), style)


S = {
    "title": ParagraphStyle("title", fontName="Times-Bold", fontSize=26, leading=30, textColor=INK, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10.5, leading=14, textColor=GREY, spaceAfter=10),
    "h": ParagraphStyle("h", fontName="Times-Bold", fontSize=14, leading=18, textColor=INK, spaceBefore=10, spaceAfter=2),
    "k": ParagraphStyle("k", fontName="Helvetica", fontSize=8.5, leading=11, textColor=GREY),
    "v": ParagraphStyle("v", fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=GREY, spaceBefore=4),
    "stat_k": ParagraphStyle("stat_k", fontName="Helvetica", fontSize=7.5, leading=10, textColor=GREY),
    "stat_v": ParagraphStyle("stat_v", fontName="Times-Bold", fontSize=15, leading=18, textColor=INK),
    "stat_s": ParagraphStyle("stat_s", fontName="Helvetica", fontSize=7.5, leading=10, textColor=GREY),
    "chk_t": ParagraphStyle("chk_t", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5, textColor=INK),
    "chk_b": ParagraphStyle("chk_b", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK),
}
STATUS = {"ok": ("OK", GREEN), "watch": ("WATCH", AMBER), "confirm": ("CONFIRM", GREY)}


def _heading(text: str) -> list:
    return [_p(text, S["h"]), HRFlowable(width=14 * mm, thickness=2, color=ACCENT, spaceAfter=6, hAlign="LEFT")]


def _kv(rows: list[tuple[str, str]], width: float) -> Table:
    t = Table([[_p(k, S["k"]), _p(v, S["v"])] for k, v in rows], colWidths=[34 * mm, width - 34 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIR),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _stat_strip(stats: list[tuple[str, str, str]], width: float) -> Table:
    cells = [[_p(k.upper(), S["stat_k"]), _p(v, S["stat_v"]), _p(sub, S["stat_s"])] for k, v, sub in stats]
    t = Table([cells], colWidths=[width / len(stats)] * len(stats))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.6, HAIR), ("LINEBEFORE", (1, 0), (-1, -1), 0.6, HAIR),
                           ("LINEABOVE", (0, 0), (-1, 0), 2, ACCENT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _site_drawing(roof: dict, panels_m: list, shown: int, spots: int | None, w: float, h: float) -> Drawing:
    """To-scale plan of the site: outline, usable area (dashed) and the panels of this option. North is up."""
    d = Drawing(w, h)
    d.add(Rect(0, 0, w, h, fillColor=PAPER, strokeColor=HAIR, strokeWidth=0.6))
    ring = roof["polygon_m"]
    xs, ys = [x for x, _ in ring], [y for _, y in ring]
    pad, foot = 10.0, 20.0
    scale = min((w - 2 * pad) / max(max(xs) - min(xs), 0.1), (h - pad - foot) / max(max(ys) - min(ys), 0.1))
    ox = pad + ((w - 2 * pad) - (max(xs) - min(xs)) * scale) / 2
    oy = foot + ((h - pad - foot) - (max(ys) - min(ys)) * scale) / 2

    def flat(pts):
        return [c for x, y in pts for c in (ox + (x - min(xs)) * scale, oy + (y - min(ys)) * scale)]

    d.add(Polygon(flat(ring), fillColor=colors.HexColor("#efeeea"), strokeColor=colors.HexColor("#52514e"), strokeWidth=1))
    if roof.get("usable_polygon_m"):
        d.add(Polygon(flat(roof["usable_polygon_m"]), fillColor=None, strokeColor=ACCENT, strokeWidth=0.8, strokeDashArray=[3, 2]))
    for pm in panels_m[:shown]:
        d.add(Polygon(flat(pm), fillColor=PANEL, strokeColor=colors.white, strokeWidth=0.3))
    bar = min(5 * scale, w - 2 * pad)  # a 5 m scale bar
    d.add(Line(pad, 10, pad + bar, 10, strokeColor=INK, strokeWidth=1.2))
    d.add(String(pad, 14, "5 m", fontName="Helvetica", fontSize=7, fillColor=GREY))
    d.add(String(pad + bar + 6, 7, f"{shown} panels" + (f" of {spots} spots" if spots else ""), fontName="Helvetica", fontSize=7, fillColor=GREY))
    d.add(Line(w - pad, h - pad - 10, w - pad, h - pad, strokeColor=INK, strokeWidth=1))  # north arrow
    d.add(Polygon([w - pad - 3, h - pad - 3, w - pad, h - pad + 2, w - pad + 3, h - pad - 3], fillColor=INK, strokeColor=INK))
    d.add(String(w - pad - 2.5, h - pad - 20, "N", fontName="Helvetica-Bold", fontSize=7, fillColor=INK))
    return d


class _Numbered(pdfcanvas.Canvas):
    """Draws the running header and 'Page X of Y' on every page once the total is known."""

    def __init__(self, *a, name: str = "", **kw):
        super().__init__(*a, **kw)
        self._saved, self._name = [], name

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self._chrome(total)
            super().showPage()
        super().save()

    def _chrome(self, total: int):
        w, h = A4
        self.saveState()
        x = 18 * mm
        if MASCOT.exists():
            self.drawImage(str(MASCOT), x, h - 21.5 * mm, width=11 * mm, height=11 * mm, mask="auto", preserveAspectRatio=True)
            x += 13 * mm
        self.setFont("Times-Bold", 20)
        self.setFillColor(INK)
        self.drawString(x, h - 18 * mm, "Sol")
        self.setFillColor(GREY)
        self.setFont("Helvetica", 8)
        self.setFillColor(GREY)
        self.drawRightString(w - 18 * mm, h - 14 * mm, "SOLAR PLAN")
        self.drawRightString(w - 18 * mm, h - 18 * mm, _t(self._name))
        self.setStrokeColor(HAIR)
        self.setLineWidth(0.6)
        self.line(18 * mm, h - 23 * mm, w - 18 * mm, h - 23 * mm)
        self.line(18 * mm, 15 * mm, w - 18 * mm, 15 * mm)
        self.drawString(18 * mm, 10.5 * mm, "Sol, your clean energy partner. Estimates for a licensed installer to confirm.")
        self.drawRightString(w - 18 * mm, 10.5 * mm, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def plan_pdf(s: Session, idx: int | None = None, *, compress: bool = True) -> tuple[str, bytes]:
    """Returns (file name, PDF bytes)."""
    d = plan_data(s, idx)
    width = A4[0] - 36 * mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=29 * mm, bottomMargin=21 * mm,
                            title=_t(f"Solar plan for {d['name']}"), author="Sol", subject="Solar plan", pageCompression=int(compress))
    out: list = [_p(f"Solar plan for {d['name']}", S["title"]), _p(f"{d['title']} · prepared {d['date']}", S["sub"]), _stat_strip(d["stats"], width)]

    # Installation area: facts on the left, the site drawn to scale on the right
    left_w, right_w = width * 0.56, width * 0.44 - 6 * mm
    site = None
    roof = s.profile.roof
    try:
        pkg = s.results["analysis"]["optimize"]["packages"][d["index"]]["package"]
        spec = PanelSpec(length_m=pkg["panel"]["dims_m"][0], width_m=pkg["panel"]["dims_m"][1])
        panels = layout.pack_panels(RoofModel.model_validate(roof), spec)["panels_m"]
        site = _site_drawing(roof, panels, d["package"]["panel_count"], d["package"].get("roof_capacity_panels"), right_w, 62 * mm)
    except (KeyError, IndexError, TypeError, ValueError):  # an older saved analysis may lack the panel size; the plan stays valid without the drawing
        log.warning("site drawing skipped", exc_info=True)
    facts = [_kv(d["area"], left_w)] + [_p("• " + n, S["small"]) for n in d["area_notes"]]
    area = Table([[facts, site or ""]], colWidths=[left_w, width - left_w])
    area.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm)]))
    out += [KeepTogether(_heading("Installation area") + [area])]

    half = (width - 8 * mm) / 2
    pair = Table([[_heading("Your inputs") + [_kv(d["inputs"], half)], _heading("Chosen package") + [_kv(d["chosen"], half)]]], colWidths=[half + 8 * mm, half])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 8 * mm), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    out += [pair]
    out += [KeepTogether(_heading("The numbers, over 10 years") + [_kv(d["numbers"], width), _p(d["weather"], S["small"])] + [_p(x, S["small"]) for x in d["extra"]])]
    if d["picked"]:
        out += [KeepTogether(_heading("Ready-made package you picked") + [_kv(d["picked"]["rows"], width), _p(d["picked"]["note"], S["small"])])]

    if d["checks"]:
        rows = []
        for c in d["checks"]:
            label, col = STATUS.get(c["status"], (c["status"].upper(), GREY))
            tag = Paragraph(f'<font color="{col.hexval().replace("0x", "#")}"><b>{label}</b></font>', ParagraphStyle("tag", parent=S["chk_b"], fontSize=7.5))
            rows.append([tag, [_p(c["title"], S["chk_t"]), _p(c["text"], S["chk_b"])]])
        t = Table(rows, colWidths=[18 * mm, width - 18 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIR), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        out += _heading("Before you invest") + [t]

    sun = Image(str(MASCOT), width=11 * mm, height=11 * mm) if MASCOT.exists() else ""
    note = Table([[sun, _p(d["caveat"], S["small"])]], colWidths=[17 * mm, width - 17 * mm])
    note.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.6, HAIR), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    out += [Spacer(1, 12), KeepTogether([note] + ([_p(f"Solar Passport {d['passport'][0]}: verify at {d['passport'][1]}", S["small"])] if d["passport"] else []))]

    doc.build(out, canvasmaker=lambda *a, **kw: _Numbered(*a, name=d["name"], **kw))
    return f"sol-plan-{d['package']['label'].lower().replace(' ', '-')}.pdf", buf.getvalue()
