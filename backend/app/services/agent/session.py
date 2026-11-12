"""Session state: what the agent knows about the household, plus chat history and results."""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from ...db import get_repo
from .personas import Persona, household_from_user, persona_from_household

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
    persona_id: str  # the owning user's id
    household: dict = Field(default_factory=dict)  # snapshot of the user's household, refreshed every turn
    title: str = ""  # shown in the user's chat list
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
        return persona_from_household(self.persona_id, self.household)

    def add_history(self, role: str, text: str) -> None:
        if text:
            self.history.append({"role": role, "text": text})
            del self.history[:-HISTORY_LIMIT]

    def invalidate_results(self) -> None:
        self.results = {}
        self.profile.confirmed = False


def sync_household(session: Session, user: dict) -> None:
    """Refresh the household snapshot from the user's account and re-seed the load if the account's usage changed.

    A load the user typed in chat (load_source != "persona") is never overwritten.
    """
    new = household_from_user(user)
    changed = new != session.household
    session.household = new
    session.persona_id = user["id"]
    p = session.profile
    if p.load_source != "persona":
        return
    if changed or (p.monthly_kwh is None and new["monthly_kwh"] is not None):
        if p.monthly_kwh != new["monthly_kwh"] or p.household_template != new["template"]:
            if p.load_confirmed or session.results:
                session.invalidate_results()
            p.monthly_kwh = new["monthly_kwh"]
            p.monthly_bill_php = None
            p.household_template = new["template"]
            p.load_confirmed = False
            session.pending.pop("changing", None)


def load_session(session_id: str, user: dict, language: str | None) -> Session:
    """Load the user's session, or start a fresh one seeded from their household. Callers check ownership first."""
    state = get_repo().get_session(session_id)
    if state:
        session = Session.model_validate(state)
    else:
        session = Session(id=session_id, persona_id=user["id"])
        session.profile.monthly_kwh = user.get("monthly_kwh")
        session.profile.household_template = user.get("household_template") or "balanced"
    sync_household(session, user)
    if language in ("auto", "english", "taglish"):
        session.language = language
    return session


def save_session(session: Session) -> None:
    get_repo().save_session(session.id, session.model_dump(mode="json"), user_id=session.persona_id, title=session.title or None)