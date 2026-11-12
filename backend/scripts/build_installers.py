"""Build data/doe_installers.json from the DOE Official Solar PV Installer Registry PDFs.

Usage (from backend/):  python scripts/build_installers.py [--print]
Needs poppler's `pdftotext` on the PATH (brew install poppler). Run it again when the DOE publishes a new list
(edit LISTS). Contact details are the business contacts the DOE itself publishes in the registry.
shortcut: reads the PDF text layout and word positions, so re-check the printed sample after each run.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND / "data" / "doe_installers.json"
LISTS = [  # (label, as-of date, PDF url)
    ("Jan 31, 2026", "2026-01-31", "https://prod-cms.doe.gov.ph/documents/d/eumb/list-of-solar-pv-installer-registry-as-of-31-january-2026-pdf"),
    ("Jul 13, 2026", "2026-07-13", "https://d24qbtp4vooyzi.cloudfront.net/api/media/file/Official%20DOE%20Solar%20PV%20Installer%20Registry%20as%20of%2013%20July%202026.pdf?prefix=dev%2Fmedia"),
]
REGION_RE = re.compile(r"^(NCR|CAR|BARMM|I|II|III|IV-A|IV-B|V|VI|VII|VIII|IX|X|XI|XII|XIII)$")
HEADER_WORDS = {"Company", "Address", "Telephone", "/", "Contact", "Number", "E-Mail", "Email", "Website", "Classification", "Name", "Business", "Type", "of", "Region"}
WEB_RE = re.compile(r"^(https?://|www\.|[\w.-]+\.(?:com|ph|net|org)\b)", re.I)


def run_pdftotext(pdf: Path, mode: str) -> str:
    out = Path(tempfile.mkdtemp()) / "o.txt"
    subprocess.run(["pdftotext", mode, str(pdf), str(out)], check=True)
    return out.read_text(encoding="utf-8")


def layout_rows(text: str) -> list[dict]:
    """Name, business type and region per record, from the fixed-width text layout."""
    lines = text.splitlines()
    start = [i for i, l in enumerate(lines) if re.match(r"\s*\d{1,3}\s{3,}\S", l)]
    groups, cur = [], []
    for i in start:
        if cur and int(re.match(r"\s*(\d+)", lines[i]).group(1)) == 1:
            groups.append(cur)
            cur = []
        cur.append(i)
    groups.append(cur)
    rows = []
    for gi, idx in enumerate(groups):
        cells = [(m.start(), m.group()) for m in re.finditer(r"\S+(?: \S+)*", lines[idx[0]])]
        type_s, name_s, region_s = cells[1][0], cells[2][0], cells[3][0]
        lo = idx[0] - 3
        hi = groups[gi + 1][0] - 6 if gi + 1 < len(groups) else len(lines)
        recs = {i: {"type": [], "name": [], "region": []} for i in idx}
        for j in range(max(lo, 0), hi):
            l = lines[j]
            if not l.strip() or re.search(r"Official DOE|updated as of|The Official|shall undergo|Republic of|Department of Energy|Kagawaran|^\s*No\s", l):
                continue
            near = min(idx, key=lambda i: (abs(i - j), i))
            if abs(near - j) > 2:
                continue
            l = l.ljust(260)
            recs[near]["type"].append(l[type_s - 1:name_s - 1].strip())
            recs[near]["name"].append(l[name_s - 1:region_s - 1].strip())
            recs[near]["region"].append(l[region_s - 1:region_s + 7].strip())
        for i in idx:
            r = recs[i]
            rows.append({"no": int(re.match(r"\s*(\d+)", lines[i]).group(1)), "table": gi,
                         "name": " ".join(x for x in r["name"] if x),
                         "type": re.sub(r"Sole\s*P+roprietor\w*", "Sole Proprietorship", " ".join(x for x in r["type"] if x)),
                         "region": " ".join(x for x in r["region"] if x)})
    return rows


def _merge_pieces(pieces: list[str], kind: str) -> list[str]:
    """Rejoin values the PDF wrapped across lines."""
    out: list[str] = []
    for p in pieces:
        if p in ("/", ",", ";"):
            continue
        prev = out[-1] if out else ""
        wrapped_email = prev and ("@" in prev and ("." not in prev.split("@", 1)[1]) or prev.endswith("@"))
        wrapped_url = prev and (re.search(r"[-/.]$", prev) or p.startswith(".")) and not WEB_RE.match(p)
        if kind == "web" and prev == "www":
            out[-1] = prev + "." + p  # the PDF drops this dot
        elif kind == "email" and wrapped_email or kind == "web" and wrapped_url:
            out[-1] = prev + p
        else:
            out.append(p)
    return out


def bbox_contacts(text: str) -> list[dict]:
    """Address, phones, emails and website per record, read by word position (columns are left aligned)."""
    records: list[dict] = []
    table, seen, cols = -1, False, {}
    for page in re.split(r"<page ", text)[1:]:
        words = [(float(a), float(b), float(c), float(d), html.unescape(t))
                 for a, b, c, d, t in re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', page)]
        nums = [w for w in words if re.fullmatch(r"\d{1,3}", w[4]) and w[0] < 110]
        if not nums:
            continue
        no_x = min(w[0] for w in nums)
        recs = sorted((w for w in nums if abs(w[0] - no_x) < 8), key=lambda w: w[1])
        regions = [w for w in words if REGION_RE.match(w[4]) and 190 < w[0] < 240 and w[1] >= recs[0][1] - 6]
        if regions:
            cols["region_end"] = max(w[2] for w in regions)
        emails = [w for w in words if "@" in w[4]]
        if emails:
            cols["email"] = min(w[0] for w in emails) - 3
        webs = [w for w in words if WEB_RE.match(w[4]) and "@" not in w[4] and w[0] > cols.get("email", 500) + 40]
        webs += [w for w in words if w[4] == "N/A" and w[0] > cols.get("email", 500) + 40]
        if webs:
            cols["web"] = min(w[0] for w in webs) - 3
        cols["phone"] = cols["email"] - 95  # phones are centered in their column, so measure from the email column
        ys = [r[1] for r in recs]
        for k, rec in enumerate(recs):
            if rec[4] == "1" and seen:
                table += 1
            elif rec[4] == "1":
                table, seen = 0, True
            starts_table = rec[4] == "1"  # a table title and header row sit above its first record
            top = rec[1] - 14 if k == 0 or starts_table else (ys[k - 1] + rec[1]) / 2
            bot = rec[1] + 45 if k == len(recs) - 1 else (ys[k + 1] - 28 if recs[k + 1][4] == "1" else (rec[1] + ys[k + 1]) / 2)
            band = sorted((w for w in words if top <= w[1] < bot and w[0] > no_x + 8 and not (starts_table and w[4] in HEADER_WORDS and w[1] < rec[1] - 2)),
                          key=lambda w: (round(w[1] / 4), w[0]))
            addr = [w[4] for w in band if cols["region_end"] + 2 <= w[0] < cols["phone"] - 3]
            phone = [w[4] for w in band if cols["phone"] <= w[0] < cols["email"] and not w[4].endswith(",")]  # a trailing comma means the address ran over
            mail = [w[4] for w in band if cols["email"] <= w[0] < cols["web"]]
            web = [w[4] for w in band if w[0] >= cols["web"]]
            phones = re.split(r"\s*/\s*", " ".join(phone).strip(" /"))
            phones = [p.strip("' ") for p in phones]
            records.append({
                "table": table, "no": int(rec[4]),
                "address": re.sub(r"\s*\b0?\d{9,11}\b", "", " ".join(addr)).strip(),  # a neighbouring phone number can spill into the address
                "phones": [p for p in phones if re.fullmatch(r"[+()\d][\d\s()+\-.]*", p) and sum(c.isdigit() for c in p) >= 7],
                "emails": [e for e in _merge_pieces(mail, "email") if "@" in e],
                "website": next((u for u in _merge_pieces(web, "web") if u != "N/A"), ""),
            })
    return records


def parse_pdf(pdf: Path) -> list[dict]:
    rows = layout_rows(run_pdftotext(pdf, "-layout"))
    contacts = bbox_contacts(run_pdftotext(pdf, "-bbox"))
    if [(r["table"], r["no"]) for r in rows] != [(c["table"], c["no"]) for c in contacts]:
        raise SystemExit(f"{pdf.name}: layout rows and word-position records do not line up ({len(rows)} vs {len(contacts)})")
    return [{**r, **c} for r, c in zip(rows, contacts)]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> int:
    firms: dict[str, dict] = {}
    meta = []
    for label, as_of, url in LISTS:
        pdf = Path(tempfile.mkdtemp()) / "registry.pdf"
        r = httpx.get(url, follow_redirects=True, timeout=60, headers={"User-Agent": "Sol-Hackathon/1.0"})
        r.raise_for_status()
        pdf.write_bytes(r.content)
        recs = parse_pdf(pdf)
        meta.append({"label": label, "as_of": as_of, "url": url, "installers": sum(1 for x in recs if x["table"] == 0), "escos": sum(1 for x in recs if x["table"] == 1)})
        for x in recs:  # newest list wins for details; each firm remembers which lists it is on
            f = firms.setdefault(norm(x["name"]), {"lists": []})
            f.update({k: x[k] for k in ("name", "type", "region", "address", "phones", "emails", "website")}, esco=x["table"] == 1)
            f["lists"].append(label)
    sites: dict[str, list[dict]] = {}
    for f in firms.values():
        if f["website"]:
            sites.setdefault(f["website"].lower().rstrip("/"), []).append(f)
    for group in sites.values():
        if len(group) > 1:  # the registry repeats one URL for different firms, so it cannot be trusted for either
            for f in group:
                f["website"] = ""
    data = {"source": "DOE Official Solar PV Installer Registry",
            "disclaimer": "The DOE publishes this registry as a reference for government entities and states that it does not endorse any listed firm.",
            "lists": meta, "firms": sorted(firms.values(), key=lambda f: f["name"].lower())}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(BACKEND)}: {len(data['firms'])} firms from {[(m['label'], m['installers'], m['escos']) for m in meta]}")
    if "--print" in sys.argv:
        for f in data["firms"]:
            print(f"{f['region']:5} {f['name'][:42]:42} | {f['address'][:46]:46} | {'; '.join(f['phones'])[:28]:28} | {'; '.join(f['emails'])[:34]:34} | {f['website'][:34]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
