"""Provider interface plus the deterministic ScriptedProvider and a FakeProvider for tests."""
from __future__ import annotations

import logging
import re
import time
from typing import Protocol

from .. import geo, installers, market_packages, rag
from . import intake, nlu, reply_format
from .summary import render_tool_result
from .tools import TurnContext

log = logging.getLogger("sol.agent")


class ProviderUnavailable(Exception):
    """The LLM could not answer (rate limit, outage, bad key). The caller falls back to the scripted agent."""


class Provider(Protocol):
    name: str

    def run_turn(self, ctx: TurnContext) -> str: ...


def tool_sentences(ctx: TurnContext) -> list[str]:
    """Plain sentences for everything the tools did this turn (also the number-guard fallback)."""
    out: list[str] = []
    for call in ctx.tool_calls:
        text = render_tool_result(call["name"], call["result"], reply_format.detect_intent(ctx.user_text))
        if text and text not in out:  # a tool called twice must not repeat its sentence
            out.append(text)
    return out


def question_text(ctx: TurnContext) -> str:
    s = ctx.session
    if any(isinstance(r, dict) and r.get("needs_location") for r in ctx.results_of("find_installers")):
        return ""  # we just asked where the home is; a second question about the site would bury it
    if any(isinstance(r, dict) and r.get("found") for r in ctx.results_of("package_details")):
        return ""  # the user is reading one package; repeating the whole summary would only bury it
    return intake.question_for(intake.next_slot(s), s, ctx.lang)


