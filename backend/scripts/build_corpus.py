"""Download the pages in data/docs_corpus/sources.yaml into data/docs_corpus/<id>.md (one file per page).

Run from backend/:  python scripts/build_corpus.py [--only id1,id2]
Pages are skipped if robots.txt does not allow them. Review the output before committing: it is public text
quoted for retrieval with a source link, not a substitute for the source.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.scraper import fetch  # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "data" / "docs_corpus"
DROP = ("script", "style", "noscript", "svg", "nav", "footer", "header", "form", "button", "iframe")


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    seen: set[str] = set()
    lines: list[str] = []
    for raw in root.get_text("\n").splitlines():
        line = " ".join(raw.split())
        if len(line) < 3 or (len(line) > 40 and line in seen):  # drop empties and repeated carousel text
            continue
        seen.add(line)
        lines.append(line)
    return "\n\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    only = {x for x in ap.parse_args().only.split(",") if x}
    sources = yaml.safe_load((CORPUS / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    failed = 0
    for s in sources:
        if only and s["id"] not in only:
            continue
        u = urlparse(s["url"])
        try:
            if not fetch.allowed_by_robots(f"{u.scheme}://{u.netloc}", u.path):
                raise fetch.FetchError("robots.txt does not allow this page")
            text = extract_text(fetch.fetch_html(s["url"]))
        except fetch.FetchError as exc:
            print(f"SKIP {s['id']}: {exc}")
            failed += 1
            continue
        meta = {k: s[k] for k in ("title", "publisher", "kind", "region") if k in s}
        meta.update(source_url=s["url"], fetched_at=date.today().isoformat())
        (CORPUS / f"{s['id']}.md").write_text(f"---\n{yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)}---\n\n{text}\n", encoding="utf-8")
        print(f"ok   {s['id']}: {len(text):,} characters")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
