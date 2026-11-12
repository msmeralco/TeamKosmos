"""Account endpoints: sign up, sign in, sign out, and the signed-in user's profile."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import get_repo
from ..services import auth
from ..services.auth import AuthContext, require_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class HouseholdFields(BaseModel):
    household_name: str | None = Field(None, max_length=80)
    city: str | None = Field(None, max_length=80)
    lat: float | None = None
    lon: float | None = None
    monthly_kwh: float | None = None
    household_template: Literal["night_heavy", "balanced", "day_heavy"] | None = None


class SignupBody(HouseholdFields):
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class ProfileBody(HouseholdFields):
    name: str | None = Field(None, max_length=80)


def _session_payload(user: dict) -> dict:
    return {"token": auth.issue_token(user["id"]), "user": auth.public_user(user)}


@router.post("/signup", status_code=201)
def signup(body: SignupBody):
    user = auth.create_user(email=body.email, password=body.password, name=body.name,
                            **body.model_dump(exclude={"name", "email", "password"}))
    return _session_payload(user)


@router.post("/login")
def login(body: LoginBody):
    return _session_payload(auth.authenticate(body.email, body.password))


@router.post("/logout")
def logout(ctx: Annotated[AuthContext, Depends(require_auth)]):
    auth.revoke_token(ctx.token)
    return {"ok": True}


@router.get("/me")
def me(ctx: Annotated[AuthContext, Depends(require_auth)]):
    return {"user": auth.public_user(ctx.user)}


@router.patch("/me")
def update_me(body: ProfileBody, ctx: Annotated[AuthContext, Depends(require_auth)]):
    fields = auth.validate_household(body.model_dump(exclude={"name"}, exclude_unset=True))
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise auth.ApiError("invalid_name", "Name cannot be empty.", status=422)
        fields["name"] = name
    get_repo().update_user(ctx.user["id"], fields)
    return {"user": auth.public_user(get_repo().get_user(ctx.user["id"]))}
