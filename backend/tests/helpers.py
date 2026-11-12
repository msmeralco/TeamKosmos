"""Test accounts: household data lives here, not in the application code."""
from __future__ import annotations

HOUSEHOLDS = {
    "reyes": {"name": "Reyes Family", "household_name": "Reyes Family", "city": "Quezon City", "lat": 14.676, "lon": 121.0437, "monthly_kwh": 450, "household_template": "balanced"},
    "maria": {"name": "Maria Santos", "household_name": "Ate Maria", "city": "Pasig City", "lat": 14.5764, "lon": 121.0851, "monthly_kwh": 250, "household_template": "night_heavy"},
    "wfh": {"name": "Alex Cruz", "household_name": "WFH Couple", "city": "Makati City", "lat": 14.5547, "lon": 121.0244, "monthly_kwh": 700, "household_template": "day_heavy"},
}


def user_row(key: str = "reyes", user_id: str = "user-test-0001") -> dict:
    """A database-shaped user row for tests that call the services directly."""
    return {"id": user_id, "email": f"{key}@sol-tests.dev", **HOUSEHOLDS[key]}