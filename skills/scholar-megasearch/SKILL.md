---
name: scholar-megasearch
description: >-
  Massive multi-source academic literature search via subagent orchestration.
  Fans out parallel searchers across every available scholarly source — arXiv,
  Semantic Scholar, Crossref, OpenAlex, PubMed/PMC, bioRxiv/medRxiv, DOAJ, CORE,
  BASE, DBLP, IACR, SSRN, Zenodo, Unpaywall, plus web/GitHub — then deduplicates
  by DOI/arXiv-id/title into one ranked corpus and synthesizes it. Use when the
  user wants a broad/exhaustive literature sweep, a "방대한"/대규모 논문 검색, a
  systematic review corpus, citation snowballing, or to find as many papers as
  possible on a topic across many databases at once. Triggers: "논문 방대하게
  검색", "literature review", "여러 DB에서 다 찾아줘", "systematic search",
  "메가 검색", "search every source", "전수조사".
---

# scholar-megasearch

Integrates every academic search MCP/skill in this environment into one fan-out →
merge → synthesize pipeline. Each subagent owns one **source bucket** and searches in
parallel; results are merged into a single deduplicated, provenance-tracked, ranked
corpus. Prefer this over single-source searches whenever breadth matters.

For the full source list and which tools live in each bucket, read
`references/sources.md`. For the orchestration templates and the record schema, read
`references/orchestration.md`.

## Workflow

### 1. Frame the query
Restate the topic in one line. If it is underspecified (e.g. "find papers on magnets"),
ask 1–2 clarifying questions (sub-aspect? time range? methods vs. phenomena?) before
fanning out — a vague seed wastes a large fan-out.

### 2. Decompose into facets + route to buckets
- **Facets** (3–8 subqueries): synonyms, sub-aspects, method vs. phenomenon, key authors,
  and at least one each of a broad and a narrow phrasing. For non-English-friendly topics
  add a localized query (e.g. Korean) for Bucket G.
- **Buckets** (4–7): pick from the domain→bucket routing table in `references/sources.md`
  based on the topic's field. Default for unknown/interdisciplinary: A, B, C, D, E, G.

### 3. Set up the run directory
Create `./literature_search/<slug>_<YYYY-MM-DD>/raw/` under the **current working
directory** (slug = short kebab of the topic; use today's date). All artifacts go here.

### 4. Fan out the searchers
- **If the user opted into workflows** ("workflow" keyword / ultracode): run the Workflow
  script in `references/orchestration.md`, passing `{topic, facets, buckets}` as `args`.
  Then write each returned `raw[i]` to `raw/<bucket>.json`.
- **Otherwise**: spawn one Agent per bucket in a single message (concurrent), each writing
  its own `raw/<bucket>.json`. Use the Agent prompt skeleton in `references/orchestration.md`.

Every searcher returns records in the schema (title, authors, year, doi, arxiv_id,
pdf_url, url, citations, abstract, **source**, **query**) and does NOT dedupe.

### 5. Merge into one corpus
```bash
python3 ~/.claude/skills/scholar-megasearch/scripts/merge_corpus.py \
  ./literature_search/<slug>_<date>/raw \
  -o ./literature_search/<slug>_<date>/corpus.json \
  --md ./literature_search/<slug>_<date>/corpus.md
```
Dedupes by DOI → arXiv-id → normalized title, merges duplicates (keeping the richest
fields + max citations), and ranks by (sources_count, citations, year). `corpus.md` is
the human-readable digest. Use `--min-sources 2` to keep only papers corroborated by ≥2
databases (high-precision shortlist).

### 6. Synthesize
Read `corpus.json` and write `summary.md` in the run dir:
- Headline count (unique papers, sources hit, year span).
- Top ~15–25 papers grouped by sub-theme, each with a one-line "why it matters".
- Seminal/most-cited works, recent frontier (last 2 yrs), and notable gaps.
- Cite by DOI/arXiv id. Report honestly what was searched and any source that failed —
  no fabricated entries (see memory `feedback_honest_writing`).

### 7. Acquire original PDFs
To pull the original PDFs of the top-K ranked papers:
```bash
python3 ~/.claude/skills/scholar-megasearch/scripts/fetch_pdfs.py \
  ./literature_search/<slug>_<date>/corpus.json \
  -o ./literature_search/<slug>_<date>/pdfs \
  --email you@example.com --top 25
```
This auto-acquires via the free/legal routes — known open-access `pdf_url`, arXiv
direct, then Unpaywall OA API — verifying each file is a real PDF, and writes
`pdfs/manifest.json`. Papers with no free route are flagged `"status": "needs_mcp"`.
For those, fetch via the session MCP download tools (`paper-search-mcp.
download_with_fallback`, source-specific `download_*`, or `download_scihub`) — a
standalone script cannot reach MCP. To read extracted full text afterward, use the
`read_*_paper` MCP tools or `pdfplumber`/`pymupdf` (`~/.claude/skill_venv/bin/`).
See `references/sources.md` for the full acquisition tool list.

## Depth control
- **Quick sweep**: 3–4 facets, 4 buckets, 1 round.
- **Exhaustive** (systematic review): 6–8 facets, 6–7 buckets, + a citation-snowball
  round (seed top DOIs/arXiv ids back through `citation_graph`/OpenAlex cited-by, merge
  the second wave into the same corpus) + a completeness-critic agent that names missing
  subtopics/authors, which become the next round's facets.

## Fallback when MCP is unavailable
If MCP servers are down/headless, searchers use `scripts/search_local.py {arxiv|
semanticscholar|ddg} "query"` (runs on `~/.claude/skill_venv/bin/python3`). arXiv may
rate-limit (HTTP 429) under heavy fan-out — stagger or lean on Semantic Scholar/OpenAlex.
Never let claude.ai `Scholar_Gateway` be a bucket's only tool (absent in headless runs).
