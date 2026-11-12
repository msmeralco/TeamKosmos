"""Tool registry and per-turn context. Tools are thin, deterministic wrappers over the services.

The LLM never does math: every number it may quote comes from these tool results.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...config import Settings
from ...errors import ApiError
from ...models import PanelSpec, RoofModel
from .. import geo, layout, load as load_svc, optimizer, passport, products, rag, simulate
from ..assumptions import A, all_assumptions
from ..scraper import search as product_search
from . import intake, nlu, summary
from .session import Session

log = logging.getLogger("sol.agent")
Emit = Callable[[dict], None]


def jsonable(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays so results are safe to store and serialise."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


# ---- per-turn context ----------------------------------------------------------------------------------------------
class TurnContext:
    def __init__(self, session: Session, user_text: str, lang: str, attachments: list, emit: Emit, settings: Settings):
        self.session = session
        self.user_text = user_text
        self.lang = lang
        self.attachments = attachments
        self.emit = emit
        self.settings = settings
        self.flags: dict[str, bool] = {"open_map": False}
        self.tool_calls: list[dict] = []  # {"name", "args", "result"} for the whole turn
        self.calls_made = 0  # counted against the per-turn cap (reset when falling back to another provider)
        self.cards: list[dict] = []
        self.trusted = False
        self.cancelled = threading.Event()
        self._step_n = 0
        self._intro_open = False

    # steps -------------------------------------------------------------------------------------------
    def _emit_step(self, step_id: str, label: str, status: str) -> None:
        self.emit({"event": "step", "data": {"id": step_id, "label": label, "status": status}})

    def start_intro(self) -> None:
        self._intro_open = True
        self._emit_step("s0", "Reading your message", "running")

    def finish_intro(self) -> None:
        if self._intro_open:
            self._intro_open = False
            self._emit_step("s0", "Reading your message", "done")

    def note_step(self, label: str) -> None:
        """A one-shot completed step (e.g. 'Switching to quick mode')."""
        self._step_n += 1
        sid = f"s{self._step_n}"
        self._emit_step(sid, label, "running")
        self._emit_step(sid, label, "done")

    # tools -------------------------------------------------------------------------------------------
    def call_tool(self, name: str, args: dict | None = None) -> dict:
        # `self.trusted` is True only while the rule-based agent runs: its values come straight from the user's
        # text or a choice button. Values chosen by an LLM are untrusted and must be traceable to what the user said.
        if self.cancelled.is_set():
            return {"error": "cancelled", "message": "The request was cancelled."}
        tool = TOOLS.get(name)
        if tool is None:
            return {"error": "unknown_tool", "message": f"There is no tool called {name}."}
        if self.calls_made >= self.settings.max_tool_calls:
            return {"error": "tool_call_limit", "message": "Too many tool calls in one turn. Answer with what you have."}
        self.calls_made += 1
        self.finish_intro()
        self._step_n += 1
        sid = f"s{self._step_n}"
        self._emit_step(sid, tool.label, "running")
        try:
            parsed = tool.args_model.model_validate(args or {})
        except ValidationError as exc:
            first = exc.errors()[0]
            result: dict = {"error": "invalid_arguments", "message": f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"}
        else:
            try:
                result = tool.fn(self, parsed)
            except ApiError as exc:
                result = {"error": exc.code, "message": exc.message, "hint": exc.hint}
            except Exception:  # noqa: BLE001 - a tool bug must not break the turn
                log.exception("tool %s failed", name)
                result = {"error": "tool_failed", "message": "That step failed unexpectedly."}
        result = jsonable(result)
        self._emit_step(sid, tool.label, "done")
        self.tool_calls.append({"name": name, "args": args or {}, "result": result})
        return result

    def results_of(self, name: str) -> list[dict]:
        return [c["result"] for c in self.tool_calls if c["name"] == name]


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[TurnContext, Any], dict]
    label: str


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, args_model: type[BaseModel], label: str):
    def deco(fn):
        TOOLS[name] = Tool(name, description, args_model, fn, label)
        return fn
    return deco


# ---- shared helpers -------------------------------------------------------------------------------------------------------
def profile_view(s: Session) -> dict:
    p = s.profile
    return {
        "roof": intake.roof_label(p.roof), "roof_method": p.roof_method, "monthly_kwh": p.monthly_kwh,
        "monthly_bill_php": p.monthly_bill_php, "usage_confirmed": p.load_confirmed,
        "system_type": p.system_type,
        "budget_min_php": p.budget_min_php, "budget_max_php": p.budget_max_php, "goal": p.goal,
        "goal_target_pct": p.goal_target_pct, "backup_hours": p.backup_hours, "net_metering": p.net_metering,
        "summary_confirmed": p.confirmed, "household": s.persona.name,
    }


def snapshot(ctx: TurnContext) -> dict:
    s = ctx.session
    slot = intake.next_slot(s)
    return {"next_slot": slot, "ask": intake.question_for(slot, s, ctx.lang), "profile": profile_view(s)}


def roof_summary(roof: RoofModel | dict) -> dict:
    r = roof if isinstance(roof, dict) else roof.model_dump(mode="json")
    return {k: r[k] for k in ("id", "source", "area_m2", "usable_area_m2", "azimuth_deg", "tilt_deg", "roof_type",
                              "confidence", "notes", "warnings") if k in r}


def _set_roof(ctx: TurnContext, roof: RoofModel, method: str) -> None:
    s = ctx.session
    s.profile.roof = roof.model_dump(mode="json")
    s.profile.roof_method = method  # type: ignore[assignment]
    s.pending.pop("candidates", None)
    s.pending.pop("candidate_texts", None)
    s.pending["roof_announced_id"] = roof.id
    s.invalidate_results()
    ctx.flags["open_map"] = True
    ctx.cards.append({"type": "roof", "data": roof_summary(roof)})


def load_params(s: Session) -> dict:
    p = s.profile
    tmpl = p.household_template or "balanced"
    if p.monthly_kwh is not None:
        return {"monthly_kwh": p.monthly_kwh, "template": tmpl, "basis": "persona" if p.load_source == "persona" else "kwh_input"}
    return {"bill_php": p.monthly_bill_php, "template": tmpl, "basis": "bill"}


# ---- tools ------------------------------------------------------------------------------------------------------------------------
class UpdateProfileArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    monthly_kwh: float | None = Field(None, description="Household usage in kWh per month, as stated by the user.")
    monthly_bill_php: float | None = Field(None, description="Monthly electricity bill in pesos, as stated by the user.")
    confirm_load: bool | None = Field(None, description="True when the user confirms the usage/bill shown.")
    load_source: Literal["user", "bill_photo"] | None = Field(None, description="bill_photo only if read from an attached bill and confirmed.")
    household_template: Literal["night_heavy", "balanced", "day_heavy"] | None = None
    system_type: Literal["on_grid", "off_grid", "hybrid"] | None = Field(
        None, description="Type of solar system the user chose: on_grid (grid-tied, no battery), off_grid (batteries, no utility) or hybrid (grid plus battery).")
    budget_min_php: float | None = Field(None, description="Lower end of the budget in pesos, 0 if the user gave only a maximum.")
    budget_max_php: float | None = Field(None, description="Maximum budget in pesos for the whole installed system.")
    goal: Literal["cut_bill", "max_savings_10y", "fastest_payback", "backup"] | None = None
    goal_target_pct: float | None = Field(None, description="Target bill reduction in percent, only for goal cut_bill.")
    backup_hours: float | None = Field(None, description="Hours of blackout backup wanted, only for goal backup.")
    net_metering: bool | None = None
    confirm_summary: bool | None = Field(None, description="True when the user says to run the numbers after the summary.")


_NUMERIC_FIELDS = ("monthly_kwh", "monthly_bill_php", "budget_min_php", "budget_max_php", "goal_target_pct", "backup_hours")


def _stated_numbers(ctx: TurnContext) -> list[float]:
    """Numbers the user actually wrote in this message or their last two, plus values read from a bill image."""
    from .guard import _numbers_in_text

    texts = [ctx.user_text] + [h["text"] for h in ctx.session.history if h["role"] == "user"][-2:]
    nums: list[float] = []
    for t in texts:
        nums += _numbers_in_text(t)
    bill = ctx.session.pending.get("bill_read") or {}
    nums += [float(v) for v in bill.values() if isinstance(v, (int, float))]
    return nums


def _user_agreed(ctx: TurnContext) -> bool:
    text = ctx.user_text.strip()
    if nlu.is_affirm(text):
        return True
    act = intake.match_choice(ctx.session, text)
    return bool(act and act["kind"] == "update" and (act["payload"].get("confirm_load") or act["payload"].get("confirm_summary")))


def ground_fields(ctx: TurnContext, fields: dict) -> tuple[dict, list[str]]:
    """Drop LLM-supplied values the user never stated, and confirmations the user never gave."""
    if ctx.trusted:
        return fields, []
    stated = _stated_numbers(ctx)
    kept, rejected = dict(fields), []
    for name in _NUMERIC_FIELDS:
        if name in kept:
            v = float(kept[name])
            if not (name == "budget_min_php" and v == 0) and not any(abs(n - v) <= max(1e-6, abs(v) * 0.005) for n in stated):
                rejected.append(f"{name} ({v:g}) was not stated by the user")
                kept.pop(name)
    for name in ("confirm_load", "confirm_summary"):
        if kept.get(name) and not _user_agreed(ctx):
            rejected.append(f"{name} was set but the user has not agreed yet")
            kept.pop(name)
    if kept.get("load_source") == "bill_photo" and not ctx.session.pending.get("bill_read"):
        kept.pop("load_source")
    return kept, rejected


@tool("update_profile", "Record household details the USER STATED (usage, bill, budget, goal) after validation. "
      "Only pass values the user wrote in their latest messages; never guess, and never confirm for them. "
      "The result says what to ask next.", UpdateProfileArgs, "Saving your details")
def _update_profile(ctx: TurnContext, a: UpdateProfileArgs) -> dict:
    fields, rejected = ground_fields(ctx, a.model_dump(exclude_none=True))
    applied, errors = intake.apply_updates(ctx.session, **fields)
    out = {"applied": applied, "errors": errors, **snapshot(ctx)}
    ack = summary.render_tool_result("update_profile", out)
    if ack:
        out["acknowledge"] = ack  # a ready-made, number-safe sentence for the model to open its reply with
    if rejected:
        out["rejected"] = rejected
        out["message"] = "Some values were not saved because the user did not state them. Ask the user instead of assuming."
    return out


class RoofModeArgs(BaseModel):
    mode: Literal["address", "draw", "sketch"] = Field(description="address = look up by address; draw = trace on the satellite map; sketch = blank canvas with a metre scale.")


@tool("request_roof_input", "Switch how the user provides their roof. draw/sketch opens the map panel for the user.",
      RoofModeArgs, "Setting up the roof input")
def _request_roof_input(ctx: TurnContext, a: RoofModeArgs) -> dict:
    applied, errors = intake.apply_updates(ctx.session, roof_method=a.mode)
    if a.mode in ("draw", "sketch"):
        ctx.flags["open_map"] = True
    return {"applied": applied, "errors": errors, **snapshot(ctx)}


class GeocodeArgs(BaseModel):
    query: str = Field(min_length=3, max_length=200, description="The address as the user typed it.")


def _select_candidate(ctx: TurnContext, idx: int | None, lat: float | None = None, lon: float | None = None) -> dict:
    s = ctx.session
    if idx is not None:
        cands = s.pending.get("candidates") or []
        if not 0 <= idx < len(cands):
            return {"error": "invalid_candidate", "message": "That address choice does not exist. Ask the user to pick again.", **snapshot(ctx)}
        lat, lon = float(cands[idx]["lat"]), float(cands[idx]["lon"])
    if lat is None or lon is None:
        return {"error": "missing_location", "message": "Give a candidate_index or a lat and lon.", **snapshot(ctx)}
    s.pending["anchor"] = {"lat": lat, "lon": lon}
    try:
        roof = geo.roof_from_address(lat, lon)
    except ApiError as exc:
        if exc.code in ("no_building", "lookup_unavailable"):
            intake.apply_updates(s, roof_method="draw")
            ctx.flags["open_map"] = True
            return {"found": False, "reason": exc.code, "message": exc.message, "hint": exc.hint, **snapshot(ctx)}
        raise
    _set_roof(ctx, roof, "address")
    return {"found": True, "roof": roof_summary(roof), **snapshot(ctx)}


@tool("geocode_address", "Search an address in the Philippines. Returns candidates; if exactly one, its roof outline is looked up automatically.",
      GeocodeArgs, "Searching the address")
def _geocode(ctx: TurnContext, a: GeocodeArgs) -> dict:
    s = ctx.session
    res = geo.geocode(a.query)
    cands = res["candidates"][:5]
    intake.apply_updates(s, roof_method="address")
    if not cands:
        s.pending.pop("candidates", None)
        s.pending.pop("candidate_texts", None)
        msg = ("The address search is not available right now, so please draw the roof on the map instead."
               if res["degraded"] else "I found no match for that address. Try adding the barangay and city, or draw the roof on the map.")
        return {"candidates": [], "degraded": res["degraded"], "message": msg, **snapshot(ctx)}
    s.pending["candidates"] = cands
    s.pending["candidate_texts"] = {f"Use {str(c['label'])[:120]}": i for i, c in enumerate(cands)}
    listing = [{"index": i, "label": c["label"], "lat": c["lat"], "lon": c["lon"], "source": c["source"]} for i, c in enumerate(cands)]
    if len(cands) == 1:
        out = _select_candidate(ctx, 0)
        return {"candidates": listing, "auto_selected": True, "degraded": res["degraded"], **out}
    # Several matches: show the best one on the map right away so the user sees where the search landed.
    s.pending["anchor"] = {"lat": float(cands[0]["lat"]), "lon": float(cands[0]["lon"])}
    ctx.flags["open_map"] = True
    return {"candidates": listing, "degraded": res["degraded"], **snapshot(ctx)}


class OutlineArgs(BaseModel):
    candidate_index: int | None = Field(None, description="Index of the address candidate the user picked.")
    lat: float | None = None
    lon: float | None = None


@tool("get_building_outline", "Look up the building outline for a chosen address candidate (or lat/lon) and set it as the roof.",
      OutlineArgs, "Finding your roof outline")
def _outline(ctx: TurnContext, a: OutlineArgs) -> dict:
    return _select_candidate(ctx, a.candidate_index, a.lat, a.lon)


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


@tool("run_analysis", "Run the full analysis: household load, equipment search, optimizer and the 25-year simulation. "
      "Only works once the roof, usage, budget and goal are set and the user confirmed the summary.", NoArgs, "Running the numbers")
def _run_analysis(ctx: TurnContext, _a: NoArgs) -> dict:
    s = ctx.session
    slot = intake.next_slot(s)
    if slot != "run":
        return {"error": "not_ready", "message": "The inputs are not complete or not confirmed yet.", **snapshot(ctx)}
    p = s.profile
    s.pending.pop("full_roof", None)
    roof = RoofModel.model_validate(p.roof)
    ld = load_svc.from_profile(p)
    try:
        res = optimizer.optimize(roof, ld, budget_max_php=p.budget_max_php, budget_min_php=p.budget_min_php, goal=p.goal,
                                 goal_target_pct=p.goal_target_pct, backup_hours=p.backup_hours, system_type=p.system_type)
    except ApiError:
        # No design fits: send the user to the "change something" choices instead of looping on 'run'.
        p.confirmed = False
        s.pending["changing"] = True
        raise
    res = jsonable(res)
    s.results["analysis"] = {"optimize": res, "load": ld.to_dict(include_hourly=False), "selected_index": 0}
    summ = summary.summarize_analysis(res, p.net_metering, p.system_type, roof)
    s.results["summary"] = summ
    ctx.cards.append({"type": "analysis", "data": summ})
    return {"summary": summ, **snapshot(ctx)}


def _analysis_item(s: Session, idx: int | None) -> tuple[dict, int]:
    a = s.results.get("analysis")
    if not a:
        raise ApiError("not_ready", "There is no analysis yet. Run the numbers first.")
    pk = a["optimize"]["packages"]
    i = a.get("selected_index", 0) if idx is None else idx
    if not 0 <= i < len(pk):
        raise ApiError("invalid_package", f"Package index must be between 0 and {len(pk) - 1}.")
    return pk[i], i


class CompareArgs(BaseModel):
    package_index: int | None = Field(None, description="Which option (0 is the top one).")
    export_credit_php_per_kwh: float | None = Field(None, ge=0, le=30, description="Optional what-if export credit in pesos per kWh.")


@tool("compare_net_metering", "Compare results with and without net metering for an option, optionally with a different export credit.",
      CompareArgs, "Comparing net metering")
def _compare(ctx: TurnContext, a: CompareArgs) -> dict:
    s = ctx.session
    item, i = _analysis_item(s, a.package_index)
    roi = item["roi"]
    if a.export_credit_php_per_kwh is not None:
        roi = jsonable(simulate.simulate_package(item["package"], RoofModel.model_validate(s.profile.roof),
                                                 load_svc.from_profile(s.profile), export_credit_php_per_kwh=a.export_credit_php_per_kwh))
    vname = "hybrid" if roi.get("hybrid") else "on_grid"

    def pick(variant: dict) -> dict:
        sc = {x["name"]: x for x in variant["scenarios"]}
        return {"payback_years": {"bad_year": sc["pessimistic"]["payback_years"], "expected": sc["expected"]["payback_years"],
                                  "best_case": sc["optimistic"]["payback_years"]},
                "net_profit_25y_php": {"bad_year": sc["pessimistic"]["net_profit_25y_php"], "expected": sc["expected"]["net_profit_25y_php"],
                                       "best_case": sc["optimistic"]["net_profit_25y_php"]},
                "year1_savings_php": sc["expected"]["year1_savings_php"]}

    out = {"package": item["package"]["label"], "package_index": i, "variant": vname,
           "net_metering_on": pick(roi[vname]), "net_metering_off": pick(roi["net_metering_off"][vname]),
           "export_credit_php_per_kwh": roi["export_credit_php_per_kwh"]}
    s.results["net_metering_compare"] = out
    return out


class ExplainArgs(BaseModel):
    topic: str | None = Field(None, description="Optional topic: net metering, battery, tariff, costs, weather, emissions.")


_TOPICS = {
    ("net", "credit", "export", "meter"): ("export_credit", "net_metering", "tariff"),
    ("battery", "backup", "blackout"): ("battery",),
    ("tariff", "rate", "bill", "price", "meralco"): ("tariff",),
    ("cost", "install", "permit", "maintenance", "replace", "capex"): ("install", "permits", "om_pct", "replacement", "life"),
    ("weather", "sun", "solar", "pvgis", "loss", "degrad", "inverter"): ("system_losses", "degradation", "inverter_eff", "dc_ac"),
    ("emission", "co2", "carbon"): ("grid_emission",),
}
FACTS = {
    "net": [
        "Exported power is credited at an approximation of Meralco's monthly blended generation charge, not the full retail rate. The credit is editable.",
        "Credits are banked from month to month and offset energy charges only. Fixed charges are not offset and unused credit is not paid out in cash.",
        "This method is modelled and still needs to be verified against a real Meralco bill.",
    ],
    "weather": [
        "Sunlight data is PVGIS-ERA5, a modelled reanalysis dataset, simulated hour by hour against an estimated household load.",
        "Results are shown for a bad, a typical and a good weather year instead of one confident number.",
    ],
    "general": [
        "All results are estimates for a licensed installer to confirm. Demo data is synthetic.",
    ],
}


@tool("explain_assumptions", "List the assumptions behind the numbers (with units, sources and dates) and approved explanations of net metering "
      "and the weather data. Use only what this returns when explaining.", ExplainArgs, "Gathering the assumptions")
def _explain(ctx: TurnContext, a: ExplainArgs) -> dict:
    topic = (a.topic or "").lower()
    keys: tuple[str, ...] = ()
    facts = list(FACTS["general"])
    for words, ks in _TOPICS.items():
        if any(w in topic for w in words):
            keys += ks
    if any(w in topic for w in ("net", "credit", "export", "meter")):
        facts = FACTS["net"] + facts
    if any(w in topic for w in ("weather", "sun", "pvgis")):
        facts = FACTS["weather"] + facts
    if not keys:
        facts = FACTS["net"] + FACTS["weather"] + facts
    items = [x for x in all_assumptions() if (not keys or any(k in x["key"] for k in keys))]
    return {"assumptions": items[:40], "facts": facts, "count": len(items)}


class DocsArgs(BaseModel):
    query: str = Field(..., min_length=2, max_length=300, description="The question, in plain words.")
    kind: Literal["meralco", "policy", "installer", "general", "product"] | None = Field(
        None, description="Optional: limit to Meralco pages, DOE policy, installer guidance, general solar background or manufacturer pages.")


@tool("search_docs", "Search the local library of Meralco solar pages, DOE rules, installer guidance, general solar background and "
      "manufacturer pages. Returns passages with source links. Use it for rules, fees, permits, process, equipment and how-solar-works "
      "questions, and quote only what it returns. Facts and citations only: never calculate from it.", DocsArgs, "Checking the sources")
def _search_docs(ctx: TurnContext, a: DocsArgs) -> dict:
    hits = rag.search(a.query, k=4, kinds=[a.kind] if a.kind else None)
    if not hits:
        return {"passages": [], "message": "No source in the library covers this. Say you do not have a source and suggest asking Meralco or an installer. Do not guess."}
    return {"passages": hits, "message": "Quote or paraphrase only these passages and name the source. Passages marked region US are general background, not Philippine rules: "
                                         "prefer Meralco and policy sources, and say when something is a US example."}


class PassportArgs(BaseModel):
    package_index: int | None = Field(None, description="Which option to record (0 is the top one).")


@tool("issue_passport", "Create the signed, hashed Solar Passport for an analysed option.", PassportArgs, "Signing your Solar Passport")
def _issue_passport(ctx: TurnContext, a: PassportArgs) -> dict:
    s = ctx.session
    item, i = _analysis_item(s, a.package_index)
    existing = s.results.get("passport")
    if existing and existing.get("package_index") == i:
        # Same analysis, same option: show the record already issued instead of signing a duplicate.
        ctx.cards.append({"type": "passport", "data": existing})
        return {**existing, "already_issued": True}
    p = s.profile
    inputs = {
        "roof": p.roof, "load": {"params": load_params(s), "summary": s.results["analysis"]["load"]},
        "budget_php": [p.budget_min_php or 0.0, p.budget_max_php], "goal": p.goal, "goal_target_pct": p.goal_target_pct,
        "backup_hours": p.backup_hours, "net_metering": p.net_metering, "household": s.persona.name,
    }
    rec = passport.issue(inputs=jsonable(inputs), package=item["package"], results=item["roi"])
    checks = {c["name"]: c["status"] for c in rec["body"]["verification"]["checks"]}
    out = {"id": rec["id"], "short_hash": rec["short_hash"], "verify_path": rec["verify_path"], "hash": rec["hash"],
           "package_index": i, "checks_at_issue": checks, "created_at": rec["created_at"],
           "option": item["package"].get("label") or "Selected option",
           "panels": item["package"]["panel_count"], "kwp": item["package"]["kwp"]}
    s.results["passport"] = out
    ctx.cards.append({"type": "passport", "data": out})
    return out


@tool("toggle_roof_fill", "Switch the map between the chosen design and a preview with panels on the whole roof. "
      "Use when the user wants to see the roof fully covered. The preview is a layout, not a recommendation.", NoArgs, "Laying panels on the roof")
def _toggle_roof_fill(ctx: TurnContext, _a: NoArgs) -> dict:
    s = ctx.session
    item, _i = _analysis_item(s, None)
    pkg = item["package"]
    if s.pending.get("full_roof"):
        s.pending.pop("full_roof")
        ctx.flags["open_map"] = True
        return {"mode": "design", "panels": pkg["panel_count"], "kwp": pkg["kwp"]}
    roof = RoofModel.model_validate(s.profile.roof)
    panel = pkg["panel"]
    n = layout.panel_capacity(roof, *panel["dims_m"])
    if n <= 0:
        return {"error": "no_space", "message": "No more panels fit on this roof."}
    kwp = n * panel["watts"] / 1000.0
    cost = n * panel["price_php"] + A("install_cost_php_per_kw") * kwp + A("permits_misc_php")
    s.pending["full_roof"] = True
    ctx.flags["open_map"] = True
    budget = s.profile.budget_max_php
    return {
        "mode": "full", "panels": n, "kwp": round(kwp, 2), "panel_model": f"{panel['brand']} {panel['model']} ({panel['watts']:g} W)",
        "panel_area_m2": round(n * panel["dims_m"][0] * panel["dims_m"][1], 0), "roof_area_m2": roof.area_m2,
        "rough_cost_php": round(cost, 0), "design_panels": pkg["panel_count"], "design_kwp": pkg["kwp"],
        "design_cost_php": pkg["capex_php"], "budget_max_php": budget,
        "over_budget_php": round(max(0.0, cost - budget), 0) if budget else None,
        "net_metering_cap_kw": A("net_metering_cap_kw"), "above_net_metering_cap": kwp > A("net_metering_cap_kw"),
        "largest_inverter_kw": max((p["inverter_ac_kw"] for p in products.list_products() if p["category"] == "inverter"), default=0),
    }


class ProductArgs(BaseModel):
    categories: list[Literal["panel", "inverter", "battery"]] | None = None


@tool("search_products", "Refresh equipment prices from enabled retailer sources and report what the catalog holds. "
      "Falls back to cached and demo prices and says so.", ProductArgs, "Checking equipment prices")
def _search_products(ctx: TurnContext, a: ProductArgs) -> dict:
    events = list(product_search.search(list(a.categories) if a.categories else None))
    done = events[-1] if events else {}
    failed = [e for e in events if e["event"] == "source_failed"]
    cat = products.list_products()
    fresh: dict[str, int] = {}
    for p in cat:
        fresh[p["freshness"]] = fresh.get(p["freshness"], 0) + 1
    live = done.get("found_live", 0)
    msg = (f"I found {live} live listings. " if live else "No live listings were available, so I'm using cached and demo prices. ")
    return {"found_live": live, "catalog_size": len(cat), "freshness_counts": fresh,
            "source_notes": [f["reason"] for f in failed][:3],
            "message": msg + "Prices are suggestions, so confirm with the seller."}


class BillArgs(BaseModel):
    kwh: float | None = Field(None, description="kWh used, as printed on the attached bill.")
    amount_php: float | None = Field(None, description="Total amount due in pesos, as printed on the attached bill.")
    note: str | None = Field(None, max_length=200)


@tool("record_bill_reading", "Record what you read from an attached bill image. This does NOT change the profile: "
      "ask the user to confirm, then call update_profile.", BillArgs, "Reading your bill")
def _bill(ctx: TurnContext, a: BillArgs) -> dict:
    errors = []
    if a.kwh is not None and not intake.KWH_RANGE[0] <= a.kwh <= intake.KWH_RANGE[1]:
        errors.append("That kWh figure looks implausible for a household")
    if a.amount_php is not None and not intake.BILL_RANGE[0] <= a.amount_php <= intake.BILL_RANGE[1]:
        errors.append("That amount looks implausible for a household bill")
    if a.kwh is None and a.amount_php is None:
        errors.append("Nothing was read from the bill")
    if errors:
        return {"recorded": False, "errors": errors, "message": "; ".join(errors) + ". Ask the user to type the figures instead."}
    ctx.session.pending["bill_read"] = {"kwh": a.kwh, "amount_php": a.amount_php}
    return {"recorded": True, "kwh": a.kwh, "amount_php": a.amount_php,
            "message": "Tell the user what you read and ask them to confirm before it is used."}


def layout_for_selected(s: Session) -> dict | None:
    """Panel rectangles for the selected option, for the map panel."""
    a = s.results.get("analysis")
    if not a or not s.profile.roof:
        return None
    item = a["optimize"]["packages"][a.get("selected_index", 0)]
    panel = item["package"]["panel"]
    roof = RoofModel.model_validate(s.profile.roof)
    res = layout.pack_panels(roof, PanelSpec(length_m=panel["dims_m"][0], width_m=panel["dims_m"][1]))
    n = len(res["panels_lonlat"]) if s.pending.get("full_roof") else item["package"]["panel_count"]
    res["full_roof"] = bool(s.pending.get("full_roof"))
    # Positions the roof could still hold are returned too, so the map can show the unused room.
    res["spots_lonlat"] = res["panels_lonlat"][n:]
    res["panels_m"], res["panels_lonlat"] = res["panels_m"][:n], res["panels_lonlat"][:n]
    res["count"] = len(res["panels_m"])
    res["capacity"] = res["count"] + len(res["spots_lonlat"])
    return jsonable(res)
