"""Local document search (RAG) for the chat agent: facts and citations only, never calculations.

The library is the markdown files in data/docs_corpus/ (see scripts/build_corpus.py). Each file has a
front-matter block (title, publisher, kind, source_url, fetched_at). Files are split into passages and
ranked with BM25 keyword search. shortcut: keyword search only, upgrade to embeddings if questions are
phrased far from the source wording.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import BACKEND_DIR

CORPUS_DIR = Path(BACKEND_DIR) / "data" / "docs_corpus"
MAX_CHARS = 900  # passage size
K1, B = 1.5, 0.75
MIN_SCORE = 5.0  # below this a hit is noise, so the agent should say it has no source
# Local rules beat general background when both match.
KIND_BOOST = {"meralco": 1.5, "policy": 1.5, "installer": 1.2}
# Words people use for what the sources call something else (applied to questions and sources alike).
SYNONYMS = {"blackout": "outage", "brownout": "outage", "price": "cost", "cheaper": "cost", "expensive": "cost", "lifespan": "life", "lifetime": "life", "lose": "degradation", "decline": "degradation", "weaken": "degradation"}
STOP = frozenset("a an and are as at be by can do does for from has have how i if in is it me my of on or so that the to we what when where which who will with you your".split())
_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if w in STOP:
            continue
        w = w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
        out.append(SYNONYMS.get(w, w))
    return out


@dataclass(frozen=True)
class Passage:
    text: str
    meta: dict
    tf: Counter
    length: int


def _split(body: str) -> list[str]:
    parts: list[str] = []
    for para in (p.strip() for p in body.split("\n\n")):
        if not para:
            continue
        if len(para) > MAX_CHARS * 1.4:  # one long block: cut on sentence ends
            parts.extend(re.findall(r".{1,%d}(?:[.!?]\s|$)" % MAX_CHARS, para, flags=re.S))
        else:
            parts.append(para)
    chunks, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > MAX_CHARS:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{p}".strip()
    return chunks + ([cur] if cur else [])


@lru_cache(maxsize=1)
def _index() -> tuple[list[Passage], dict[str, float], float]:
    passages: list[Passage] = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            continue
        _, front, body = raw.split("---", 2)
        meta = yaml.safe_load(front) or {}
        meta["id"] = path.stem
        for text in _split(body):
            toks = tokens(f"{meta.get('title', '')} {text}")
            passages.append(Passage(text, meta, Counter(toks), len(toks)))
    n = len(passages)
    df = Counter(t for p in passages for t in p.tf)
    idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    return passages, idf, (sum(p.length for p in passages) / n if n else 0.0)


def clear_cache() -> None:
    _index.cache_clear()


def search(query: str, k: int = 4, kinds: list[str] | None = None) -> list[dict]:
    """Best passages for the question, each with its source. Empty when nothing matches well."""
    passages, idf, avg = _index()
    q = set(tokens(query))
    scored = []
    for p in passages:
        if kinds and p.meta.get("kind") not in kinds:
            continue
        if sum(t in p.tf for t in q) < min(2, len(q)):  # one shared common word is not a match
            continue
        s = sum(idf[t] * p.tf[t] * (K1 + 1) / (p.tf[t] + K1 * (1 - B + B * p.length / avg)) for t in q if t in p.tf)
        s *= KIND_BOOST.get(p.meta.get("kind"), 1.0)
        if s >= MIN_SCORE:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for s, p in scored:
        if p.text in seen:
            continue
        seen.add(p.text)
        m = p.meta
        out.append({"id": m.get("id", ""), "text": p.text, "title": m.get("title", ""), "publisher": m.get("publisher", ""), "kind": m.get("kind", ""),
                    "region": m.get("region", "PH"), "source_url": m.get("source_url", ""), "fetched_at": str(m.get("fetched_at", "")),
                    "score": round(s, 1)})
        if len(out) == k:
            break
    return out


def library() -> list[dict]:
    """One row per source file, for health checks and the docs."""
    seen: dict[str, dict] = {}
    for p in _index()[0]:
        m = seen.setdefault(p.meta["id"], {"id": p.meta["id"], "title": p.meta.get("title", ""), "kind": p.meta.get("kind", ""), "passages": 0})
        m["passages"] += 1
    return list(seen.values())
