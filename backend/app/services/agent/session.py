"""Session state: what the agent knows about the household, plus chat history and results."""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from ...db import get_repo
from .personas import Persona, get_persona

GOALS = ("cut_bill", "max_savings_10y", "fastest_payback", "backup")
TEMPLATES = ("night_heavy", "balanced", "day_heavy")
HISTORY_LIMIT = 40


class Profile(BaseModel):
    roof_method: Literal["address", "draw", "sketch"] | None = None
    roof: dict | None = None
    monthly_kwh: float | None = None
    monthly_bill_php: float | None = None
    household_template: str | None = None
    load_source: Literal["persona", "user", "bill_photo"] = "persona"
    load_confirmed: bool = False
    budget_min_php: float | None = None
    budget_max_php: float | None = None
    goal: str | None = None
    goal_target_pct: float | None = None
    backup_hours: float | None = None
    net_metering: bool = True
    confirmed: bool = False


class Session(BaseModel):
    id: str
    persona_id: str
    language: str = "auto"
    profile: Profile = Field(default_factory=Profile)
    history: list[dict] = Field(default_factory=list)  # {"role": "user"|"model", "text": str}
    pending: dict[str, Any] = Field(default_factory=dict)  # transient: address candidates, changing flag
    results: dict[str, Any] = Field(default_factory=dict)  # analysis outputs (also the number-guard allow list)
    guard_events: list[dict] = Field(default_factory=list)
    turn_count: int = 0
    created_at: float = Field(default_factory=time.time)

    @property
    def persona(self) -> Persona:
        return get_persona(self.persona_id)

    def add_history(self, role: str, text: str) -> None:
        if text:
            self.history.append({"role": role, "text": text})
            del self.history[:-HISTORY_LIMIT]

    def invalidate_results(self) -> None:
        self.results = {}
        self.profile.confirmed = False


def apply_persona(session: Session, persona_id: str) -> None:
    """Seed (or re-seed) the household load from the persona unless the user typed their own."""
    persona = get_persona(persona_id)
    changed = persona.id != session.persona_id
    session.persona_id = persona.id
    p = session.profile
    if p.load_source == "persona" and (changed or p.monthly_kwh is None):
        if p.monthly_kwh != persona.monthly_kwh or p.household_template != persona.template:
            if p.load_confirmed or session.results:
                session.invalidate_results()
        p.monthly_kwh = persona.monthly_kwh
        p.monthly_bill_php = None
        p.household_template = persona.template
        p.load_confirmed = False
        if changed:
            session.pending.pop("changing", None)


def load_session(session_id: str, persona_id: str | None, language: str | None) -> Session:
    state = get_repo().get_session(session_id)
    if state:
        session = Session.model_validate(state)
    else:
        persona = get_persona(persona_id)
        session = Session(id=session_id, persona_id=persona.id)
        session.profile.monthly_kwh = persona.monthly_kwh
        session.profile.household_template = persona.template
    if persona_id and persona_id != session.persona_id:
        apply_persona(session, persona_id)
    if language in ("auto", "english", "taglish"):
        session.language = language
    return session


def save_session(session: Session) -> None:
    get_repo().save_session(session.id, session.model_dump(mode="json"))
