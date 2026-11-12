"""Gemini provider: manual function-calling loop with retry, a short response cache and clean failure signals."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import types as pytypes
import typing
from typing import Any, Literal, get_args, get_origin

from ...config import Settings
from . import intake
from .prompt import build_system
from .providers import ProviderUnavailable
from .tools import TOOLS, TurnContext

log = logging.getLogger("sol.gemini")
REQUEST_TIMEOUT_S = 12.0
CACHE_TTL_S = 600.0
CACHE_MAX = 200
RETRY_DELAY_S = 1.5
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _unwrap_optional(ann):
    origin = get_origin(ann)
    if origin in (typing.Union, pytypes.UnionType):
        args = [a for a in get_args(ann) if a is not type(None)]
        return args[0] if len(args) == 1 else ann
    return ann


def schema_for(types, ann, description: str | None):
    ann = _unwrap_optional(ann)
    origin = get_origin(ann)
    kw: dict[str, Any] = {"description": description} if description else {}
    if origin is Literal:
        return types.Schema(type="STRING", enum=[str(a) for a in get_args(ann)], **kw)
    if origin is list:
        inner = _unwrap_optional(get_args(ann)[0]) if get_args(ann) else str
        return types.Schema(type="ARRAY", items=schema_for(types, inner, None), **kw)
    if ann is bool:
        return types.Schema(type="BOOLEAN", **kw)
    if ann is int:
        return types.Schema(type="INTEGER", **kw)
    if ann is float:
        return types.Schema(type="NUMBER", **kw)
    return types.Schema(type="STRING", **kw)


def function_declarations(types) -> list:
    decls = []
    for t in TOOLS.values():
        props, required = {}, []
        for name, field in t.args_model.model_fields.items():
            props[name] = schema_for(types, field.annotation, field.description)
            if field.is_required():
                required.append(name)
        params = types.Schema(type="OBJECT", properties=props, required=required or None) if props else None
        decls.append(types.FunctionDeclaration(name=t.name, description=t.description, parameters=params))
    return decls


def _retryable(exc: Exception) -> bool:
    """Only a rate limit is worth one quick retry. 503s and timeouts already cost 7 to 17 s each, so fail over instead."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code == 429 or "ratelimit" in exc.__class__.__name__.lower()


class _Breaker:
    """After a failure, skip Gemini for a short while so the next messages answer instantly in quick mode."""

    def __init__(self, cooldown_s: float):
        self.cooldown_s = cooldown_s
        self._until = 0.0
        self._lock = threading.Lock()

    def open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._until

    def trip(self) -> None:
        with self._lock:
            self._until = time.monotonic() + self.cooldown_s

    def reset(self) -> None:
        with self._lock:
            self._until = 0.0


_breakers: dict[str, _Breaker] = {}
_breakers_lock = threading.Lock()


def breaker_for(model: str) -> _Breaker:
    with _breakers_lock:
        return _breakers.setdefault(model, _Breaker(cooldown_s=60.0))


