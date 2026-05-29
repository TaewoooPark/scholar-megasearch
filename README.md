<h1 align="center">scholar-megasearch</h1>

<p align="center">
  <strong>Massive multi-source academic literature search for Claude Code.</strong><br>
  <em>One skill that fans out subagents across 20+ scholarly databases, merges everything into a single deduplicated corpus, and acquires the original PDFs.</em>
</p>

<p align="center">
  <a href="./README.ko.md">한국어 README</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/SKILL.md">SKILL.md</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/references/sources.md">Source catalog</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="License">
  <img src="https://img.shields.io/github/stars/TaewoooPark/scholar-megasearch?style=flat-square&logo=github&logoColor=white&labelColor=000000&color=333333&cacheSeconds=3600" alt="GitHub stars">
  <img src="https://img.shields.io/github/last-commit/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="Last commit">
  <img src="https://img.shields.io/github/languages/top/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="Top language">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude%20Code-000000?style=flat-square&logo=anthropic&logoColor=white&labelColor=000000&cacheSeconds=3600" alt="Claude Code">
  <img src="https://img.shields.io/badge/Skill%20%2B%20MCP-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="Skill plus MCP">
  <img src="https://img.shields.io/badge/Python-000000?style=flat-square&logo=python&logoColor=white&labelColor=000000&cacheSeconds=3600" alt="Python">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/arXiv-000000?style=flat-square&logo=arxiv&logoColor=white&labelColor=000000&cacheSeconds=3600" alt="arXiv">
  <img src="https://img.shields.io/badge/Semantic%20Scholar-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="Semantic Scholar">
  <img src="https://img.shields.io/badge/Crossref-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="Crossref">
  <img src="https://img.shields.io/badge/OpenAlex-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="OpenAlex">
  <img src="https://img.shields.io/badge/PubMed%20%2F%20PMC-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="PubMed and PMC">
  <img src="https://img.shields.io/badge/Unpaywall-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="Unpaywall">
  <img src="https://img.shields.io/badge/DOAJ%20%C2%B7%20CORE%20%C2%B7%20BASE-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="DOAJ, CORE, BASE">
  <img src="https://img.shields.io/badge/DBLP%20%C2%B7%20IACR%20%C2%B7%20SSRN-000000?style=flat-square&labelColor=000000&color=000000&cacheSeconds=3600" alt="DBLP, IACR, SSRN">
</p>

## What It Is

`scholar-megasearch` packages a single Claude Code skill — **scholar-megasearch** —
together with the supporting skills and MCP servers it needs to run. Instead of
querying one database at a time, it decomposes a topic into facets, assigns each
**source bucket** to its own subagent, and fans them out in parallel. Every hit is
normalized into one schema, deduplicated by DOI → arXiv-id → normalized title,
ranked by cross-database corroboration, and synthesized into a cited report. The
top-ranked papers are then acquired as **original PDFs** through free/legal routes.

The point is breadth with provenance: instead of "here are five papers I found",
you get a single ranked corpus where every entry records which databases surfaced
it, with the PDFs on disk.

## How It Works

```
topic
  │  decompose into 3–8 facet subqueries
  ▼
┌─────────────────────────────────────────────────────────────┐
│  fan out — one subagent per source bucket (parallel)          │
│                                                               │
│  A arXiv        B Semantic Scholar   C Crossref / OpenAlex    │
│  D PubMed/PMC   E DOAJ·CORE·BASE     F DBLP·IACR·SSRN         │
│  G web / GitHub / grey literature                             │
└─────────────────────────────────────────────────────────────┘
  │  each writes raw/<bucket>.json   (no dedup)
  ▼
merge_corpus.py   →  dedup (DOI→arXiv→title) + merge + rank  →  corpus.json / corpus.md
  ▼
fetch_pdfs.py     →  pdf_url → arXiv → Unpaywall OA → MCP fallback  →  pdfs/ + manifest.json
  ▼
synthesize        →  summary.md  (themes · seminal · frontier · gaps)
```

Orchestration runs as a deterministic **Workflow** when available, and falls back
to direct **Agent** fan-out otherwise. A domain → bucket routing table picks the
right 4–7 buckets per topic (physics, life sciences, CS, cryptography, economics,
math, or interdisciplinary).

## What's Bundled

