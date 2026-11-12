# Sol backend

FastAPI service for Sol, the Meralco solar advisor (Team Kosmos, IDOL Hackathon 2026, Challenge 1). Frontend contract: [`docs/agent-contract.md`](docs/agent-contract.md).

## Run (Windows PowerShell, from the repo root)

```powershell
uv venv --python 3.12 .venv
uv pip install -p .venv\Scripts\python.exe -r backend\requirements.txt
cd backend
Copy-Item .env.example .env        # then fill in the values below
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

`GET http://127.0.0.1:8000/api/health` shows which database and which agent mode are active. API docs: `/docs`.

## Configuration (`backend/.env`, never committed)

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini for the chat agent. Run `python scripts/verify_gemini.py` to find a model that supports image input and function calling on your key. Without a key the rule-based agent answers. |
| `DATABASE_URL`, `DB_BACKEND` | Supabase Postgres (use the **session pooler** URI). `auto` falls back to local SQLite if Supabase is unreachable. Apply the schema with `python -m app.db.migrate` (or paste `migrations/001_init.sql` in the Supabase SQL editor). |
| `CONTACT_EMAIL` | **Set a real address.** Nominatim answers 403 to the placeholder, so address search fails until you do. |
| `PVGIS_LIVE` | `1` fetches PVGIS-ERA5 for locations not in `data/pvgis_bundled` (can take up to 35 s, then falls back to a labelled approximation). |
| `AGENT_MODE` | `scripted` forces the rule-based agent even when a key is set. |

## Useful scripts (from `backend/`)

- `python scripts/demo_run.py` runs the three demo households end to end and prints a table. Add `--base-url http://127.0.0.1:8000` to hit a running server.
- `python scripts/agent_chat.py` chats with Sol in the terminal.
- `python scripts/prefetch_pvgis.py [--tilt 12]` pre-downloads PVGIS data for offline demos (already bundled for the three personas at 12 and 20 degrees, facing south).
- `python scripts/build_demo_outlines.py --name ... --address ...` builds `data/demo_outlines.geojson` from real OpenStreetMap outlines. The shipped file holds **synthetic** rectangles.

## Tests

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

Tests run offline against a temporary SQLite database. Live checks are marked `live` and need `RUN_LIVE=1`.

## Data honesty

- Households, demo roofs and the product catalog (`data/seed_catalog.csv`) are **synthetic**.
- `ASSUMPTIONS.yaml` lists every number with unit, source and date. Entries with `verified: false` are placeholders or judgement and must be replaced with sourced values before real use. The agent says so when they drive a result.
- Sunlight data is PVGIS-ERA5 (a modelled dataset). The scraper has no enabled retailer: add hand-checked sources in `app/services/scraper/sources.yaml` after reading each site's robots.txt and terms.
