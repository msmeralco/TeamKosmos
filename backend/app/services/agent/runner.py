"""Run one agent turn: locking, provider choice and fallback, number guard, reply assembly, SSE/JSON output."""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator

from ...config import Settings, get_settings
from ...errors import ApiError
from ...models import FinalizeRequest, FromAddressRequest, LatLon, RoofModel, SketchRequest
from .. import geo, installers as installers_svc, market_packages, roof as roof_svc
from . import followups, guard, intake, reply_format, summary as summary_svc
from .providers import Provider, ProviderUnavailable, ScriptedProvider, question_text, tool_sentences
from .session import Session, load_session, save_session
from .tools import TurnContext, budget_packages_card, jsonable, layout_for_selected, market_region as tools_market_region, profile_view, roof_summary

log = logging.getLogger("sol.agent")
PLACEHOLDER_TEXT = "attached files"  # what the UI sends for a files-only message
MAX_CHOICES = 5
_DONE = object()


@dataclass
class ChatRequest:
    conversation_id: str
    message: str
    user: dict = field(default_factory=dict)  # the signed-in account row
    language: str = "auto"
    files: list = field(default_factory=list)  # list[Attachment]


def make_title(text: str, n_files: int) -> str:
    t = " ".join(text.split())
    if not t:
        return "Attached files" if n_files != 1 else "Attached file"
    return t if len(t) <= 40 else t[:39].rstrip() + "…"


# ---- per-session lock (one turn at a time) -----------------------------------------------------------------------
class SessionLocks:
    def __init__(self):
        self._guard = threading.Lock()
        self._held: dict[str, tuple[str, float]] = {}

    def acquire(self, sid: str, max_age_s: float) -> str | None:
        with self._guard:
            held = self._held.get(sid)
            if held and time.monotonic() - held[1] < max_age_s:
                return None
            token = uuid.uuid4().hex
            self._held[sid] = (token, time.monotonic())
            return token

    def release(self, sid: str, token: str) -> None:
        with self._guard:
            if self._held.get(sid, ("", 0))[0] == token:
                self._held.pop(sid, None)

    def clear(self) -> None:
        with self._guard:
            self._held.clear()


LOCKS = SessionLocks()


