#!/usr/bin/env python3
"""Offline-friendly fallback search using the skill_venv packages (no MCP needed).

Run with the venv interpreter:
    ~/.claude/skill_venv/bin/python3 search_local.py SOURCE "query" [-n 30] [-o out.json]

SOURCE is one of: arxiv | semanticscholar | ddg
Emits a JSON list of records in the corpus schema (title, authors, year, doi,
arxiv_id, pdf_url, url, citations, abstract, source, query) to stdout or -o.

This is the fallback path for when MCP servers are unavailable (headless/cron) or a
source is down. The primary path is the MCP tools — see references/sources.md.
"""
import argparse
import json
import sys


def search_arxiv(query, n):
    import arxiv
    client = arxiv.Client()
    out = []
    for r in client.results(arxiv.Search(query=query, max_results=n,
                                          sort_by=arxiv.SortCriterion.Relevance)):
        out.append({
            "title": r.title,
            "authors": [str(a) for a in r.authors],
            "year": r.published.year if r.published else None,
            "arxiv_id": r.entry_id.split("/")[-1],
            "doi": r.doi,
            "pdf_url": r.pdf_url,
            "url": r.entry_id,
            "venue": "arXiv",
            "abstract": (r.summary or "").strip(),
            "source": "arxiv",
            "query": query,
        })
    return out


def search_semanticscholar(query, n):
    from semanticscholar import SemanticScholar
    sch = SemanticScholar()
    res = sch.search_paper(query, limit=min(n, 100),
                           fields=["title", "authors", "year", "venue", "externalIds",
                                   "openAccessPdf", "citationCount", "abstract"])
    out = []
    for p in res[:n]:
        ext = p.externalIds or {}
        out.append({
            "title": p.title,
            "authors": [a.name for a in (p.authors or [])],
            "year": p.year,
            "venue": p.venue,
            "doi": ext.get("DOI"),
            "arxiv_id": ext.get("ArXiv"),
            "pdf_url": (p.openAccessPdf or {}).get("url") if p.openAccessPdf else None,
            "citations": p.citationCount,
            "abstract": p.abstract,
            "source": "semanticscholar",
            "query": query,
        })
    return out


def search_ddg(query, n):
    from ddgs import DDGS
    out = []
    for r in DDGS().text(query, max_results=n):
        out.append({
            "title": r.get("title"),
            "url": r.get("href") or r.get("link"),
            "abstract": r.get("body"),
            "source": "ddg",
            "query": query,
        })
    return out


DISPATCH = {"arxiv": search_arxiv, "semanticscholar": search_semanticscholar, "ddg": search_ddg}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", choices=list(DISPATCH))
    ap.add_argument("query")
    ap.add_argument("-n", "--limit", type=int, default=30)
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    try:
        recs = DISPATCH[args.source](args.query, args.limit)
    except Exception as e:  # noqa: BLE001 - surface any source/network error as JSON-less stderr
        sys.exit(f"{args.source} search failed: {e}")

    payload = json.dumps(recs, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {len(recs)} records -> {args.out}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
