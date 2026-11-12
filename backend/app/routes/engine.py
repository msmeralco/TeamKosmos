"""Load, catalog, optimizer, simulation and assumptions endpoints."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from ..errors import ApiError
from ..models import RoofModel
from ..services import load as load_svc
from ..services import optimizer, products, simulate
from ..services.agent.tools import jsonable
from ..services.assumptions import all_assumptions
from ..services.scraper import search as product_search

router = APIRouter(prefix="/api", tags=["engine"])


class LoadSpec(BaseModel):
    monthly_kwh: float | None = Field(None, gt=0)
    bill_php: float | None = Field(None, gt=0)
    template: Literal["night_heavy", "balanced", "day_heavy"] = "balanced"

    @model_validator(mode="after")
    def _one_of(self):
        if (self.monthly_kwh is None) == (self.bill_php is None):
            raise ValueError("give exactly one of monthly_kwh or bill_php")
        return self

    def build(self) -> load_svc.LoadProfile:
        return load_svc.estimate_load(monthly_kwh=self.monthly_kwh, bill_php=self.bill_php, template=self.template)


class LoadRequest(LoadSpec):
    include_hourly: bool = False


@router.post("/load/estimate")
def load_estimate(req: LoadRequest):
    return req.build().to_dict(include_hourly=req.include_hourly)


@router.get("/products")
def get_products(category: Literal["panel", "inverter", "battery"] | None = None):
    return {"products": products.list_products(category),
            "note": "Suggested prices from demo or public listings. Confirm with the seller."}


@router.post("/products/search")
def search_products(categories: list[Literal["panel", "inverter", "battery"]] | None = None):
    """Server-sent events: source_started, product_found, source_failed, done."""
    def gen():
        for ev in product_search.search(categories):
            yield f"event: {ev['event']}\ndata: {json.dumps(jsonable(ev), ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class OptimizeRequest(LoadSpec):
    roof: RoofModel
    budget_max_php: float = Field(gt=0)
    budget_min_php: float | None = Field(None, ge=0)
    goal: Literal["cut_bill", "max_savings_10y", "fastest_payback", "backup"]
    goal_target_pct: float | None = Field(None, ge=5, le=100)
    backup_hours: float | None = Field(None, ge=1, le=48)

    @model_validator(mode="after")
    def _goal_params(self):
        if self.goal == "cut_bill" and self.goal_target_pct is None:
            raise ValueError("goal_target_pct is required for cut_bill")
        return self


@router.post("/optimize")
def optimize(req: OptimizeRequest):
    return jsonable(optimizer.optimize(req.roof, req.build(), budget_max_php=req.budget_max_php, budget_min_php=req.budget_min_php,
                                       goal=req.goal, goal_target_pct=req.goal_target_pct, backup_hours=req.backup_hours))


class SimulateRequest(LoadSpec):
    roof: RoofModel
    package: dict
    export_credit_php_per_kwh: float | None = Field(None, ge=0, le=30)
    tariff_php_per_kwh: float | None = Field(None, gt=0, le=60)


@router.post("/simulate")
def simulate_route(req: SimulateRequest):
    try:
        return jsonable(simulate.simulate_package(req.package, req.roof, req.build(),
                                                  export_credit_php_per_kwh=req.export_credit_php_per_kwh,
                                                  tariff_php_per_kwh=req.tariff_php_per_kwh))
    except (KeyError, TypeError) as exc:
        raise ApiError("invalid_package", f"The package is missing or has a wrong field: {exc}.",
                       hint="Use a package returned by /api/optimize.", status=422)


@router.get("/assumptions")
def assumptions(verified: bool | None = Query(None, description="filter by verified status")):
    items = all_assumptions()
    if verified is not None:
        items = [a for a in items if a["verified"] is verified]
    return {"assumptions": items, "note": "Unverified entries are placeholders or judgement and are labelled as such."}
