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
    3. title          normalized: lowercased, non-word (Unicode-aware) chars and
                      underscores collapsed to spaces, ws collapsed. CJK/Hangul titles
                      use a 6-char floor for the title key; pure-Latin titles need >8.

Records sharing any key are merged into one. Merged record keeps the richest value
per field (longest abstract, most authors, max citations, etc.) and accumulates the
set of sources that found it in "sources" — source-hit-count is a strong relevance
signal.

Ranking defaults to a five-layer score designed to keep independent signals
orthogonal: provenance, impact, recency, access/completeness, and query relevance.
Use --ranking classic to restore the older sources_count/citations/year sort.

Usage:
    merge_corpus.py RAW_DIR [-o corpus.json] [--md corpus.md] [--min-sources N]
                    [--topic TOPIC] [--goal survey|systematic|newest|seminal|implementation|pdf-corpus]

RAW_DIR may be a directory of *.json files or one or more explicit json files.
"""
import argparse
import glob
import json
import math
import os
import re
import sys
from datetime import datetime, timezone


CURRENT_YEAR = datetime.now(timezone.utc).year

GOAL_WEIGHTS = {
    # Five orthogonal layers: source agreement, scholarly uptake, time frontier,
    # acquisition/readability, and topic fit. Each profile sums to 1.0.
    "survey": {"provenance": 0.30, "impact": 0.20, "recency": 0.15, "access": 0.15, "relevance": 0.20},
    "systematic": {"provenance": 0.35, "impact": 0.20, "recency": 0.10, "access": 0.15, "relevance": 0.20},
    "newest": {"provenance": 0.20, "impact": 0.10, "recency": 0.40, "access": 0.10, "relevance": 0.20},
    "seminal": {"provenance": 0.20, "impact": 0.45, "recency": 0.05, "access": 0.10, "relevance": 0.20},
    "implementation": {"provenance": 0.20, "impact": 0.15, "recency": 0.20, "access": 0.20, "relevance": 0.25},
    "pdf-corpus": {"provenance": 0.25, "impact": 0.15, "recency": 0.10, "access": 0.30, "relevance": 0.20},
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "into", "is",
    "of", "on", "or", "the", "to", "via", "with", "without", "using", "based",
    "paper", "papers", "study", "studies", "review", "survey",
}


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
    # 유니코드 단어문자(한글·CJK 포함)는 보존하고, 그 외 구두점/기호와 밑줄(_)만 공백으로.
    v = re.sub(r"[\W_]+", " ", str(v).lower(), flags=re.UNICODE).strip()
    return v or None


def terms(text):
    out = set()
    for tok in re.findall(r"[a-z0-9][a-z0-9-]{2,}", str(text or "").lower()):
        tok = tok.strip("-")
        if tok and tok not in STOPWORDS:
            out.add(tok)
    return out


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
    # 한글/CJK가 포함되면 짧아도 정보량이 충분하므로 길이 가드를 6자로 완화,
    # 순수 라틴 제목은 기존대로 8자 초과만 키로 사용(우연한 단문 충돌 방지).
    if t:
        has_cjk = bool(re.search(r"[　-鿿가-힣]", t))
        if (has_cjk and len(t) >= 6) or (not has_cjk and len(t) > 8):
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


def _classic_key(r):
    return (
        len(r.get("sources") or []),
        int(r.get("citations") or 0),
        int(r.get("year") or 0),
    )


def _norm_log(value, max_value):
    if not value or not max_value:
        return 0.0
    return math.log1p(max(0, value)) / math.log1p(max_value)


def _access_score(r):
    score = 0.0
    if norm_doi(r.get("doi")) or norm_arxiv(r.get("arxiv_id") or r.get("arxiv")):
        score += 0.25
    if r.get("pdf_url"):
        score += 0.25
    if r.get("abstract"):
        score += 0.20
    if r.get("authors"):
        score += 0.15
    if r.get("year") or r.get("venue") or r.get("url"):
        score += 0.15
    return min(1.0, score)


def _relevance_score(r, query_terms):
    if not query_terms:
        return 0.0
    doc_terms = terms(" ".join(str(x or "") for x in (
        r.get("title"), r.get("abstract"), r.get("venue"), " ".join(r.get("queries") or [])
    )))
    if not doc_terms:
        return 0.0
    overlap = len(query_terms & doc_terms)
    # Cap the denominator so long query expansions do not crush good matches.
    return min(1.0, overlap / max(1, min(len(query_terms), 12)))


def _layer_scores(r, stats, query_terms):
    citations = int(r.get("citations") or 0)
    year = int(r.get("year") or 0)
    age = max(1, CURRENT_YEAR - year + 1) if year else None
    citation_velocity = citations / age if age else 0.0
    impact = (
        0.65 * _norm_log(citations, stats["max_citations"]) +
        0.35 * _norm_log(citation_velocity, stats["max_velocity"])
    )
    recency = 0.0
    if age:
        recency = max(0.0, 1.0 - ((age - 1) / 12.0))
    return {
        "provenance": min(1.0, (r.get("sources_count") or 0) / max(1, min(stats["max_sources"], 4))),
        "impact": round(impact, 6),
        "recency": round(recency, 6),
        "access": round(_access_score(r), 6),
        "relevance": round(_relevance_score(r, query_terms), 6),
    }


def rank(records, ranking="layered", topic="", goal="survey"):
    if ranking == "classic":
        for r in records:
            r.pop("rank_layers", None)
            r.pop("score", None)
            r.pop("rank_goal", None)
        return sorted(records, key=_classic_key, reverse=True)

    weights = GOAL_WEIGHTS.get(goal) or GOAL_WEIGHTS["survey"]
    max_citations = max((int(r.get("citations") or 0) for r in records), default=0)
    velocities = []
    for r in records:
        year = int(r.get("year") or 0)
        if year:
            velocities.append(int(r.get("citations") or 0) / max(1, CURRENT_YEAR - year + 1))
    stats = {
        "max_citations": max_citations,
        "max_velocity": max(velocities, default=0.0),
        "max_sources": max((r.get("sources_count") or 0 for r in records), default=1),
    }
    query_terms = terms(topic)
    for r in records:
        query_terms |= terms(" ".join(r.get("queries") or []))

    for r in records:
        layers = _layer_scores(r, stats, query_terms)
        score = sum(layers[k] * weights[k] for k in weights)
        r["rank_layers"] = layers
        r["rank_goal"] = goal
        r["score"] = round(score, 6)

    def keyf(r):
        return (
            float(r.get("score") or 0.0),
            _classic_key(r),
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
        if r.get("score") is not None:
            tags.append(f"score {r['score']}")
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
    ap.add_argument("--ranking", choices=["layered", "classic"], default="layered",
                    help="ranking mode: five-layer score (default) or legacy tuple sort")
    ap.add_argument("--topic", default="", help="topic text used by the relevance layer")
    ap.add_argument("--goal", choices=sorted(GOAL_WEIGHTS), default="survey",
                    help="goal-specific weight profile for layered ranking")
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
    merged = rank(merged, ranking=args.ranking, topic=args.topic, goal=args.goal)
    for n, r in enumerate(merged, 1):
        r["rank"] = n  # 1-based corpus rank; PDF filenames + summary.md number by this
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
