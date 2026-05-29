#!/usr/bin/env python3
"""Acquire original PDFs for the top-K papers in a merged corpus.

Reads corpus.json (output of merge_corpus.py) and tries, per paper, the free/legal
acquisition routes in order, stopping at the first that yields a real PDF:

    1. pdf_url field           (open-access PDF already known)
    2. arXiv                   (https://arxiv.org/pdf/<id>) when arxiv_id present
    3. Unpaywall OA API        (DOI -> best OA location) using --email

Downloads land in OUT_DIR/ as <NN>_<slug>.pdf. Writes OUT_DIR/manifest.json recording,
per paper, the route used or the reason it failed. Stdlib only — runs on system python3.

Papers with NO free route here (closed-access, no OA copy) are listed in the manifest
with status "needs_mcp": the calling agent should fetch those via the session MCP tools
(paper-search-mcp.download_with_fallback / download_scihub / source-specific download_*),
which is the route a standalone script cannot reach.

Usage:
    fetch_pdfs.py corpus.json -o ./run/pdfs --email you@example.com --top 25
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = "scholar-megasearch/1.0 (mailto:%s)"
TIMEOUT = 45


def slug(rec, i):
    base = rec.get("title") or rec.get("doi") or rec.get("arxiv_id") or f"paper{i}"
    s = re.sub(r"[^a-z0-9]+", "-", str(base).lower()).strip("-")
    return f"{i:02d}_{s[:60]}"


def _get(url, email, binary=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA % email})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
    return data, ctype


def _is_pdf(data, ctype):
    return data[:5] == b"%PDF-" or "application/pdf" in (ctype or "").lower()


def _save(data, path):
    with open(path, "wb") as f:
        f.write(data)


def try_pdf_url(rec, email):
    url = rec.get("pdf_url")
    if not url:
        return None, None
    data, ctype = _get(url, email)
    return (data, "pdf_url") if _is_pdf(data, ctype) else (None, None)


def try_arxiv(rec, email):
    aid = rec.get("arxiv_id")
    if not aid:
        return None, None
    aid = re.sub(r"^arxiv:", "", str(aid), flags=re.IGNORECASE).rsplit("/", 1)[-1]
    data, ctype = _get(f"https://arxiv.org/pdf/{aid}", email)
    return (data, "arxiv") if _is_pdf(data, ctype) else (None, None)


def try_unpaywall(rec, email):
    doi = rec.get("doi")
    if not doi:
        return None, None
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", str(doi).strip().lower())
    api = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
    try:
        meta, _ = _get(api, email, binary=False)
        info = json.loads(meta)
    except Exception:  # noqa: BLE001
        return None, None
    loc = info.get("best_oa_location") or {}
    url = loc.get("url_for_pdf") or loc.get("url")
    if not url:
        return None, None
    try:
        data, ctype = _get(url, email)
    except Exception:  # noqa: BLE001
        return None, None
    return (data, "unpaywall") if _is_pdf(data, ctype) else (None, None)


ROUTES = [try_pdf_url, try_arxiv, try_unpaywall]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus")
    ap.add_argument("-o", "--out", default="./pdfs")
    ap.add_argument("--email", default=os.environ.get("PAPER_SEARCH_MCP_UNPAYWALL_EMAIL", ""),
                    help="contact email for arXiv/Unpaywall politeness + OA lookup")
    ap.add_argument("--top", type=int, default=25, help="acquire PDFs for the top-N ranked papers")
    args = ap.parse_args()
    if not args.email:
        sys.exit("--email is required (or set PAPER_SEARCH_MCP_UNPAYWALL_EMAIL)")

    with open(args.corpus, encoding="utf-8") as f:
        corpus = json.load(f)
    papers = corpus[: args.top]
    os.makedirs(args.out, exist_ok=True)

    manifest = []
    ok = 0
    for i, rec in enumerate(papers, 1):
        name = slug(rec, i)
        entry = {"i": i, "title": rec.get("title"), "doi": rec.get("doi"),
                 "arxiv_id": rec.get("arxiv_id")}
        got = False
        for route in ROUTES:
            try:
                data, used = route(rec, args.email)
            except Exception as e:  # noqa: BLE001
                continue
            if data:
                path = os.path.join(args.out, name + ".pdf")
                _save(data, path)
                entry.update(status="ok", route=used, file=path, bytes=len(data))
                ok += 1
                got = True
                print(f"  [{i:02d}] ok via {used:10s} {name}.pdf ({len(data)//1024} KB)", file=sys.stderr)
                break
        if not got:
            entry["status"] = "needs_mcp"  # no free route; use session MCP download tools
            print(f"  [{i:02d}] needs_mcp  {(rec.get('title') or '')[:60]}", file=sys.stderr)
        manifest.append(entry)

    mpath = os.path.join(args.out, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    need = sum(1 for m in manifest if m["status"] == "needs_mcp")
    print(f"\n  acquired {ok}/{len(papers)} PDFs; {need} need MCP fallback. manifest: {mpath}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
