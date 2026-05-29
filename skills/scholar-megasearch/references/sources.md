# Source catalog & domain routing

All search/read/download capabilities available in this environment, grouped into
**buckets** that map cleanly onto one subagent each. A megasearch assigns 1 bucket
per agent so they fan out without overlapping or rate-limiting each other.

Most tools are **deferred** — load schemas with `ToolSearch` before calling, e.g.
`ToolSearch({query: "select:mcp__paper-search-mcp__search_pubmed,mcp__paper-search-mcp__search_crossref", max_results: 10})`.
Inside a Workflow, agents load their own schemas via ToolSearch automatically.

## Bucket A — arXiv (preprints, physics/CS/math)
`arxiv-mcp-server`: `search_papers`, `semantic_search`, `get_abstract`,
`download_paper`, `read_paper`, `citation_graph`, `list_papers`.
- `search_papers` — boolean field queries (`ti:`, `au:`, `abs:`, `cat:`).
- `semantic_search` — natural-language similarity.
- `citation_graph` — forward/backward citations from a seed arXiv id (snowballing).
Fallback: `scripts/search_local.py arxiv "query"`.

## Bucket B — Semantic Scholar (200M+ papers, citation counts)
`semantic-scholar-mcp`: `semanticSearch`. Also claude.ai `Scholar_Gateway.semanticSearch`
(best-effort; may be absent in headless/cron runs — never make it the only source).
`paper-search-mcp`: `search_semantic`, `read_semantic_paper`, `download_semantic`.
Best source for **citation counts** → ranking and for finding the canonical version of
a preprint. Fallback: `scripts/search_local.py semanticscholar "query"`.

## Bucket C — Crossref + OpenAlex (DOIs, published-version metadata)
`paper-search-mcp`: `search_crossref`, `get_crossref_paper_by_doi`, `read_crossref_paper`,
`search_openalex`, `read_openalex_paper`, `download_openalex`.
Use to resolve a DOI → authoritative journal/venue/year, and for broad cross-discipline
coverage (OpenAlex ≈ 250M works). `get_crossref_paper_by_doi` is the verified path for
DOI → full bibliographic record (see memory: paper-search-mcp must be git-main build).

## Bucket D — Life sciences
`paper-search-mcp`: `search_pubmed`, `read_pubmed_paper`, `search_pmc`,
`search_biorxiv`, `read_biorxiv_paper`, `search_medrxiv`, `read_medrxiv_paper`,
`search_europepmc`. Route here for biology / medicine / neuroscience / clinical.

## Bucket E — Open access & repositories
`paper-search-mcp`: `search_doaj` (OA journals), `search_core`, `search_base`,
`search_openaire`, `search_zenodo` (datasets/software), `search_unpaywall`
(OA PDF for a DOI), `search_hal` (French repo). Route here to maximize free full-text.

## Bucket F — Domain specialists
`paper-search-mcp`: `search_dblp` (CS/venues), `search_iacr` (cryptography),
`search_citeseerx`, `search_ssrn` (social science / econ / law).
Route by topic: cryptography → IACR; CS systems/ML venues → DBLP; econ/law → SSRN.

## Bucket G — Web & grey literature
`scripts/search_local.py ddg "query"` (DuckDuckGo: GitHub, blogs, theses, lab pages).
`crawl4ai` (`~/.claude/skill_venv/bin/crwl "URL" -o markdown`) or the `firecrawl-*`
skills to scrape a specific page → markdown. `WebSearch`/`WebFetch` as generic fallback.
`mcp__github__search_repositories` / `search_code` for code/datasets behind a method.

## Domain → bucket routing (pick 4–7 buckets per run)

| Domain of the query | Always | Plus |
|---|---|---|
| Physics / materials / cond-mat | A, B, C | E, G |
| CS / ML / systems | A, B, F(DBLP) | C, G(GitHub) |
| Biology / medicine / neuro | D, B, C | E |
| Chemistry / materials | B, C, D(PMC) | E |
| Cryptography / security | A, F(IACR), B | G(GitHub) |
| Economics / social science / law | F(SSRN), B, C | G |
| Math | A, B, C | F |
| Interdisciplinary / unknown | A, B, C, D | E, G |

`unpaywall`/`scihub`/`download_with_fallback` are for **acquisition** (getting the PDF
of an already-identified paper), not discovery — use them in the optional download phase.

## Acquisition (download original PDFs + full-text read)
**Primary (automated, no MCP):** `scripts/fetch_pdfs.py corpus.json -o pdfs --email <e>
--top K` acquires the top-K originals via free/legal routes (open-access `pdf_url` →
arXiv direct → Unpaywall OA API), verifies each is a real `%PDF-`, and writes
`pdfs/manifest.json`. Papers with no free route get `status: "needs_mcp"`.

**MCP fallback (for `needs_mcp` / closed-access):** `paper-search-mcp.
download_with_fallback` (tries multiple hosts) or source-specific `download_arxiv` /
`download_openalex` / `download_semantic` / `download_scihub`. These are session tools
the standalone script can't call.

**Full-text read:** `read_*_paper` MCP tools, or `pdfplumber` / `pymupdf`
(`~/.claude/skill_venv/bin/`) on the downloaded PDFs for text extraction.
