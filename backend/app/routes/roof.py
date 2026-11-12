"""Forms path: the same services the agent uses, as plain endpoints (works without any LLM)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..models import FinalizeRequest, FromAddressRequest, LayoutRequest, RoofModel, SketchRequest
from ..services import geo, layout, roof

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
