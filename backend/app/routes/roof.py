"""Forms path: the same services the agent uses, as plain endpoints (works without any LLM)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from ..config import get_settings
from ..errors import ApiError
from ..models import FinalizeRequest, FromAddressRequest, LayoutRequest, RoofModel, SketchRequest
from ..services import geo, layout, roof, upload_check
from ..services.auth import AuthContext, require_auth

router = APIRouter(prefix="/api", tags=["roof"])


class GeocodeRequest(BaseModel):
    q: str = Field(min_length=3, max_length=200)


@router.post("/geocode")
def geocode(req: GeocodeRequest):
    return geo.geocode(req.q)


@router.post("/roof/from-address", response_model=RoofModel)
def roof_from_address(req: FromAddressRequest):
    return geo.roof_from_address(req.lat, req.lon)


@router.post("/roof/finalize", response_model=RoofModel)
def roof_finalize(req: FinalizeRequest):
    return roof.finalize(req)


@router.post("/roof/from-sketch", response_model=RoofModel)
def roof_from_sketch(req: SketchRequest):
    return roof.sketch_to_roof(req)


@router.post("/roof/layout")
def roof_layout(req: LayoutRequest):
    return layout.pack_panels(req.roof, req.panel)


@router.post("/roof/check-upload", response_model=upload_check.UploadVerdict)
def roof_check_upload(file: Annotated[UploadFile, File()], ctx: Annotated[AuthContext, Depends(require_auth)]):
    """Sketch canvas guardrail: is this upload a roof photo, plan, blueprint or satellite view? Fails open if Gemini is down."""
    if not getattr(file, "filename", None):
        raise ApiError("empty_file", "No file was sent.", status=422)
    return upload_check.check_upload(file.filename, file.file, get_settings(), user_id=ctx.user["id"])
