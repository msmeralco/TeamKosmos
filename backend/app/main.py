from fastapi import FastAPI

app = FastAPI(title="Sol")


@app.get("/api/health")
def health():
    return {"status": "ok"}
