"""One reply layout for every answer Sol gives, whichever agent wrote it (Gemini, scripted, or the fallback).

The layout, top to bottom (the frontend's RichText turns it into styled blocks):

    **Lead sentence with the key point.**         short paragraph(s), key terms in bold
    - detail                                       bullet list when there are three or more points
    > Source: [Name](https://...)                  sources and caveats, shown as a muted note
    **The one question for the user?**             last, on its own line, in bold

`tidy()` only fixes layout (blank lines, sources, closing question). It never changes a number or a word.
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


def tidy(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return text
    if "\n" not in text and len(text) >= LONG_BLOCK:
        text = split_paragraphs(text)
    lines = _sources_as_notes(text.split("\n"))
    lines = _separate_blocks(lines)
    blocks = "\n".join(lines).split("\n\n")
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


def shorten(sentence: str, limit: int = 220) -> str:
    s = sentence.strip()
    if len(s) <= limit:
        return s if s.endswith((".", "!", "?", "…")) else s + "."
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


__all__ = ["tidy", "split_paragraphs", "clean_passage", "shorten"]