class RateLimiter:
    """Sliding-window limiter so an anonymous client cannot drain the Gemini quota."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, list[float]] = {}
        self._guard = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._guard:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window_s]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def reset(self) -> None:
        with self._guard:
            self._hits.clear()


PER_CONVERSATION = RateLimiter(limit=20, window_s=60.0)
GLOBAL = RateLimiter(limit=120, window_s=60.0)


def _check_rate(conversation_id: str) -> None:
    if not PER_CONVERSATION.allow(conversation_id) or not GLOBAL.allow("*"):
        raise ApiError("rate_limited", "Too many messages too quickly.", hint="Wait a few seconds and try again.", status=429)


def _busy() -> ApiError:
    return ApiError("turn_in_progress", "Sol is still working on your last message.", hint="Wait a moment and try again.", status=409)


# ---- provider selection ----------------------------------------------------------------------------------------
_provider_override: Provider | None = None  # tests inject a FakeProvider


def set_provider_override(p: Provider | None) -> None:
    global _provider_override
    _provider_override = p


def choose_provider(settings: Settings) -> Provider:
    if _provider_override is not None:
        return _provider_override
    if settings.llm_configured:
        from .gemini_provider import GeminiProvider

        return GeminiProvider(settings)
    return ScriptedProvider()


# ---- guard -------------------------------------------------------------------------------------------------------
def allowed_numbers(ctx: TurnContext) -> guard.Allowed:
    s = ctx.session
    sources = [
        [c["result"] for c in ctx.tool_calls], ctx.user_text, profile_view(s), s.persona.monthly_kwh,
        s.results.get("summary"), s.results.get("net_metering_compare"), s.results.get("passport"),
        s.pending.get("bill_read"), [h["text"] for h in s.history if h["role"] == "user"][-6:],
    ]
    return guard.Allowed(sources)


def safe_text(ctx: TurnContext) -> str:
    """Template reply built only from tool results and the next question."""
    parts = tool_sentences(ctx)
    parts.append(question_text(ctx))
    return "\n\n".join(p for p in parts if p)


# ---- the turn ------------------------------------------------------------------------------------------------------
def _build_reply(ctx: TurnContext, text: str) -> dict:
    s = ctx.session
    slot = intake.next_slot(s)
    return {
        "text": text,
        "hasMapArtifact": bool(ctx.flags["open_map"] or slot == "roof_draw"),
        "next": followups.suggestions(ctx, intake.choices_for(slot, s), MAX_CHOICES),
        "cards": jsonable(ctx.cards),
        "slot": slot,
    }


def _worker(req: ChatRequest, settings: Settings, out: "queue.Queue", ctx_box: list, lock_token: str) -> None:
    sid = req.conversation_id
    ctx: TurnContext | None = None
    try:
        session = load_session(sid, req.user, req.language)
        lang = intake.pick_language(session, req.message)
        files_only = req.message.strip().lower() == PLACEHOLDER_TEXT and bool(req.files)
        user_text = "" if files_only else req.message
        ctx = TurnContext(session, user_text, lang, req.files, out.put, settings)
        ctx_box.append(ctx)
        out.put({"event": "turn", "data": {"conversationId": sid, "persona": session.persona_id, "language": lang}})
        ctx.start_intro()

        text = ""
        used_scripted = False  # scripted text is built from templates, so the number guard is not needed
        try:
            provider = choose_provider(settings)
            used_scripted = isinstance(provider, ScriptedProvider)
            try:
                text = provider.run_turn(ctx)
            except ProviderUnavailable as exc:
                log.warning("LLM unavailable (%s); using the scripted agent for this turn", exc)
                ctx.note_step("Switching to quick mode")
                ctx.calls_made = 0
                used_scripted = True
                text = ScriptedProvider().run_turn(ctx)
        except Exception:  # noqa: BLE001 - always answer
            log.exception("agent turn failed")
            text = ""

        if ctx.cancelled.is_set():
            return
        ctx.finish_intro()
        if not text.strip():
            text = safe_text(ctx) or "Sorry, something went wrong on my side. Please try again."
        elif not used_scripted:
            bad = guard.check_text(text, allowed_numbers(ctx))
            if bad:
                log.warning("number guard replaced a reply; untraced numbers: %s", bad)
                session.guard_events.append({"at": time.time(), "untraced": bad[:10], "original": text[:400]})
                del session.guard_events[:-20]
                text = safe_text(ctx)
            elif guard.off_slot_question(text, intake.next_slot(session)):
                # The model skipped ahead (for example it says the sketch is ready, but Sol has not received one), so its
                # question would not match the suggestion pills. Ask the question for the step Sol is really on.
                slot_now = intake.next_slot(session)
                log.warning("off-script reply replaced; slot=%s", slot_now)
                session.guard_events.append({"at": time.time(), "untraced": [], "off_slot": slot_now, "original": text[:400]})
                del session.guard_events[:-20]
                lead = "I don't see your installation site outline yet." if slot_now == "roof_draw" else ""
                text = "\n\n".join(p for p in (lead, safe_text(ctx)) if p)

        text = reply_format.tidy(text)  # one layout for every agent: lead, bullets, source note, bold closing question

        # The results table is built from tool results only (so it is exempt from the number guard) and goes above
        # the model's explanation. History keeps just the explanation, to keep the next prompt short.
        blocks: list[str] = []
        for res in ctx.results_of("run_analysis"):
            if isinstance(res, dict) and res.get("summary"):
                blocks.append(summary_svc.analysis_markdown(res["summary"]))
                top = res["summary"]["packages"][0]
                kind = "off-grid" if res["summary"].get("system_type") == "off_grid" else "hybrid" if top.get("battery") else "grid-tied"
                # A card the panel can show; "open": False means it only appears as a link in the chat until the user asks.
                ctx.cards.append({"type": "packages", "data": {**market_packages.panel(top["kwp"], kind, tools_market_region(session), session.profile.budget_min_php,
                                                                                         session.profile.budget_max_php), "open": False}})
        for res in ctx.results_of("issue_passport")[-1:]:
            if isinstance(res, dict) and res.get("id"):
                blocks.append(summary_svc.passport_markdown(res))
        for res in ctx.results_of("package_details")[-1:]:
            if isinstance(res, dict) and res.get("markdown"):
                blocks.append(res["markdown"])
        for res in ctx.results_of("solar_brief")[-1:]:
            if isinstance(res, dict) and res.get("markdown"):
                blocks.append(res["markdown"])
        for res in ctx.results_of("toggle_roof_fill")[-1:]:
            if isinstance(res, dict) and res.get("mode") == "full":
                blocks.append(summary_svc.roof_fill_markdown(res))
        shown = "\n\n".join([*blocks, text])

        offered = budget_packages_card(ctx)  # the budget just landed: show what fits it, in the side panel
        if offered:
            ctx.cards.append(offered)
        reply = _build_reply(ctx, shown)
        session.add_history("user", user_text or f"[attached {len(req.files)} file(s)]")
        session.add_history("model", text)
        session.turn_count += 1
        if not session.title:
            session.title = make_title(user_text, len(req.files))
        session.language = req.language if req.language in ("auto", "english", "taglish") else session.language
        save_session(session)
        out.put({"event": "reply", "data": reply})
        out.put({"event": "done", "data": {}})
    except Exception:  # noqa: BLE001
        log.exception("agent worker crashed")
        out.put({"event": "reply", "data": {"text": "Sorry, something went wrong on my side. Please try again.",
                                           "hasMapArtifact": False, "next": [], "cards": [], "slot": None}})
        out.put({"event": "done", "data": {}})
    finally:
        LOCKS.release(sid, lock_token)
        out.put(_DONE)


def stream_events(req: ChatRequest, settings: Settings | None = None) -> Iterator[dict]:
    """Start the turn now (raising 409 if one is running) and return an iterator of {'event', 'data'} dicts.

    'keepalive' events are emitted while waiting. The stream always ends with reply + done.
    """
    settings = settings or get_settings()
    token = LOCKS.acquire(req.conversation_id, settings.turn_timeout_s * 2)
    if token is None:
        raise _busy()
    try:
        _check_rate(req.conversation_id)
    except ApiError:
        LOCKS.release(req.conversation_id, token)
        raise
    out: queue.Queue = queue.Queue()
    ctx_box: list = []
    threading.Thread(target=_worker, args=(req, settings, out, ctx_box, token), daemon=True).start()
    return _drain(out, ctx_box, settings)


def _drain(out: "queue.Queue", ctx_box: list, settings: Settings) -> Iterator[dict]:
    deadline = time.monotonic() + settings.turn_timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if ctx_box:
                ctx_box[0].cancelled.set()
            yield {"event": "reply", "data": {"text": "That is taking too long. Please try again in a moment.",
                                              "hasMapArtifact": False, "next": [], "cards": [], "slot": None}}
            yield {"event": "done", "data": {}}
            return
        try:
            ev = out.get(timeout=min(10.0, remaining))
        except queue.Empty:
            yield {"event": "keepalive", "data": {}}
            continue
        if ev is _DONE:
            return
        yield ev


def run_turn_json(req: ChatRequest, settings: Settings | None = None) -> dict:
    """Non-streaming mode: the same payload shape as the frontend's AgentMsg once finished."""
    steps: dict[str, dict] = {}
    reply: dict | None = None
    conv = {}
    for ev in stream_events(req, settings):
        if ev["event"] == "step":
            steps[ev["data"]["id"]] = ev["data"]
        elif ev["event"] == "reply":
            reply = ev["data"]
        elif ev["event"] == "turn":
            conv = ev["data"]
    for st in steps.values():
        st["status"] = "done"
    return {"conversationId": req.conversation_id, "phase": "done", "steps": list(steps.values()), "reply": reply, **{k: v for k, v in conv.items() if k != "conversationId"}}


