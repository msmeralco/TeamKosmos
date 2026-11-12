# Sol data contracts

The Pydantic models in `backend/app/models.py` are the source of truth. The frontend mirrors them in `frontend/src/lib/api.ts`. The chat and SSE contract is in `backend/docs/agent-contract.md`.

Interactive docs while the backend runs: `http://127.0.0.1:8000/docs`.

## API surface

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Database, LLM and PVGIS status |
| `POST /api/geocode` | Address candidates `{label, lat, lon}` |
| `POST /api/roof/from-address` | OSM building outline as a `RoofModel` (404 with a hint if none) |
| `POST /api/roof/finalize` | Polygon to metres, usable area, tilt and azimuth |
| `POST /api/roof/from-sketch` | Canvas sketch with manual scale to a `RoofModel` |
| `POST /api/roof/layout` | Panel packing inside the usable polygon |
| `POST /api/load/estimate` | Hourly `LoadProfile` from kWh or bill |
| `GET /api/products` | Cached catalog |
| `POST /api/products/search` | SSE: `source_started`, `product_found`, `source_failed`, `done` |
| `POST /api/optimize` | Top packages by goal and budget |
| `POST /api/simulate` | Three-scenario `RoiTable` with net metering on and off |
| `GET /api/assumptions` | Every assumption with source and date |
| `POST /api/passport` | Issue a signed Passport |
| `GET /api/passport/{id}` | Fetch a Passport |
| `GET /api/passport/{id}/verify` | Verification result |
| `POST /api/passport/verify` | Paste-to-verify (a changed digit fails) |
| `GET /verify/{id}` | Human-readable verify page |
| `POST /api/agent/chat` | Agent turn over SSE |

## Rules that hold everywhere

- Azimuth: 180 is south (pvlib convention). Tilt is the panel plane tilt.
- Money is PHP. Energy is kWh. System size is kWp.
- Scenario names are `pessimistic`, `expected`, `optimistic`. Cumulative cash flow has 26 values and index 0 is `-capex`.
- Every result is an estimate for a licensed installer to confirm. Demo data is synthetic.
