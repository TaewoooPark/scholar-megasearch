---
name: scholar-megasearch
description: >-
  Massive multi-source academic literature search via subagent orchestration.
  Fans out parallel searchers across every available scholarly source — arXiv,
  Semantic Scholar, Crossref, OpenAlex, PubMed/PMC, bioRxiv/medRxiv, DOAJ, CORE,
  BASE, DBLP, IACR, SSRN, Zenodo, Unpaywall, plus web/GitHub — then deduplicates
  by DOI/arXiv-id/title into one ranked corpus and synthesizes it. Use when the
  user wants a broad/exhaustive literature sweep, a large-scale paper search, a
  systematic review corpus, citation snowballing, or to find as many papers as
  possible on a topic across many databases at once. Triggers: "massive literature
  search", "literature review", "search across every database", "systematic search",
  "mega search", "search every source", "exhaustive search". Localized trigger phrases
  in other languages map to the same intent.
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

### 1. Frame the query + pick a depth level
Restate the topic in one line. If it is underspecified (e.g. "find papers on neural
networks"), ask 1–2 clarifying questions (sub-aspect? time range? methods vs. phenomena?) before
fanning out — a vague seed wastes a large fan-out.
Then pick a **depth level L1–L5** (see `## Depth levels` below): it sets the facet count,
bucket count, per-source hit cap, and how many waves run. An explicit `depth=N` / `LN` /
bare `1–5` in the request wins; otherwise infer from phrasing; otherwise default **L2**.

### 2. Decompose into facets + route to buckets
- **Facets** (count set by the depth level, 3–8): synonyms, sub-aspects, method vs.
  phenomenon, key authors, and at least one each of a broad and a narrow phrasing. For
  topics with strong non-English literature, add a localized query in the relevant
  language for Bucket G.
- **Buckets** (count set by the depth level, 4–7): pick from the domain→bucket routing
  table in `references/sources.md` based on the topic's field. Default for
  unknown/interdisciplinary: A, B, C, D, E, G.

### 3. Set up the run directory
Create `./literature_search/<slug>_<YYYY-MM-DD>/raw/` under the **current working
directory** (slug = short kebab of the topic; use today's date). All artifacts go here.

### 4. Fan out the searchers (wave 1)
- **If the user opted into workflows** ("workflow" keyword / ultracode): run the Workflow
  script in `references/orchestration.md`, passing `{topic, facets, buckets, cap}` as `args`
  (`cap` = the level's hits/subquery). Then write each returned `raw[i]` to `raw/<bucket>.json`.
- **Otherwise**: spawn one Agent per bucket in a single message (concurrent), each writing
  its own `raw/<bucket>.json`. Use the Agent prompt skeleton in `references/orchestration.md`.

Every searcher returns records in the schema (title, authors, year, doi, arxiv_id,
pdf_url, url, citations, abstract, **source**, **query**) and does NOT dedupe. This is
**wave 1**; L3+ add further waves after the first merge — see `## Depth levels`.

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
- **Number every paper by its `corpus.json` `rank`** (1-based) shown as `[#NN]`. That
  same number is the `NN_` prefix of the acquired `pdfs/NN_*.pdf` and the `rank`/`i` in
  `pdfs/manifest.json`, so a reader jumps from a summary `[#NN]` straight to its file.
- Seminal/most-cited works, recent frontier (last 2 yrs), and notable gaps.
- Cite by DOI/arXiv id. Report honestly what was searched and any source that failed —
  no fabricated entries (see memory `feedback_honest_writing`).

### 7. Acquire original PDFs
Pull the original PDFs for the depth level's count — L1 → top 10, L2 → 30, L3 → 50,
L4 → 100, **L5 → `all`** (every paper in the corpus). `--top all` (or `0`) takes the
whole corpus; files are saved as `NN_<slug>.pdf` by `corpus.json` rank, matching the
`[#NN]` in `summary.md`:
```bash
python3 ~/.claude/skills/scholar-megasearch/scripts/fetch_pdfs.py \
  ./literature_search/<slug>_<date>/corpus.json \
  -o ./literature_search/<slug>_<date>/pdfs \
  --email you@example.com --top 30
```
This auto-acquires via the free/legal routes — known open-access `pdf_url`, arXiv
direct, then Unpaywall OA API — verifying each file is a real PDF, and writes
`pdfs/manifest.json`. Papers with no free route are flagged `"status": "needs_mcp"`.
For those, fetch via the session MCP download tools (`paper-search-mcp.
download_with_fallback`, source-specific `download_*`, or `download_scihub`) — a
standalone script cannot reach MCP. To read extracted full text afterward, use the
`read_*_paper` MCP tools or `pdfplumber`/`pymupdf` (`~/.claude/skill_venv/bin/`).
See `references/sources.md` for the full acquisition tool list.

## Depth levels (L1–L5)
One knob: breadth (facets × buckets × hits) and recursion (extra waves) scale together.
Pick one per run — explicit `depth=N` / `LN` / bare `1–5` wins; else infer from phrasing;
else default **L2**. Clamp out-of-range to 1–5, and state the level you ran at.

| Lvl | facets | buckets | hits/subq | waves | PDFs | output |
|-----|--------|---------|-----------|-------|------|--------|
| **L1 Quick** | 3 | 4 | 15 | wave 1 only | top 10 | corpus |
| **L2 Standard** *(default)* | 5 | 5 | 25 | wave 1 only | top 30 | corpus |
| **L3 Deep** | 6 | 6 | 30 | + citation-snowball | top 50 | corpus |
| **L4 Exhaustive** | 8 | 7 (all) | 40 | + snowball + 1 completeness-critic pass | top 100 | corpus + ≥2 shortlist |
| **L5 Total / Exhaustive** | 8 | 7 (all) | 40 | + snowball + critic **loop-until-dry** | all | corpus + ≥2 shortlist |

Phrasing → level when not explicit: quick·first look·taste → L1 · *(no signal)* → L2 ·
deep·snowball·trace citations → L3 · systematic review·comprehensive·thorough → L4 ·
exhaustive·every source·all of them·to the end → L5. Equivalent phrases in other
languages map the same way. Higher levels spawn more subagents and cost more tokens
(L5 is bounded only by the token budget, not a fixed wave count).

**Waves** — each is a fan-out followed by a `merge_corpus.py` pass into the *same* corpus;
applies to both the Workflow and Agent paths:
1. **Wave 1** (all levels): `buckets` searchers, each running the `facets` subqueries,
   ~`hits` per subquery.
2. **Citation-snowball** (L3+): take the top ~10 DOIs/arXiv ids from the corpus so far and
   fan out one wave that expands their forward (cited-by) + backward (references) neighbours.
   Workflow: re-run the script with `seeds:[...]`. Agent: tell each searcher to run
   `asta get_citations` / arXiv `citation_graph` / OpenAlex cited-by on the seeds.
3. **Completeness-critic** (L4+): a critic agent reads `corpus.md` and names the missing
   subtopics / seminal authors; those become new facets for one more wave-1-style fan-out.
4. **Loop-until-dry** (L5): repeat the critic → facets → fan-out → merge cycle until two
   consecutive critic passes surface nothing new (or, under Workflow, `budget.remaining()`
   runs low).

L4/L5 also re-run the merge with `--min-sources 2` → `corpus_shortlist.json` (papers
corroborated by ≥2 databases) alongside the full `corpus.json`.

## Fallback when MCP is unavailable
If MCP servers are down/headless, searchers use `scripts/search_local.py {arxiv|
semanticscholar|ddg} "query"` (runs on `~/.claude/skill_venv/bin/python3`). arXiv may
rate-limit (HTTP 429) under heavy fan-out — stagger or lean on Asta/OpenAlex. The Asta
(Semantic Scholar) MCP is remote and needs **no key** (a key only raises rate limits) —
in headless/cron runs just ensure network access, or fall back to
`search_local.py semanticscholar`. Never let claude.ai `Scholar_Gateway` be a bucket's
only tool (absent in headless runs).