def reset_breakers() -> None:
    with _breakers_lock:
        for b in _breakers.values():
            b.reset()


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings, client: Any = None):
        self.settings = settings
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            # A chat turn is capped at 75 s, so never let one request (or the SDK's own retries) eat the budget.
            self._client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT_S * 1000), retry_options=types.HttpRetryOptions(attempts=1)),
            )
        return self._client

    # ---- request building ------------------------------------------------------------------------------------
    @staticmethod
    def _history(types, ctx: TurnContext) -> list:
        contents: list = []
        for h in ctx.session.history[-20:]:
            role = "user" if h["role"] == "user" else "model"
            if contents and contents[-1].role == role:
                contents[-1].parts.append(types.Part(text=h["text"]))
            else:
                contents.append(types.Content(role=role, parts=[types.Part(text=h["text"])]))
        while contents and contents[0].role != "user":
            contents.pop(0)
        return contents

    def _current_user(self, types, ctx: TurnContext):
        parts = [types.Part.from_bytes(data=a.data, mime_type=a.mime) for a in ctx.attachments]
        text = ctx.user_text.strip() or ("(The user attached files without a message.)" if ctx.attachments else "")
        parts.append(types.Part(text=text))
        return types.Content(role="user", parts=parts)

    # ---- generation --------------------------------------------------------------------------------------------
    def _generate(self, contents: list, config) -> Any:
        key = hashlib.sha256((str(config.system_instruction) + "|".join(c.model_dump_json(exclude_none=True) for c in contents)).encode()).hexdigest()
        now = time.monotonic()
        with _cache_lock:
            hit = _cache.get(key)
            if hit and now - hit[0] < CACHE_TTL_S:
                return hit[1]
        models = [self.settings.gemini_model]
        if self.settings.gemini_fallback_model and self.settings.gemini_fallback_model != self.settings.gemini_model:
            models.append(self.settings.gemini_fallback_model)
        last: Exception | None = None
        for model in models:
            breaker = breaker_for(model)
            if breaker.open():
                continue  # this model failed recently: go straight to the next one
            for attempt in range(2):
                try:
                    resp = self.client.models.generate_content(model=model, contents=contents, config=config)
                    breaker.reset()
                    with _cache_lock:
                        if len(_cache) >= CACHE_MAX:
                            _cache.pop(next(iter(_cache)))
                        _cache[key] = (now, resp)
                    return resp
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    if attempt == 0 and _retryable(exc):
                        log.warning("Gemini rate limit on %s; retrying once", model)
                        time.sleep(RETRY_DELAY_S)
                        continue
                    break
            log.warning("Gemini model %s failed (%s)", model, last.__class__.__name__ if last else "?")
            breaker.trip()
        if last is None:
            raise ProviderUnavailable("Gemini recently failed; using quick mode for a minute")
        raise ProviderUnavailable(f"{last.__class__.__name__}: {str(last)[:160]}")

    @staticmethod
    def _text(resp) -> str:
        try:
            return (resp.text or "").strip()
        except Exception:  # noqa: BLE001 - blocked or malformed responses
            return ""

    def run_turn(self, ctx: TurnContext) -> str:
        from google.genai import types

        # A tapped address suggestion is deterministic: look up that candidate's roof instead of letting the
        # model search the address again (which would just show the same list).
        picked = intake.match_choice(ctx.session, ctx.user_text.strip()) if ctx.user_text.strip() else None
        if picked and picked["kind"] == "pick":
            ctx.call_tool("get_building_outline", {"candidate_index": picked["payload"]})

        contents = self._history(types, ctx)
        contents.append(self._current_user(types, ctx))
        extra: dict[str, Any] = {}
        if self.settings.gemini_model.startswith("gemini-3"):
            # Gemini 3 models reason by default and count thinking tokens against the output limit. A chat turn
            # needs speed, so use LOW thinking. Temperature is left at the model default (Google advises against
            # lowering it on Gemini 3). Function-call parts are echoed back unchanged, which keeps thought signatures.
            extra["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")
        else:
            extra["temperature"] = 0.3
        config = types.GenerateContentConfig(
            system_instruction=build_system(ctx),
            tools=[types.Tool(function_declarations=function_declarations(types))],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=4096,
            **extra,
        )
        for _ in range(self.settings.max_tool_calls + 2):
            if ctx.cancelled.is_set():
                return ""
            resp = self._generate(contents, config)
            calls = list(getattr(resp, "function_calls", None) or [])
            if not calls:
                return self._text(resp)
            cands = getattr(resp, "candidates", None) or []
            if not cands or cands[0].content is None:
                return ""
            contents.append(cands[0].content)  # keeps the model's function_call parts (and any signatures)
            response_parts = []
            for fc in calls:
                result = ctx.call_tool(fc.name, dict(fc.args or {}))
                response_parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
            contents.append(types.Content(role="user", parts=response_parts))
            # The state changed: refresh the system instruction so 'next_slot' and 'ask' are current.
            config = config.model_copy(update={"system_instruction": build_system(ctx)})
        return ""  # loop exhausted: the runner falls back to a template built from the tool results


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
    reset_breakers()