class ScriptedProvider:
    """Rule-based agent: exact-match choices, regex extraction, template replies. Needs no LLM or key."""

    name = "scripted"

    # ---- helpers ---------------------------------------------------------------------------------------------
    def _announce_new_roof(self, ctx: TurnContext, notes: list[str]) -> bool:
        """A roof submitted from the map panel between turns is acknowledged on the next message."""
        s = ctx.session
        roof = s.profile.roof
        if roof and s.pending.get("roof_announced_id") != roof["id"]:
            s.pending["roof_announced_id"] = roof["id"]
            if "analysis" in s.results:
                return False  # results already exist for this roof, so announcing it again would only add noise
            from .summary import roof_text

            notes.append(roof_text(roof))
            ctx.flags["open_map"] = True
            return True
        return False

    def _handle_action(self, ctx: TurnContext, action: dict, notes: list[str]) -> None:
        s = ctx.session
        kind, payload = action["kind"], action["payload"]
        if kind == "update":
            if "roof_method" in payload:
                ctx.call_tool("request_roof_input", {"mode": payload["roof_method"]})
            else:
                ctx.call_tool("update_profile", payload)
        elif kind == "pick":
            ctx.call_tool("get_building_outline", {"candidate_index": payload})
        elif kind == "tool":
            ctx.call_tool(payload, {})
        elif kind == "note":
            notes.append("Okay. Type your monthly bill in pesos or your usage in kWh." if payload == "load_bill"
                         else "Okay. Attach a clear photo of your bill, and I'll read it and ask you to confirm.")
        else:  # changing / change
            intake.run_action(s, action)

    # ---- several requests in one message -----------------------------------------------------------------------
    # "the bill is now 34k and run the numbers" is two jobs. They are done in a fixed, safe order: (1) save the
    # details, (2) run the numbers, (3) the follow-ups that need the numbers. A step only starts when the one before
    # it worked. When one cannot be done yet, the rest are kept in pending["queued"] and finished automatically.
    FOLLOW_UP_TOOLS = {"nm_compare": "compare_net_metering", "fill_roof": "toggle_roof_fill", "passport": "issue_passport"}
    ACTION_LABELS = {"run": "run the numbers", "nm_compare": "compare net metering", "fill_roof": "preview your whole installation site",
                     "passport": "create your Solar Passport"}

    @classmethod
    def _label_list(cls, actions: list[str]) -> str:
        names = [cls.ACTION_LABELS[a] for a in actions]
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    @staticmethod
    def _failed(result: dict) -> bool:
        return bool(result.get("error") or result.get("errors") or result.get("rejected"))

    def _handle_compound(self, ctx: TurnContext, actions: list[str], fields: dict, notes: list[str]) -> bool:
        s = ctx.session
        after = ctx.after_notes
        follow_ups = [a for a in actions if a != "run"]

        if fields:  # step 1: details first, so everything after works on the new values
            if self._failed(ctx.call_tool("update_profile", fields)):
                s.pending["queued"] = follow_ups
                after.append(f"I stopped there so nothing runs on a wrong value. Fix that and I'll continue with {self._label_list(actions)}."
                             if actions else "")
                return True

        if "run" in actions and "analysis" not in s.results:  # step 2: the numbers
            s.pending.pop("changing", None)  # "just run it" in the change menu means: leave the menu and go
            slot = intake.next_slot(s)
            if slot == "confirm":  # the message itself said to run them, so that is the go-ahead
                ctx.call_tool("update_profile", {"confirm_summary": True})
                slot = intake.next_slot(s)
            if slot != "run":
                s.pending["queued"] = follow_ups
                more = f", then {self._label_list(follow_ups)}" if follow_ups else ""
                after.append(f"I can't run the numbers yet because something is still missing. Once it's filled in I'll show you the summary to confirm{more}.")
                return True
            if self._failed(ctx.call_tool("run_analysis", {})):
                s.pending["queued"] = follow_ups
                after.append(f"I stopped there, so I haven't done {self._label_list(follow_ups)}." if follow_ups else "")
                return True
        elif "run" in actions and not fields:
            after.append("Your numbers are already up to date. If you change anything, I'll run them again.")

        self._run_follow_ups(ctx, follow_ups)  # step 3: needs the numbers
        return True

    def _run_follow_ups(self, ctx: TurnContext, actions: list[str]) -> None:
        s = ctx.session
        after = ctx.after_notes
        s.pending.pop("queued", None)
        for i, action in enumerate(actions):
            if "analysis" not in s.results:
                s.pending["queued"] = actions[i:]
                after.append(f"Once the numbers are ready I'll also {self._label_list(actions[i:])}.")
                return
            if self._failed(ctx.call_tool(self.FOLLOW_UP_TOOLS[action], {})):
                rest = actions[i + 1:]
                if rest:
                    s.pending["queued"] = rest
                    after.append(f"I stopped there. Still to do: {self._label_list(rest)}.")
                return

    def _handle_free_text(self, ctx: TurnContext, text: str, notes: list[str]) -> bool:
        """Returns True if the message was understood."""
        s = ctx.session
        slot = intake.next_slot(s)
        intent = nlu.detect_intent(text)
        analysed = "analysis" in s.results

        if s.pending.get("queued") and re.search(r"\b(cancel|never ?mind|forget (?:it|that)|skip (?:it|that))\b", text.lower()):
            s.pending.pop("queued", None)  # the user dropped what was waiting
            notes.append("Okay, I've dropped the things I had lined up.")
            return True
        actions = nlu.requested_actions(text)
        if actions:
            fields = nlu.extract(text, slot, s.profile.goal)
            if len(actions) >= 2 or fields or "run" in actions:
                return self._handle_compound(ctx, actions, fields, notes)

        if intent == "passport" and analysed:
            ctx.call_tool("issue_passport", {})
            return True
        if intent == "nm_compare" and analysed:
            ctx.call_tool("compare_net_metering", {})
            return True
        if re.search(r"tell me more about|more (?:info|details?) (?:on|about)|details? (?:on|about|of)", text, re.I):
            pk = market_packages.find(text)
            if pk:
                ctx.call_tool("package_details", {"name": pk["name"], "installer": None if pk["synthetic"] else pk["installer"]})
                return True
        if intent == "packages":
            ctx.call_tool("find_packages", {"battery": nlu.battery_wish(text), "location": text if installers.region_for(text) else None})
            return True
        if intent == "brief":
            ctx.call_tool("solar_brief", {})
            return True
        if intent == "export":
            ctx.call_tool("export_plan", {})
            return True
        if intent == "recommend" and s.profile.roof and not analysed:
            ctx.call_tool("recommend_budget", {})
            return True
        if intent == "recommend" and analysed:
            from .summary import analysis_text

            notes.append(analysis_text(s.results["summary"]))  # the numbers already ran: restate the top pick
            return True
        if intent == "recommend" and not s.profile.roof:
            notes.append("I can size a recommendation once I know your installation site and usage.")
            return True
        if intent == "installers" or (s.pending.get("await_installer_location") and nlu.detect_intent(text) is None
                                      and (installers.region_for(text) or len(text.split()) <= 4)):
            place = text if installers.region_for(text) or installers.RESET.search(text) or intent != "installers" else ""  # "suggest installers" names no place yet
            ctx.call_tool("find_installers", {"location": place, "show_all": bool(re.search(r"\ball\b|every|more", text, re.I))})
            return True
        if intent in ("docs", "ask"):
            if intent == "docs" or rag.search(text[:300], k=1):
                ctx.call_tool("search_docs", {"query": text[:300]})
                return True
            intent = "explain"  # a general question the library cannot answer: fall back to the assumptions list
        if intent == "explain":
            ctx.call_tool("explain_assumptions", {"topic": text[:80]})
            return True
        if intent == "products":
            ctx.call_tool("search_products", {})
            return True

        if slot == "roof_method":
            # Details given in passing ("my bill is 7000 and I have 400k") are saved and acknowledged first.
            fields = nlu.extract(text, slot, s.profile.goal)
            if fields:
                ctx.call_tool("update_profile", fields)
                return True
            method = nlu.method_from(text)
            if geo.has_demo_match(text):  # a named synthetic demo site still loads directly (demos and tests)
                ctx.call_tool("geocode_address", {"query": text})
                return True
            if method:
                ctx.call_tool("request_roof_input", {"mode": method})
                return True
            if nlu.looks_like_address(text):
                ctx.call_tool("request_roof_input", {"mode": "draw"})
                notes.append("I can't look up addresses in the chat. Use the search box on the map to jump to your street, then outline your installation site.")
                return True
            return False
        if slot == "roof_draw":
            method = nlu.method_from(text)
            if method and method != s.profile.roof_method and not re.search(r"\b(done|finished|tapos|ok(?:ay)?)\b", text.lower()):
                ctx.call_tool("request_roof_input", {"mode": method})
                return True
            ctx.flags["open_map"] = True
            notes.append("I don't see an installation site outline yet. Please finish it in the map panel, then tell me.")
            return True
        if slot == "change":
            low = text.lower().strip()
            if re.search(r"\b(go|go ahead|run|retry|try again|proceed|sige)\b", low) and not nlu.extract(text, slot, s.profile.goal):
                # "go" / "run the numbers": leave the menu and run with what is already filled in.
                s.pending.pop("changing", None)
                if intake.next_slot(s) == "confirm":
                    s.profile.confirmed = True
                return True
            if re.search(r"\b(cancel|never ?mind|nvm|go back|keep (?:it|everything)|no changes?|nothing|none|nope|no)\b", low) \
                    and not nlu.extract(text, slot, s.profile.goal):
                s.pending.pop("changing", None)  # back out of the change menu
                return True
            fields = nlu.extract(text, "budget", s.profile.goal)  # a bare amount here is most likely the budget
            if fields:  # "make it 250k": apply the new value directly instead of asking again
                ctx.call_tool("update_profile", fields)
                return True
            for key, labels in (("roof", ("site", "roof")), ("load", ("bill",)), ("budget", ("budget",)), ("goal", ("goal",)), ("system", ("system",))):
                if any(label in text.lower() for label in labels):
                    act = intake.match_choice(s, intake.CHANGE_CHOICES[key][2])
                    intake.run_action(s, act)  # type: ignore[arg-type]
                    return True
            return False

        fields = nlu.extract(text, slot, s.profile.goal)
        if slot == "confirm" and nlu.is_negate(text) and not fields:
            intake.run_action(s, intake.match_choice(s, intake.CHANGE_TEXT))  # type: ignore[arg-type]
            return True
        if fields:
            ctx.call_tool("update_profile", fields)
            return True
        if slot == "done":
            return False
        return False

    # ---- main --------------------------------------------------------------------------------------------------
    def run_turn(self, ctx: TurnContext) -> str:
        ctx.trusted = True  # values below are parsed from the user's own text or a choice button
        s = ctx.session
        text = ctx.user_text.strip()
        notes: list[str] = []
        first = s.turn_count == 0
        understood = True

        if ctx.attachments:
            notes.append("I can't read photos or PDFs in quick mode. Please type your monthly bill in pesos or your usage in kWh.")
        announced = self._announce_new_roof(ctx, notes)
        if text:
            action = intake.match_choice(s, text)
            if action:
                self._handle_action(ctx, action, notes)
            else:
                understood = self._handle_free_text(ctx, text, notes) or announced  # "I've finished my roof" is understood

        if intake.next_slot(s) == "run" and not ctx.results_of("run_analysis"):
            ctx.call_tool("run_analysis", {})

        # Things lined up from an earlier message are finished as soon as the numbers exist.
        queued = list(s.pending.get("queued") or [])
        if queued and "analysis" in s.results:
            self._run_follow_ups(ctx, queued)

        parts: list[str] = []
        if first:
            parts.append(intake.INTRO[ctx.lang if ctx.lang in intake.INTRO else "english"].format(first=s.persona.first))
        parts.extend(notes)
        parts.extend(tool_sentences(ctx))
        parts.extend(ctx.after_notes)
        if not understood and not first and not ctx.tool_calls:
            parts.append("Sorry, I didn't catch that." if ctx.lang != "taglish" else "Pasensya, hindi ko nakuha.")
        parts.append(question_text(ctx))
        return "\n\n".join(p for p in parts if p)


class FakeProvider:
    """Test double: replays a script of ('tool', name, args) and ('text', str) steps."""

    name = "fake"

    def __init__(self, script: list[tuple]):
        self.script = script

    def run_turn(self, ctx: TurnContext) -> str:
        text = ""
        for step in self.script:
            if step[0] == "tool":
                ctx.call_tool(step[1], step[2] if len(step) > 2 else {})
            elif step[0] == "text":
                text = step[1]
            elif step[0] == "raise":
                raise step[1]
            elif step[0] == "sleep":
                time.sleep(step[1])
        return text
