"""The household behind a chat: built from the signed-in user's account row, never from fixed demo data."""
from __future__ import annotations

from dataclasses import dataclass

# Map centre used only when the account has no location yet (central Metro Manila).
DEFAULT_LAT, DEFAULT_LON = 14.5995, 120.9842
DEFAULT_CITY = "Metro Manila"
DEFAULT_TEMPLATE = "balanced"


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    first: str
    monthly_kwh: float | None
    template: str  # night_heavy | balanced | day_heavy
    city: str
    lat: float  # default location for irradiance and the roof map
    lon: float

    @property
    def subtitle(self) -> str:
        pretty = {"night_heavy": "Night-heavy", "balanced": "Balanced", "day_heavy": "Day-heavy"}[self.template]
        return f"{self.monthly_kwh:g} kWh/mo · {pretty}" if self.monthly_kwh else pretty


def household_from_user(user: dict) -> dict:
    """The snapshot stored on a session. Plain JSON so it survives the session round trip."""
    name = user.get("household_name") or user["name"]
    return {
        "name": name, "first": user["name"].split()[0] if not user.get("household_name") else name,
        "monthly_kwh": user.get("monthly_kwh"), "template": user.get("household_template") or DEFAULT_TEMPLATE,
        "city": user.get("city") or DEFAULT_CITY,
        "lat": user["lat"] if user.get("lat") is not None else DEFAULT_LAT,
        "lon": user["lon"] if user.get("lon") is not None else DEFAULT_LON,
    }


def persona_from_household(persona_id: str, h: dict | None) -> Persona:
    h = h or {}
    return Persona(
        id=persona_id, name=h.get("name") or "your household", first=h.get("first") or "there",
        monthly_kwh=h.get("monthly_kwh"), template=h.get("template") or DEFAULT_TEMPLATE,
        city=h.get("city") or DEFAULT_CITY,
        lat=h["lat"] if h.get("lat") is not None else DEFAULT_LAT,
        lon=h["lon"] if h.get("lon") is not None else DEFAULT_LON,
    )
