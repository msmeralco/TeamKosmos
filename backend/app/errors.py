"""Uniform error shape: {"detail": {"code", "message", "hint"}}."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, code: str, message: str, *, hint: str = "", status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status


def error_body(code: str, message: str, hint: str = "") -> dict:
    return {"detail": {"code": code, "message": message, "hint": hint}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(error_body(exc.code, exc.message, exc.hint), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = f"{loc}: {first.get('msg', 'invalid request')}" if loc else "invalid request"
        return JSONResponse(error_body("invalid_request", msg, "Check the request fields."), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):  # pragma: no cover - last resort
        return JSONResponse(error_body("internal_error", "Something went wrong on the server."), status_code=500)
