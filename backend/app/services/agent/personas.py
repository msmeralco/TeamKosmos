"""Synthetic demo households. The frontend sends only the persona id; the backend owns the data."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    first: str
    monthly_kwh: float
    template: str  # night_heavy | balanced | day_heavy
    city: str
    lat: float  # approximate city centroid, used as default location for irradiance
    lon: float

    @property
    def subtitle(self) -> str:
        pretty = {"night_heavy": "Night-heavy", "balanced": "Balanced", "day_heavy": "Day-heavy"}[self.template]
        return f"{self.monthly_kwh:g} kWh/mo · {pretty}"


PERSONAS: dict[str, Persona] = {
    "reyes": Persona("reyes", "Reyes Family", "Reyes Family", 450, "balanced", "Quezon City", 14.6760, 121.0437),
    "maria": Persona("maria", "Ate Maria", "Maria", 250, "night_heavy", "Pasig City", 14.5764, 121.0851),
    "wfh": Persona("wfh", "WFH Couple", "Alex & Sam", 700, "day_heavy", "Makati City", 14.5547, 121.0244),
}
DEFAULT_PERSONA = "reyes"


def get_persona(persona_id: str | None) -> Persona:
    return PERSONAS.get(persona_id or "", PERSONAS[DEFAULT_PERSONA])