# ---- roof hand-off from the map panel ---------------------------------------------------------------------------------------
def submit_roof(session_id: str, submission, user: dict) -> dict:
    settings = get_settings()
    token = LOCKS.acquire(session_id, settings.turn_timeout_s * 2)
    if token is None:
        raise _busy()
    try:
        s = load_session(session_id, user, None)
        mode = submission.mode
        if mode == "drawn":
            roof = roof_svc.finalize(FinalizeRequest(**submission.model_dump(exclude={"mode"})))
            method = "draw"
        elif mode == "sketch":
            data = submission.model_dump(exclude={"mode"})
            if data.get("anchor") is None:
                a = s.pending.get("anchor")
                data["anchor"] = a if a else {"lat": s.persona.lat, "lon": s.persona.lon}
            roof = roof_svc.sketch_to_roof(SketchRequest(**data))
            method = "sketch"
        else:
            roof = geo.roof_from_address(submission.lat, submission.lon)
            s.pending["anchor"] = {"lat": submission.lat, "lon": submission.lon}
            method = "address"
        s.profile.roof = roof.model_dump(mode="json")
        s.profile.roof_method = method  # type: ignore[assignment]
        s.pending.pop("candidates", None)
        s.pending.pop("candidate_texts", None)
        s.pending.pop("roof_announced_id", None)  # so the next chat turn acknowledges it
        s.invalidate_results()
        save_session(s)
        return {"roof": roof.model_dump(mode="json"), "nextSlot": intake.next_slot(s)}
    finally:
        LOCKS.release(session_id, token)


def session_roof_payload(s: Session) -> dict:
    anchor = s.pending.get("anchor")
    if s.profile.roof:
        c = s.profile.roof["centroid"]
        center = {"lat": c["lat"], "lon": c["lon"], "zoom": 20}
    elif anchor:
        center = {"lat": anchor["lat"], "lon": anchor["lon"], "zoom": 19}
    else:
        center = {"lat": s.persona.lat, "lon": s.persona.lon, "zoom": 17}
    return {
        "center": center, "pin": anchor and {"lat": anchor["lat"], "lon": anchor["lon"]},
        "persona": {"id": s.persona_id, "city": s.persona.city},
        "roof": s.profile.roof, "roofMethod": s.profile.roof_method, "nextSlot": intake.next_slot(s),
        "needsRoof": s.profile.roof is None, "layout": layout_for_selected(s) if s.profile.roof else None,
        "roofSummary": roof_summary(s.profile.roof) if s.profile.roof else None,
    }


__all__ = ["ChatRequest", "stream_events", "run_turn_json", "submit_roof", "LOCKS", "set_provider_override",
           "session_roof_payload", "LatLon", "RoofModel", "FromAddressRequest"]
