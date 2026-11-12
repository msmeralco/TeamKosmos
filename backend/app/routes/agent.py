"""Chat agent endpoints. The payload mirrors the frontend's AgentMsg: steps [{id,label,status}] and
reply {text, hasMapArtifact, next:[{id,label,hint,text}]} (plus additive `cards` and `slot`)."""
from __future__ import annotations

import json
import re
from typing import Annotated, Literal, Union

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import Field

from ..config import get_settings
from ..db import get_repo
from ..errors import ApiError
from ..models import FinalizeRequest, FromAddressRequest, SketchRequest
from ..services.agent import intake
from ..services.agent.attachments import validate_files
from ..services.agent.runner import LOCKS, ChatRequest, run_turn_json, session_roof_payload, stream_events, submit_roof
from ..services.agent.session import Session
from ..services.auth import AuthContext, require_auth

router = APIRouter(prefix="/api/agent", tags=["agent"])
ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")  # the id doubles as the access key: use a random UUID
MAX_MESSAGE = 4000


def _check_id(conversation_id: str) -> str:
    if not ID_RE.match(conversation_id or ""):
        raise ApiError("invalid_conversation_id", "conversation_id must be 16 to 64 letters, digits, dashes or underscores (use a UUID).", status=422)
    return conversation_id


def _authorize(session_id: str, user_id: str, *, must_exist: bool = False) -> None:
    """A conversation id only works for the account that created it. Others get the same 404 as a missing id."""
    repo = get_repo()
    owner = repo.get_session_owner(session_id)
    if owner == user_id:
        return
    if owner is None and not must_exist and repo.get_session(session_id) is None:
        return  # a brand-new conversation
    raise ApiError("not_found", "No conversation with that id.", status=404)


def sse(ev: dict) -> str:
    if ev["event"] == "keepalive":
        return ": keepalive\n\n"
    return f"event: {ev['event']}\ndata: {json.dumps(ev['data'], ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(
    conversation_id: Annotated[str, Form()],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    message: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "auto",
    files: Annotated[list[UploadFile] | None, File()] = None,
    stream: Annotated[bool, Query(description="false returns the finished message as JSON")] = True,
):
    settings = get_settings()
    _check_id(conversation_id)
    _authorize(conversation_id, ctx.user["id"])
    if language not in ("auto", "english", "taglish"):
        raise ApiError("invalid_language", "language must be auto, english or taglish.", status=422)
    if len(message) > MAX_MESSAGE:
        raise ApiError("message_too_long", f"Messages can be up to {MAX_MESSAGE} characters.", status=422)
    uploads = [f for f in (files or []) if getattr(f, "filename", "")]
    attachments = validate_files([(f.filename, f.file) for f in uploads], max_files=settings.max_files, max_bytes=settings.max_upload_bytes)
    if not message.strip() and not attachments:
        raise ApiError("empty_message", "Type a message or attach a file.", status=422)
    req = ChatRequest(conversation_id=conversation_id, message=message, user=ctx.user, language=language, files=attachments)
    if not stream:
        return run_turn_json(req, settings)
    events = stream_events(req, settings)  # raises 409 here, before the response starts
    return StreamingResponse((sse(e) for e in events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


def _load(session_id: str, user_id: str) -> Session:
    _check_id(session_id)
    _authorize(session_id, user_id, must_exist=True)
    state = get_repo().get_session(session_id)
    if not state:
        raise ApiError("not_found", "No conversation with that id.", status=404)
    return Session.model_validate(state)


@router.get("/sessions")
def list_sessions(ctx: Annotated[AuthContext, Depends(require_auth)]):
    """The signed-in user's chats, newest first."""
    rows = get_repo().list_sessions(ctx.user["id"])
    return {"sessions": [{"id": r["id"], "title": r["title"], "turnCount": r["turn_count"], "updatedAt": r["updated_at"]} for r in rows]}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, ctx: Annotated[AuthContext, Depends(require_auth)]):
    s = _load(session_id, ctx.user["id"])
    return {
        "id": s.id, "title": s.title, "language": s.language, "turnCount": s.turn_count,
        "nextSlot": intake.next_slot(s), "profile": s.profile.model_dump(mode="json"),
        "summary": s.results.get("summary"), "passport": s.results.get("passport"),
        "history": s.history, "guardEvents": s.guard_events,
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, ctx: Annotated[AuthContext, Depends(require_auth)]):
    _check_id(session_id)
    _authorize(session_id, ctx.user["id"], must_exist=True)
    token = LOCKS.acquire(session_id, get_settings().turn_timeout_s * 2)
    if token is None:  # a running turn would re-save the session right after we delete it
        raise ApiError("turn_in_progress", "Sol is still working on this chat.", hint="Try again in a moment.", status=409)
    try:
        return {"deleted": get_repo().delete_session(session_id)}
    finally:
        LOCKS.release(session_id, token)

class DrawnSubmit(FinalizeRequest):
    mode: Literal["drawn"]


class SketchSubmit(SketchRequest):
    mode: Literal["sketch"]


class AddressSubmit(FromAddressRequest):
    mode: Literal["address"]


RoofSubmit = Annotated[Union[DrawnSubmit, SketchSubmit, AddressSubmit], Field(discriminator="mode")]


@router.post("/sessions/{session_id}/roof")
def post_roof(session_id: str, body: RoofSubmit, ctx: Annotated[AuthContext, Depends(require_auth)]):
    """The map panel / canvas sends the finished roof here. The next chat turn acknowledges it."""
    _check_id(session_id)
    _authorize(session_id, ctx.user["id"])
    return submit_roof(session_id, body, ctx.user)


@router.get("/sessions/{session_id}/roof")
def get_roof(session_id: str, ctx: Annotated[AuthContext, Depends(require_auth)]):
    return session_roof_payload(_load(session_id, ctx.user["id"]))