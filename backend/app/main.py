from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import db_status
from .errors import install_error_handlers
from .routes import agent, auth, engine, passport, roof

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Sol", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for r in (auth.router, agent.router, roof.router, engine.router, passport.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        s = get_settings()
        return {
            "status": "ok",
            "db": db_status(),
            "llm": {
                "configured": s.llm_configured,
                "model": s.gemini_model if s.llm_configured else None,
                "mode": "gemini" if s.llm_configured else "scripted",
            },
            "pvgis_live": s.pvgis_live,
            "contact_email_is_placeholder": s.contact_email.endswith("@example.com"),
        }

    return app


app = create_app()
