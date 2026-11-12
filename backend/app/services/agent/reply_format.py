"""Light layout clean-up for Sol's replies. It does not decide how an answer is shaped.

How a reply is shaped is the model's job, guided by the "How to answer" section of prompt.py. This module only
repairs layout problems that make rich text look broken, and it never changes a word or a number:

- a wall of text with no line breaks is split into short paragraphs
- blocks of different kinds (paragraph, list, table, note, heading) get a blank line between them
- a "Source:" line becomes a muted note
- a closing question that is stuck to the end of a paragraph moves to its own paragraph

`detect_intent` and `passage_answer` are used only by the scripted fallback agent (no LLM), which has no judgement of
its own, so it picks one of a few shapes from the user's wording.
"""
from __future__ import annotations

import re

_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_ROW = re.compile(r"^\s*\|.*\|\s*$")
_HEAD = re.compile(r"^\s{0,3}#{1,4}\s+")
_QUOTE = re.compile(r"^\s*>")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(*\[])")
LONG_BLOCK = 220  # a single unbroken paragraph longer than this gets split
PARA_MAX = 240


def _kind(line: str) -> str:
    if not line.strip():
        return "blank"
    if _ROW.match(line):
        return "table"
    if _HEAD.match(line):
        return "head"
    if _QUOTE.match(line):
        return "quote"
    if _ITEM.match(line):
        return "list"
    return "para"


def split_paragraphs(text: str) -> str:
    """A wall of text becomes short paragraphs; a closing question gets its own."""
    sents = _SENTENCE_END.split(text.strip())
    out: list[str] = []
    cur = ""
    for i, s in enumerate(sents):
        closing_question = i == len(sents) - 1 and len(sents) > 1 and s.rstrip("*").endswith("?")
        if cur and (closing_question or len(cur) + 1 + len(s) > PARA_MAX):
            out.append(cur)
            cur = ""
        cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return "\n\n".join(out)


def _separate_blocks(lines: list[str]) -> list[str]:
    """Blank line between blocks of a different kind (paragraph, list, table, note, heading)."""
    out: list[str] = []
    prev = "blank"
    for line in lines:
        k = _kind(line)
        if k == "blank":
            if out and out[-1] != "":
                out.append("")
            prev = "blank"
            continue
        if prev not in ("blank", k) or (k == "head" and prev != "blank"):
            out.append("")
        out.append(line.rstrip())
        prev = k
    while out and out[-1] == "":
        out.pop()
    return out


def _sources_as_notes(lines: list[str]) -> list[str]:
    return [f"> {ln.strip()}" if re.match(r"^\s*Sources?:\s", ln) else ln for ln in lines]


def tidy(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return text
    one_line = "\n" not in text
    if one_line and (len(text) >= LONG_BLOCK or (text.endswith("?") and _SENTENCE_END.search(text))):
        text = split_paragraphs(text)
    lines = _sources_as_notes(text.split("\n"))
    return "\n".join(_separate_blocks(lines))


# ---- scripted fallback only --------------------------------------------------------------------------------------
_INTENTS: list[tuple[str, re.Pattern]] = [
    ("cost", re.compile(r"\b(how much|cost|costs|fee|fees|price|prices|pay|charge|rate)\b", re.I)),
    ("steps", re.compile(r"\b(how (do|can|should) (i|we)|how to|steps?|process|procedure|requirements?|what do i need)\b", re.I)),
    ("compare", re.compile(r"\b(vs\.?|versus|difference|differences|compare|compared|comparison|better than)\b", re.I)),
    ("yesno", re.compile(r"^\s*(can|could|do|does|did|is|are|am|will|would|should|may|must|need|allowed)\b", re.I)),
]


def detect_intent(user_text: str | None) -> str:
    """Rough kind of question, for the scripted agent only: steps, cost, compare, yesno, explain or chat."""
    t = (user_text or "").strip()
    if not t:
        return "chat"
    is_question = t.endswith("?") or bool(re.match(r"^(how|what|why|can|could|do|does|is|are|will|should|which|who|where|when|tell|explain|compare)\b", t, re.I))
    if not is_question:
        return "chat"
    for name, pat in _INTENTS:
        if pat.search(t):
            return name
    return "explain"


_JUNK = re.compile(
    r"(all rights reserved|©|privacy policy|powered by|cookie|subscribe|sign up for|follow us|ICP备|沪ICP|terms of (use|service)|"
    r"\bdownload more\b|\blearn more\b|\bread more\b|\bclick here\b)", re.I)


def clean_passage(text: str) -> str:
    """Remove web-page leftovers (menus, 'Learn more', copyright lines) from a scraped passage."""
    t = re.sub(r"\b(Learn more|Read more|Download more|Click here)\b", ". ", text, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+\.", ".", t)
    t = re.sub(r"(?:\.\s*){2,}", ". ", t)
    kept = [s for s in _SENTENCE_END.split(t) if s.strip() and not _JUNK.search(s)]
    return " ".join(kept).strip().lstrip(":;,.-– ").strip()


def short_source(name: str) -> str:
    """'Rappler (news summary of the DOE circular); Meralco FAQ confirms the details' -> 'Rappler'."""
    n = re.split(r"\s*[;(]\s*", name.strip(), maxsplit=1)[0].strip(" :,-")
    return n or name.strip()


def passage_answer(points: list[str], who: str, us: str, url: str, intent: str) -> str:
    """Scripted answer from a document, shaped by the kind of question."""
    note = f"> Source: [{who}]({url})" + (" (a US example, not Philippine rules)" if us else "") if url else ""
    if intent == "steps":
        body = "\n".join(f"{i}. {p}" for i, p in enumerate(points[:5], 1))
    elif intent in ("yesno", "cost"):
        body = " ".join(points[:2])
    else:
        body = "\n".join(f"- {p}" for p in points[:3]) if len(points) > 2 else " ".join(points)
    return "\n\n".join(x for x in (body, note) if x)


def shorten(sentence: str, limit: int = 220) -> str:
    s = sentence.strip()
    if len(s) <= limit:
        return s if s.endswith((".", "!", "?", "…")) else s + "."
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


__all__ = ["tidy", "split_paragraphs", "clean_passage", "short_source", "passage_answer", "detect_intent", "shorten"]
