"""Check that your Gemini key works with image input AND function calling together.

Usage (from backend/):  python scripts/verify_gemini.py [model ...]
Prints PASS/FAIL per model. Sends only a tiny synthetic image. Resolves the [VERIFY] items in the plan.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

# 1x1 red PNG: enough to prove the image part is accepted.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

CANDIDATES = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-flash-latest"]


def try_model(client, types, model: str) -> tuple[bool, str]:
    tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="report_color",
                description="Report the dominant color of the attached image.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"color": types.Schema(type=types.Type.STRING)},
                    required=["color"],
                ),
            )
        ]
    )
    try:
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=PNG_1X1, mime_type="image/png"),
                "What color is this image? Call report_color with your answer.",
            ],
            config=types.GenerateContentConfig(
                tools=[tool],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {str(exc)[:200]}"
    calls = resp.function_calls or []
    if calls and calls[0].name == "report_color":
        return True, f"function call args={dict(calls[0].args or {})}"
    return False, f"no function call returned (text={str(resp.text)[:80]!r})"


def main() -> int:
    s = get_settings()
    if not s.gemini_api_key:
        print("SKIP: GEMINI_API_KEY is not set in backend/.env")
        return 2
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=s.gemini_api_key)
    models = sys.argv[1:] or [s.gemini_model] + [m for m in CANDIDATES if m != s.gemini_model]
    ok_any = False
    for model in models:
        ok, detail = try_model(client, types, model)
        print(f"{'PASS' if ok else 'FAIL'}  {model}: {detail}")
        ok_any = ok_any or ok
        if ok:
            print(f"\nSet GEMINI_MODEL={model} in backend/.env")
            break
    return 0 if ok_any else 1


if __name__ == "__main__":
    sys.exit(main())
