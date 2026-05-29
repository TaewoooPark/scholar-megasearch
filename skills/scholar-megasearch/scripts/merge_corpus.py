#!/usr/bin/env python3
"""Merge per-source paper-search result files into one deduplicated, ranked corpus.

Each subagent writes ONE JSON file to the run's raw/ directory. Each file is either
a JSON list of records, or an object with a "results" list. A record is a dict with
any of these keys (all optional except a title or an id):

    title, authors (list[str]), year (int), venue, doi, arxiv_id,
    pdf_url, url, citations (int), abstract, source (str), query (str)

Dedup keys, in priority order:
    1. DOI            normalized: lowercased, strip leading "https://doi.org/" / "doi:"
    2. arXiv id       normalized: strip "arXiv:" prefix and version suffix (v1, v2, ...)
    3. title          normalized: lowercased, non-alphanumeric stripped, ws collapsed

Records sharing any key are merged into one. Merged record keeps the richest value
per field (longest abstract, most authors, max citations, etc.) and accumulates the
set of sources that found it in "sources" — source-hit-count is a strong relevance
signal.

Ranking (descending): sources_count, citations, year.

Usage:
    merge_corpus.py RAW_DIR [-o corpus.json] [--md corpus.md] [--min-sources N]

RAW_DIR may be a directory of *.json files or one or more explicit json files.
"""
import argparse
import glob
import json
import os
import re
import sys


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! skip {os.path.basename(path)}: {e}", file=sys.stderr)
        return []
    if isinstance(data, dict):
        data = data.get("results") or data.get("papers") or data.get("data") or []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def norm_doi(v):
    if not v:
        return None
    v = str(v).strip().lower()
    v = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", v)
    return v or None


def norm_arxiv(v):
    if not v:
        return None
    v = str(v).strip()
    v = re.sub(r"^arxiv:", "", v, flags=re.IGNORECASE)
    v = v.rsplit("/", 1)[-1]
    v = re.sub(r"v\d+$", "", v)
    return v.lower() or None


def norm_title(v):
    if not v:
        return None
    v = re.sub(r"[^a-z0-9]+", " ", str(v).lower()).strip()
    return v or None


def record_keys(r):
    """Yield the dedup keys this record participates in."""
    keys = []
    d = norm_doi(r.get("doi"))
    if d:
        keys.append(("doi", d))
    a = norm_arxiv(r.get("arxiv_id") or r.get("arxiv"))
    if a:
        keys.append(("arxiv", a))
    t = norm_title(r.get("title"))
    if t and len(t) > 8:  # avoid merging on trivially short titles
        keys.append(("title", t))
    return keys


def _richer(a, b):
    """Pick the more informative of two scalar/list values."""
    if a is None or a == "":
        return b
    if b is None or b == "":
        return a
    if isinstance(a, list) or isinstance(b, list):
        la = a if isinstance(a, list) else [a]
        lb = b if isinstance(b, list) else [b]
        return la if len(la) >= len(lb) else lb
    if isinstance(a, str) and isinstance(b, str):
        return a if len(a) >= len(b) else b
    return a


def merge_into(dst, src):
    for k, v in src.items():
        if k in ("source", "sources", "query", "queries"):
            continue
        dst[k] = _richer(dst.get(k), v)
    # citations: keep max
    for cf in ("citations", "citationCount"):
        if cf in src:
            try:
                dst["citations"] = max(int(dst.get("citations") or 0), int(src[cf] or 0))
            except (TypeError, ValueError):
                pass
    dst.setdefault("sources", set())
    if src.get("source"):
        dst["sources"].add(str(src["source"]))
    for s in src.get("sources", []) or []:
        dst["sources"].add(str(s))
    dst.setdefault("queries", set())
    if src.get("query"):
        dst["queries"].add(str(src["query"]))


def dedupe(records):
    union = {}          # key -> cluster id
    clusters = {}       # cluster id -> merged record
    next_id = 0
    for r in records:
        keys = record_keys(r)
        if not keys:
            continue
        found = next((union[k] for k in keys if k in union), None)
        if found is None:
            found = next_id
            next_id += 1
            clusters[found] = {}
        merge_into(clusters[found], r)
        for k in keys:
            existing = union.get(k)
            if existing is not None and existing != found:
                # fold existing cluster into found
                merge_into(clusters[found], clusters.pop(existing))
                for kk, vv in list(union.items()):
                    if vv == existing:
                        union[kk] = found
            union[k] = found
    return list(clusters.values())


def rank(records):
    def keyf(r):
        return (
            len(r.get("sources") or []),
            int(r.get("citations") or 0),
            int(r.get("year") or 0),
        )
    return sorted(records, key=keyf, reverse=True)


def finalize(r):
    r["sources"] = sorted(r.get("sources") or [])
    r["sources_count"] = len(r["sources"])
    r["queries"] = sorted(r.get("queries") or [])
    return r


def to_md(records):
    lines = [f"# Literature corpus — {len(records)} unique papers\n"]
    for i, r in enumerate(records, 1):
        au = ", ".join((r.get("authors") or [])[:3])
        if r.get("authors") and len(r["authors"]) > 3:
            au += " et al."
        bits = [f"**{i}. {r.get('title', '(untitled)')}**"]
        meta = []
        if au:
            meta.append(au)
        if r.get("year"):
            meta.append(str(r["year"]))
        if r.get("venue"):
            meta.append(r["venue"])
        if meta:
            bits.append("  \n   " + " · ".join(meta))
        tags = []
        if r.get("citations"):
            tags.append(f"cited {r['citations']}")
        tags.append(f"{r['sources_count']} sources: {', '.join(r['sources'])}")
        bits.append(f"  \n   _{' | '.join(tags)}_")
        link = r.get("doi") and f"https://doi.org/{norm_doi(r['doi'])}" or r.get("pdf_url") or r.get("url")
        if link:
            bits.append(f"  \n   {link}")
        lines.append("".join(bits) + "\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="raw/ directory or explicit .json files")
    ap.add_argument("-o", "--out", default="corpus.json")
    ap.add_argument("--md", help="also write a human-readable markdown digest")
    ap.add_argument("--min-sources", type=int, default=1, help="drop papers found by fewer than N sources")
    args = ap.parse_args()

    files = []
    for inp in args.inputs:
        if os.path.isdir(inp):
            files += sorted(glob.glob(os.path.join(inp, "*.json")))
        else:
            files.append(inp)
    if not files:
        sys.exit("no input json files found")

    raw = []
    for f in files:
        recs = _load(f)
        print(f"  loaded {len(recs):4d} from {os.path.basename(f)}", file=sys.stderr)
        raw += recs
    print(f"  total raw records: {len(raw)}", file=sys.stderr)

    merged = [finalize(r) for r in dedupe(raw)]
    merged = [r for r in merged if r["sources_count"] >= args.min_sources]
    merged = rank(merged)
    print(f"  unique papers: {len(merged)}", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"  wrote {args.out}", file=sys.stderr)

    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(to_md(merged))
        print(f"  wrote {args.md}", file=sys.stderr)


if __name__ == "__main__":
    main()
