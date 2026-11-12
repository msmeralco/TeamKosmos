# Sol: Your Clean Energy Partner

Team Kosmos, IDOL Hackathon 2026.

## Run

```
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -r backend/requirements.txt
cd backend && ../.venv/bin/uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```