| Path | Role |
|------|------|
| `skills/scholar-megasearch/` | The orchestration skill — `SKILL.md`, source catalog, orchestration templates, and three tested scripts (`merge_corpus.py`, `fetch_pdfs.py`, `search_local.py`). |
| `skills/arxiv-search/` | Supporting skill — venv-based arXiv / Semantic Scholar / DuckDuckGo search patterns. |
| `skills/semantic-scholar-mcp/` | The Semantic Scholar MCP server (vendored — see [Attribution](#attribution)). |
| `setup/install.sh` | Installs skills, builds the venvs, installs all three MCP servers, emits a resolved MCP config. |
| `setup/requirements.txt` | Pinned Python deps for the search/acquisition venv. |
| `setup/mcp.servers.json` | MCP server registration template for `~/.claude.json`. |

MCP servers that are pip/uvx-installable (`paper-search-mcp`, `arxiv-mcp-server`)
are reconstituted from source by the installer with pinned/known-good versions,
rather than vendored.

## Install

```bash
git clone https://github.com/TaewoooPark/scholar-megasearch.git
cd scholar-megasearch
bash setup/install.sh you@example.com      # email used for Unpaywall OA + arXiv politeness
```

The script installs the skills into `~/.claude/skills/`, builds
`~/.claude/skill_venv` and `~/.claude/paper_search_mcp_venv`, installs
`paper-search-mcp` from git main (the PyPI build lacks Crossref/OpenAlex), and
writes `setup/mcp.servers.resolved.json`. Merge that file's `mcpServers` entries
into `~/.claude.json` and restart Claude Code.

> Requires Python 3.11+ and [`uv`](https://astral.sh/uv) (for `uvx arxiv-mcp-server`).

## Usage

Inside Claude Code, trigger the skill in natural language:

```
search every database for spin–orbit torque switching and grab the PDFs
MoE 관련 최근 1년 논문 방대하게 검색해줘, PDF까지
```

Or run the scripts directly:

```bash
# merge per-source result files into one ranked corpus
python3 ~/.claude/skills/scholar-megasearch/scripts/merge_corpus.py \
  ./literature_search/<topic>_<date>/raw \
  -o corpus.json --md corpus.md --min-sources 2

# acquire original PDFs for the top 25 ranked papers
python3 ~/.claude/skills/scholar-megasearch/scripts/fetch_pdfs.py \
  corpus.json -o ./pdfs --email you@example.com --top 25
```

## Outputs

Everything lands under `./literature_search/<topic>_<date>/` in the working directory:

```
literature_search/<topic>_<date>/
├── raw/<bucket>.json     # per-source hits (one file per subagent)
├── corpus.json           # deduplicated, ranked, provenance-tracked corpus
├── corpus.md             # human-readable digest
├── pdfs/                  # acquired original PDFs + manifest.json
└── summary.md            # synthesized review
```

## Source Buckets

| Bucket | Databases |
|--------|-----------|
| A · Preprints | arXiv (search · semantic · citation graph) |
| B · Citations | Semantic Scholar (200M+, citation counts) |
| C · DOI / published | Crossref, OpenAlex |
| D · Life sciences | PubMed, PMC, bioRxiv, medRxiv, Europe PMC |
| E · Open access | DOAJ, CORE, BASE, OpenAIRE, Zenodo, Unpaywall, HAL |
| F · Domain | DBLP (CS), IACR (crypto), SSRN (econ/law), CiteSeerX |
| G · Web | DuckDuckGo, GitHub, crawl4ai / firecrawl |

Full per-bucket tool lists and the domain → bucket routing table are in
[`skills/scholar-megasearch/references/sources.md`](./skills/scholar-megasearch/references/sources.md).

## Attribution

- **semantic-scholar-mcp** is vendored from
  [JackKuo666/semanticscholar-MCP-Server](https://github.com/JackKuo666/semanticscholar-MCP-Server)
  and retains its upstream README.
- **paper-search-mcp** ([openags/paper-search-mcp](https://github.com/openags/paper-search-mcp))
  and **arxiv-mcp-server** are installed from their upstream sources by `setup/install.sh`.

Original work in this repository (the `scholar-megasearch` and `arxiv-search` skills and
the setup scripts) is released under the [MIT License](./LICENSE).
