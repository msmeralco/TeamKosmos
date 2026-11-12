"""One reply layout for every answer Sol gives, whichever agent wrote it (Gemini, scripted, or the fallback).

The layout depends on what the user asked (see `detect_intent`), not one template for everything:

    steps    "How do I apply...?"        numbered list, one step per line
    yesno    "Can I add a battery?"      the answer first, in bold, then one or two sentences. No bullets
    cost     "How much is the fee?"      the figure first, in bold, then a short note
    compare  "X vs Y", "difference"      bullets, one point per side
    explain  "What is net metering?"     bold definition, then short bullets
    chat     the user gave an answer     a plain, short acknowledgement, then the bold question

Every layout can end with a "> Source: ..." note and a bold closing question. `tidy()` only fixes layout
(blank lines, lists, sources, closing question). It never changes a number or a word.
"""
from __future__ import annotations

import re

_INTENTS: list[tuple[str, re.Pattern]] = [
    ("cost", re.compile(r"\b(how much|cost|costs|fee|fees|price|prices|pay|charge|rate)\b", re.I)),
    ("steps", re.compile(r"\b(how (do|can|should) (i|we)|how to|steps?|process|procedure|requirements?|what do i need)\b", re.I)),
    ("compare", re.compile(r"\b(vs\.?|versus|difference|differences|compare|compared|comparison|better than)\b", re.I)),
    ("yesno", re.compile(r"^\s*(can|could|do|does|did|is|are|am|will|would|should|may|must|need|allowed)\b", re.I)),
    ("explain", re.compile(r"\b(what('s| is| are| does)|why|explain|tell me (about|more)|meaning of|warranty|degradation|lifespan)\b", re.I)),
]


def detect_intent(user_text: str | None) -> str:
    """Pick the reply shape from what the user wrote. 'chat' is the default: a plain, short conversational reply."""
    t = (user_text or "").strip()
    if not t:
        return "chat"
    is_question = t.endswith("?") or bool(re.match(r"^(how|what|why|can|could|do|does|is|are|will|should|which|who|where|when|tell|explain|compare)\b", t, re.I))
    if not is_question:
        return "chat"  # the user is giving details (a bill, a budget, a choice), not asking
    for name, pat in _INTENTS:
        if pat.search(t):
            return name
    return "explain"

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
    """A wall of text becomes short paragraphs (two or three sentences each); a closing question gets its own."""
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


def _bold_closing_question(blocks: list[str]) -> list[str]:
    """The user's one question goes last and in bold, so it is easy to spot."""
    if len(blocks) < 2:
        return blocks
    last = blocks[-1]
    if (_kind(last.split("\n")[0]) == "para" and "\n" not in last and last.endswith("?") and "*" not in last
            and len(last) <= 200 and not _SENTENCE_END.search(last)):
        return [*blocks[:-1], f"**{last}**"]
    return blocks


def _number_list(blocks: list[str]) -> list[str]:
    """Steps read best as 1, 2, 3: turn a bullet list into a numbered one."""
    out = []
    for b in blocks:
        lines = b.split("\n")
        if all(re.match(r"^\s*[-*•]\s+", ln) for ln in lines):
            b = "\n".join(f"{i}. " + re.sub(r"^\s*[-*•]\s+", "", ln) for i, ln in enumerate(lines, 1))
        out.append(b)
    return out


def _bold_answer(blocks: list[str]) -> list[str]:
    """Yes/no and cost answers lead with the answer itself in bold (first sentence of the first paragraph)."""
    if not blocks or _kind(blocks[0].split("\n")[0]) != "para" or "*" in blocks[0].split("\n")[0]:
        return blocks
    first = blocks[0].split("\n")
    parts = _SENTENCE_END.split(first[0], maxsplit=1)
    head = f"**{parts[0].strip()}**" + (f" {parts[1]}" if len(parts) > 1 else "")
    return [head + ("\n" + "\n".join(first[1:]) if len(first) > 1 else ""), *blocks[1:]]


def tidy(text: str, intent: str = "chat") -> str:
    """Fix the layout of a reply. `intent` (from detect_intent) decides the shape, so replies are not all alike."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return text
    if "\n" not in text and (len(text) >= LONG_BLOCK or (intent != "chat" and text.endswith("?") and _SENTENCE_END.search(text))):
        text = split_paragraphs(text)
    lines = _sources_as_notes(text.split("\n"))
    lines = _separate_blocks(lines)
    blocks = "\n".join(lines).split("\n\n")
    if intent == "steps":
        blocks = _number_list(blocks)
    elif intent in ("yesno", "cost"):
        blocks = _bold_answer(blocks)
    return "\n\n".join(_bold_closing_question(blocks))


# ---- cleaning scraped passages for display ----------------------------------------------------------------------
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
    return " ".join(kept).strip()


def passage_answer(points: list[str], who: str, us: str, url: str, intent: str) -> str:
    """A document answer shaped by the question: steps, a direct answer, a comparison, or an explanation."""
    note = f"> Source: [{who}]({url})" if url else ""
    if intent == "steps":
        body = "\n".join(f"{i}. {p}" for i, p in enumerate(points[:5], 1))
        head = f"Here is the process according to **{who}**{us}:"
    elif intent in ("yesno", "cost"):
        lead = points[0] if len(points[0]) <= 160 else ""
        rest = " ".join(points[1:2] if lead else points[:2])
        body = f"**{lead}** {rest}".strip() if lead else rest
        head = "This is a US example, not Philippine rules." if us else ""
    elif intent == "compare":
        body = "\n".join(f"- {p}" for p in points[:4])
        head = f"The main points from **{who}**{us}:"
    else:  # explain / chat: a bold lead, then the supporting detail
        short = len(points[0]) <= 160
        more = "\n".join(f"- {p}" for p in points[1:3])
        body = f"**{points[0]}**\n\n{more}".strip() if short else "\n".join(f"- {p}" for p in points[:3])
        head = f"From **{who}**{us}:" if us else ""
    return "\n\n".join(x for x in (head, body, note) if x)


def shorten(sentence: str, limit: int = 220) -> str:
    s = sentence.strip()
    if len(s) <= limit:
        return s if s.endswith((".", "!", "?", "…")) else s + "."
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


__all__ = ["tidy", "split_paragraphs", "clean_passage", "shorten"]
