# Sol: Your Clean Energy Partner

Team Kosmos, IDOL Hackathon 2026, Challenge 1.

Sol is an AI agent that helps a Meralco household go solar. You give it your address, your bill, your budget and your goal. Sol measures your roof on a satellite map, compares grid only, solar and solar with a battery over ten years, and picks the parts and an installer that fit. When the install is confirmed, your Solar Passport unlocks vouchers and discounts.

## Run the app

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node.js.

1. Start the backend from the repo root. It runs on port 8000.

```
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -r backend/requirements.txt
cd backend
cp .env.example .env    # fill in GEMINI_API_KEY and CONTACT_EMAIL (see backend/README.md)
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

2. In a second terminal, start the frontend. It proxies `/api` to the backend.

```
cd frontendv2
npm install
npm run dev
```

3. Open the address that Vite prints, usually http://localhost:5173.

On Windows, use the PowerShell commands in `backend/README.md`. Without a Gemini key the backend falls back to a rule-based agent.

## Run the pitch deck

```
cd deck
./start.command
```

The deck is a 3D voxel street. It opens in the browser, and the arrow keys move between slides. See `deck/README.md` for the controls.

## Docs

The plan, the pitch script and the Q&A guide are in `docs/`.
