# Source catalog & domain routing

All search/read/download capabilities available in this environment, grouped into
**buckets** that map cleanly onto one subagent each. A megasearch assigns 1 bucket
per agent so they fan out without overlapping or rate-limiting each other.

Most tools are **deferred** — load schemas with the host's tool discovery before calling
(`ToolSearch` in Claude Code, `tool_search` in Codex), e.g. ask for
`paper-search-mcp search_pubmed search_crossref`. Inside a Workflow, agents load their
own schemas via host tool discovery automatically.

## Bucket A — arXiv (preprints, physics/CS/math)
`arxiv-mcp-server`: `search_papers`, `semantic_search`, `get_abstract`,
`download_paper`, `read_paper`, `citation_graph`, `list_papers`.
- `search_papers` — boolean field queries (`ti:`, `au:`, `abs:`, `cat:`).
- `semantic_search` — natural-language similarity.
- `citation_graph` — forward/backward citations from a seed arXiv id (snowballing).
Fallback: `scripts/search_local.py arxiv "query"`.
Recovery ladder: `scripts/resilient_search.py "query" --sources arxiv,semanticscholar,ddg`
when MCP search fails or arXiv rate-limits.

## Bucket B — Semantic Scholar via Ai2 Asta (200M+ papers, citation counts)
`asta` — Ai2 **Asta Scientific Corpus Tool**, the official Semantic Scholar MCP (remote
HTTP `https://asta-tools.allen.ai/mcp/v1`; rate-limit + pagination handled server-side):
`search_papers_by_relevance`, `search_paper_by_title`, `snippet_search` (full-text
excerpts), `get_paper`, `get_citations` (forward cited-by — use for the snowball wave),
`get_author_papers`, `search_authors_by_name`. Also `paper-search-mcp`: `search_semantic`,
`read_semantic_paper`, `download_semantic`. Best source for **citation counts** → ranking
and for finding the canonical version of a preprint. Fallback:
`scripts/search_local.py semanticscholar "query"`.
Recovery ladder: fall back to `resilient_search.py` with `semanticscholar,arxiv,ddg`.

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
`scripts/resilient_search.py "query" --sources ddg` retries and writes status for grey-lit
fallback runs.
`crawl4ai` (`<host-skill-venv>/bin/crwl "URL" -o markdown`) or the `firecrawl-*`
skills to scrape a specific page → markdown. `WebSearch`/`WebFetch` as generic fallback.
`mcp__github__search_repositories` / `search_code` for code/datasets behind a method.

## Bucket H — 국내 / Korean (KISTI ScienceON)
`scripts/search_local.py kisti "질의"` — KISTI ScienceON OpenAPI를 통해 **국내 한국어
문헌**을 검색한다. target 3종을 한 번에(기본) 또는 `KISTI_TARGET` 환경변수로 한정:
- `arti` — KCI 등재 한국어 논문 + 국내 학술지/회의록 (KCI 99% 커버리지)
- `report` — 국내 R&D 보고서
- `patent` — 국내 특허
인증은 환경변수 `KISTI_CLIENT_ID` / `KISTI_AUTH_KEY` / `KISTI_MAC` 필요(`references/kisti.md`).
영어권 주제에는 중복만 늘므로 **국내 동향·한국어 1차 문헌이 필요할 때만** 라우팅한다.
구현·필드 매핑: `scripts/kisti_client.py`, 스펙 SSOT: `references/kisti.md`.

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
| 국내 동향 / 한국어 문헌 / KCI / 국내 R&D·정책 | H, C, B | E, G |

Bucket H(KISTI)는 한국어 질의에서 가장 강하다 — 한국어 facet을 최소 1개 포함해 fan-out하라.

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
from the installed host venv on the downloaded PDFs for text extraction.
