"""Demo rewards: the signed-in solar owner's Passport and vouchers."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..services import rewards
from ..services.auth import AuthContext, require_auth

router = APIRouter(prefix="/api/rewards", tags=["rewards"])


@router.get("")
def get_rewards(ctx: Annotated[AuthContext, Depends(require_auth)]):
    return rewards.overview(ctx.user)


@router.post("/{voucher_id}/redeem")
def redeem(voucher_id: str, ctx: Annotated[AuthContext, Depends(require_auth)]):
    return rewards.redeem(ctx.user, voucher_id)
