#!/usr/bin/env python3
"""Acquire original PDFs for the top-K papers in a merged corpus.

Reads corpus.json (output of merge_corpus.py) and tries, per paper, the free/legal
acquisition routes in order, stopping at the first that yields a real PDF:

    1. pdf_url field           (open-access PDF already known)
    2. arXiv                   (https://arxiv.org/pdf/<id>) when arxiv_id present
    3. Unpaywall OA API        (DOI -> best OA location) using --email
    4. Temporary browser       (DOI -> entitled publisher PDF) on the current LAN/VPN

Downloads land in OUT_DIR/ as <NN>_<slug>.pdf. Writes OUT_DIR/manifest.json recording,
per paper, the route used or the classified reason it failed. The OA routes remain
stdlib-only. The browser fallback lazily imports Playwright and uses a disposable profile;
run with the installed host skill venv for the fully automatic path.

Usage:
    fetch_pdfs.py corpus.json -o ./run/pdfs --email you@example.com --top 25
    --top accepts a number (top-N ranked) or 'all' (or '0') for the entire corpus.
    Add --retry-unresolved after moving onto an entitled campus/VPN network.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from browser_acquire import BrowserAcquirer, BrowserResult, is_pdf_bytes, normalize_doi

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
    del ctype  # MIME headers are advisory; only the PDF signature is trusted.
    return is_pdf_bytes(data)


def _save(data, path):
    partial = path + ".part"
    with open(partial, "wb") as f:
        f.write(data)
    os.replace(partial, path)


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
    api = (
        f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}"
        f"?email={urllib.parse.quote(email)}"
    )
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


ROUTES = [
    ("pdf_url", try_pdf_url),
    ("arxiv", try_arxiv),
    ("unpaywall", try_unpaywall),
]


def _existing_manifest(path):
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _record_key(row, fallback_rank=None):
    doi = normalize_doi(row.get("doi")).lower()
    if doi:
        return ("doi", doi)
    arxiv_id = str(row.get("arxiv_id") or "").strip().lower()
    if arxiv_id:
        return ("arxiv", arxiv_id)
    title = " ".join(str(row.get("title") or "").lower().split())
    if title:
        return ("title", title)
    return ("rank", str(row.get("rank", row.get("i", fallback_rank))))


def _existing_file(entry):
    path = entry.get("file")
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as f:
            return is_pdf_bytes(f.read(1024))
    except OSError:
        return False


def _browser_failure(status, detail=None):
    return {"status": status, **({"detail": detail} if detail else {})}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("corpus")
    ap.add_argument("-o", "--out", default="./pdfs")
    ap.add_argument("--email", default=os.environ.get("PAPER_SEARCH_MCP_UNPAYWALL_EMAIL", ""),
                    help="contact email for arXiv/Unpaywall politeness + OA lookup")
    ap.add_argument("--top", default="25",
                    help="acquire the top-N PDFs, or 'all'/'0' for the whole corpus")
    ap.add_argument("--no-browser", action="store_true",
                    help="stop after OA routes instead of trying entitled DOI access")
    ap.add_argument("--browser-mode", choices=("auto", "headed", "headless"), default="auto",
                    help="browser display mode (default: headed on desktops, headless otherwise)")
    ap.add_argument("--browser-timeout", type=float, default=45,
                    help="per browser navigation/request timeout in seconds (default: 45)")
    ap.add_argument("--retry-unresolved", action="store_true",
                    help="reuse existing successful rows and retry only unresolved papers")
    args = ap.parse_args()
    if not args.email:
        sys.exit("--email is required (or set PAPER_SEARCH_MCP_UNPAYWALL_EMAIL)")

    with open(args.corpus, encoding="utf-8") as f:
        corpus = json.load(f)
    papers = (
        corpus
        if str(args.top).strip().lower() in ("all", "0", "-1")
        else corpus[: int(args.top)]
    )
    os.makedirs(args.out, exist_ok=True)

    mpath = os.path.join(args.out, "manifest.json")
    previous = _existing_manifest(mpath) if args.retry_unresolved else []
    previous_by_key = {_record_key(row): row for row in previous}
    manifest = []
    ok = 0
    browser = None
    try:
        for i, rec in enumerate(papers, 1):
            n = rec.get("rank", i)  # corpus rank — matches corpus.md + summary.md numbering
            name = slug(rec, n)
            old = previous_by_key.get(_record_key(rec, n))
            if old and old.get("status") == "ok" and _existing_file(old):
                manifest.append(old)
                ok += 1
                print(f"  [{i:02d}] keep existing {os.path.basename(old['file'])}", file=sys.stderr)
                continue

            entry = {"i": n, "rank": n, "title": rec.get("title"), "doi": rec.get("doi"),
                     "arxiv_id": rec.get("arxiv_id"), "attempts": []}
            if old:
                entry["previous_status"] = old.get("status")
            got = False
            for route_name, route in ROUTES:
                try:
                    data, used = route(rec, args.email)
                except Exception as exc:  # noqa: BLE001
                    attempt = {"route": route_name, "status": "error",
                               "detail": " ".join(str(exc).split())[:500]}
                    code = getattr(exc, "code", None)
                    if code is not None:
                        attempt["http_status"] = code
                    entry["attempts"].append(attempt)
                    continue
                if not data:
                    entry["attempts"].append({"route": route_name, "status": "unavailable"})
                    continue

                path = os.path.join(args.out, name + ".pdf")
                _save(data, path)
                entry["attempts"].append({"route": used, "status": "ok"})
                entry.update(status="ok", route=used, file=path, bytes=len(data))
                ok += 1
                got = True
                print(f"  [{i:02d}] ok via {used:21s} {name}.pdf ({len(data)//1024} KB)",
                      file=sys.stderr)
                break

            if not got and not args.no_browser:
                if browser is None:
                    browser = BrowserAcquirer(mode=args.browser_mode,
                                              timeout_seconds=args.browser_timeout)
                landing_url = rec.get("url") if not rec.get("doi") else None
                result = browser.acquire(rec.get("doi"), landing_url=landing_url)
                entry["attempts"].append({
                    "route": result.route,
                    "status": result.status,
                    **(
                        {"http_status": result.http_status}
                        if result.http_status is not None
                        else {}
                    ),
                })
                if result.data:
                    path = os.path.join(args.out, name + ".pdf")
                    _save(result.data, path)
                    entry.update(result.manifest_fields())
                    entry.update(file=path, bytes=len(result.data))
                    ok += 1
                    got = True
                    print(f"  [{i:02d}] ok via institutional_browser {name}.pdf "
                          f"({len(result.data)//1024} KB)", file=sys.stderr)
                else:
                    entry.update(result.manifest_fields())

            if not got:
                if args.no_browser:
                    entry.update(_browser_failure(
                        "browser_disabled", "browser fallback disabled by --no-browser"))
                print(f"  [{i:02d}] {entry['status']:19s} {(rec.get('title') or '')[:60]}",
                      file=sys.stderr)
            manifest.append(entry)
    finally:
        if browser is not None:
            browser.close()

    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    unresolved = len(papers) - ok
    counts = {}
    for row in manifest:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
    print(f"\n  acquired {ok}/{len(papers)} PDFs; unresolved={unresolved} ({summary}). "
          f"manifest: {mpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
