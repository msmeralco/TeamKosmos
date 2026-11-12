"""Solar Passport endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import get_repo
from ..errors import ApiError
from ..services import passport
from ..services.agent.runner import LOCKS, _busy
from ..services.agent.session import Session, save_session
from ..services.agent.tools import TurnContext

router = APIRouter(tags=["passport"])


class IssueRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    package_index: int | None = Field(None, ge=0)


@router.post("/api/passport")
def issue(req: IssueRequest):
    settings = get_settings()
    token = LOCKS.acquire(req.session_id, settings.turn_timeout_s * 2)
    if token is None:
        raise _busy()
    try:
        state = get_repo().get_session(req.session_id)
        if not state:
            raise ApiError("not_found", "No conversation with that id.", status=404)
        s = Session.model_validate(state)
        ctx = TurnContext(s, "", "english", [], lambda e: None, settings)
        result = ctx.call_tool("issue_passport", {"package_index": req.package_index})
        if result.get("error"):
            raise ApiError(result["error"], result.get("message", "Could not issue the Passport."), hint=result.get("hint", ""), status=409)
        save_session(s)
        return passport.get(result["id"])
    finally:
        LOCKS.release(req.session_id, token)


@router.post("/api/passport/verify")
def verify_pasted(record: dict = Body(...)):
    """Paste-to-verify: checked against Sol's own key and ledger, so a changed digit fails."""
    return passport.verify_pasted(record)


@router.get("/api/passport/{record_id}")
def get_passport(record_id: str):
    return passport.get(record_id)


@router.get("/api/passport/{record_id}/verify")
def verify_stored(record_id: str):
    return passport.verify_stored(record_id)


@router.get("/verify/{record_id}", response_class=HTMLResponse)
def verify_page(record_id: str):
    return HTMLResponse(passport.html_page(record_id))
