<h1 align="center">scholar-megasearch</h1>

<p align="center">
  <strong>Massive multi-source academic literature search for Claude Code and Codex.</strong><br>
  <em>One skill that fans out subagents across 20+ scholarly databases, merges everything into a single deduplicated corpus, and acquires the original PDFs.</em>
</p>

<p align="center">
  <a href="./README.ko.md">한국어 README</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/SKILL.md">SKILL.md</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/references/sources.md">Source catalog</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/references/orchestration.md">Orchestration</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="License">
  <img src="https://img.shields.io/github/stars/TaewoooPark/scholar-megasearch?style=flat-square&logo=github&logoColor=white&labelColor=000000&color=333333&cacheSeconds=3600" alt="GitHub stars">
  <img src="https://img.shields.io/github/last-commit/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="Last commit">
  <img src="https://img.shields.io/github/languages/top/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="Top language">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude%20Code-000000?style=flat-square&logo=anthropic&logoColor=white&labelColor=000000&cacheSeconds=3600" alt="Claude Code">
  <img src="https://img.shields.io/badge/OpenAI%20Codex-000000?style=flat-square&logo=openai&logoColor=white&labelColor=000000&cacheSeconds=3600" alt="OpenAI Codex">
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

---

> **One sentence:** ask Claude Code or Codex for a topic, and get back a single ranked,
> deduplicated, provenance-tracked corpus of papers — with the PDFs already on disk.

- 🔭 **20+ databases in one pass** — arXiv, Semantic Scholar, Crossref, OpenAlex, PubMed/PMC, bioRxiv/medRxiv, DOAJ, CORE, BASE, OpenAIRE, Zenodo, Unpaywall, HAL, DBLP, IACR, SSRN, CiteSeerX, Europe PMC, plus web/GitHub.
- 🧵 **Subagent fan-out** — one searcher per source bucket, running in parallel, so breadth doesn't cost you serial wall-clock.
- 🧹 **Dedup with provenance** — merged by DOI → arXiv-id → normalized title; every paper records *which* databases surfaced it.
- 📊 **Corroboration ranking** — papers found by more independent databases rank higher, not just the ones with good SEO.
- 📄 **Original PDFs** — top-K acquired automatically via open-access routes, with a manifest of what landed and what needs a paywall fallback.
- 🧭 **Domain-aware routing** — physics, life sciences, CS, crypto, economics, or math each pull the right subset of databases.

## Why It Exists

Searching one database at a time is how good papers get missed. arXiv won't show
you the published version's citation count; Semantic Scholar won't surface the
bioRxiv preprint; Google Scholar won't tell you which of its hits also appear in
three other indexes. So you end up running the same query in five tabs, copy-pasting
into a doc, hand-deduplicating, and then hunting each PDF down separately.

`scholar-megasearch` collapses that into one request. It treats "search the
literature" as a fan-out problem: decompose the topic, send each **source bucket** to
its own subagent, and reconcile everything afterward. The output isn't a chat reply —
it's a corpus on disk where every entry is deduplicated, ranked by how many
independent databases corroborate it, and backed by a downloaded PDF wherever a free
route exists.

## How It Works

<p align="center">
  <img src="./docs/pipeline.png" width="900" alt="scholar-megasearch pipeline: topic → decompose into facets → fan out one subagent per source bucket → merge_corpus.py (dedup + rank) → fetch_pdfs.py → synthesize">
</p>

Orchestration runs as a deterministic **Workflow** when available, and falls back to
direct **Agent/subagent** fan-out otherwise. A domain → bucket routing table picks the
right 4–7 buckets per topic.

### Dedup & ranking

Records from different databases are merged when they share **any** of: a normalized
DOI, an arXiv id (version-stripped), or a normalized title. The merged record keeps
the richest value per field — the longest abstract, the most complete author list,
the maximum citation count — and accumulates the **set of sources** that found it.
Ranking is then `(number of sources, citation count, year)`, descending. Pass
`--min-sources 2` to keep only papers corroborated by two or more databases — a
high-precision shortlist that filters out single-index noise.

### A typical run

A mid-depth sweep (≈ **L3 Deep**) on a focused topic looks roughly like this *(illustrative)*:

```
topic: "graph neural networks for molecular property prediction"
  facets:  6 subqueries        buckets: A B C E G (5 searchers)
  raw hits: ~310 across buckets
  unique:   ~150 after dedup   (≈60 corroborated by ≥2 databases)
  PDFs:     22 / 25 acquired   (3 flagged needs_mcp — paywalled)
  output:   ./literature_search/gnn-molecular-property_2026-05-29/
```

## Install

```bash
git clone https://github.com/TaewoooPark/scholar-megasearch.git
cd scholar-megasearch

# Claude Code (default, backwards-compatible)
bash setup/install.sh you@example.com

# Codex
bash setup/install.sh --target codex --email you@example.com

# Both hosts
bash setup/install.sh --target both --email you@example.com

# If your default python3 is too new/old, pin the venv interpreter explicitly
PYTHON_BIN=python3.11 bash setup/install.sh --target codex --email you@example.com
```

The installer preserves the original Claude Code behavior by default. For Claude Code,
it installs skills into `~/.claude/skills/`, builds `~/.claude/skill_venv` and
`~/.claude/paper_search_mcp_venv`, and writes `setup/mcp.servers.resolved.json` for
`~/.claude.json`.

For Codex, it installs personal skills into `$HOME/.agents/skills` by default, builds
the search venvs under `${CODEX_HOME:-~/.codex}`, and writes
`setup/mcp.servers.codex.resolved.toml` for `~/.codex/config.toml`. If the `codex`
CLI is available, add `--register-codex-mcp` to have the installer run `codex mcp add`
for `arxiv-mcp-server`, `asta`, and `paper-search-mcp`.

Both hosts use `paper-search-mcp` from git main — the PyPI build lacks
Crossref/OpenAlex — plus `arxiv-mcp-server` via `uvx`. Semantic Scholar (Bucket B) is
the **remote** [Ai2 Asta MCP](https://allenai.org/asta/resources/mcp): nothing to
install, and it works **without a key** (rate-limited). For higher rate limits, request
a free key and add a literal `x-api-key` header to the `asta` entry. Asta use is
subject to Ai2's terms (see [Attribution](#attribution)).

**Requirements**

| | |
|---|---|
| Python | 3.11+ |
| [`uv`](https://astral.sh/uv) | for `uvx arxiv-mcp-server` |
| `git` | `pip install` of `paper-search-mcp` (git main) at install time |
| Claude Code or Codex | the skill is triggered from within a session |

## Usage

Inside Claude Code or Codex, trigger the skill in natural language:

```
search every database for graph neural networks and grab the PDFs
do a massive literature search on mixture-of-experts routing from the last year, with PDFs
```

The skill also understands trigger phrases in other languages, so a request written in,
say, Korean or Japanese routes to the same pipeline.

If the request is underspecified, the skill asks a short mini-survey before fan-out:
**field**, **goal**, and numeric **depth 1–5**. The same plan can be generated from a
terminal:

```bash
python3 ~/.claude/skills/scholar-megasearch/scripts/plan_run.py \
  "graph neural networks" --field cs-ml --goal survey --depth 3
```

Or invoke it as a **slash command**, optionally pinning the depth level (see
[Depth levels](#depth-levels)) — prepend `depth=N`, `LN`, or a bare `1–5`, or use a
phrase like `quick` / `exhaustive`. Everything after the command is the topic:

```
/scholar-megasearch depth=4 graph neural networks for molecular property prediction
/scholar-megasearch L5 CRISPR-Cas9 off-target prediction methods   # L5 = grab every source's PDFs
/scholar-megasearch quick first look at retrieval-augmented generation
/scholar-megasearch exhaustive measurement of topological insulator surface states  # → L5
/scholar-megasearch mixture-of-experts routing papers from the last year   # no level → defaults to L2
```

Or run the scripts directly:

```bash
# merge per-source result files into one ranked corpus
python3 ~/.claude/skills/scholar-megasearch/scripts/merge_corpus.py \
  ./literature_search/<topic>_<date>/raw \
  -o corpus.json --md corpus.md --min-sources 2 \
  --goal survey --topic "graph neural networks"

# recover partial results when MCP sources are unavailable
python3 ~/.claude/skills/scholar-megasearch/scripts/resilient_search.py \
  "graph neural networks" --sources arxiv,semanticscholar,ddg \
  -o raw/local_recovery.json --status raw/local_recovery.status.json

# acquire original PDFs for the top 25 ranked papers
python3 ~/.claude/skills/scholar-megasearch/scripts/fetch_pdfs.py \
  corpus.json -o ./pdfs --email you@example.com --top 25

# Codex default script path is:
# ~/.agents/skills/scholar-megasearch/scripts/
```

### Depth levels

One knob scales **breadth** (facets × buckets × hits per query) and **recursion**
(extra waves) together. Pick a level per run — an explicit `depth=N` / `LN` / bare
`1–5` wins; otherwise it's inferred from phrasing (`quick` → L1 …
`every source` / `exhaustive` → L5, including equivalent phrases in other
languages); otherwise it defaults to **L2**.

| Level | Facets | Buckets | Hits/query | Waves | PDFs | Output |
|-------|:------:|:-------:|:----------:|-------|:----:|--------|
| **L1 · Quick** | 3 | 4 | 15 | wave 1 only | top 10 | corpus |
| **L2 · Standard** *(default)* | 5 | 5 | 25 | wave 1 only | top 30 | corpus |
| **L3 · Deep** | 6 | 6 | 30 | + citation snowball | top 50 | corpus |
| **L4 · Exhaustive** | 8 | 7 (all) | 40 | + snowball + completeness-critic pass | top 100 | corpus + ≥2 shortlist |
| **L5 · Total** (Exhaustive) | 8 | 7 (all) | 40 | + snowball + critic loop-until-dry | all sources | corpus + ≥2 shortlist |

Each wave is a fan-out followed by a merge into the *same* corpus: the **citation
snowball** (L3+) seeds the top DOIs/arXiv ids back through citation graphs; the
**completeness-critic** (L4+) names missing subtopics/authors that become the next
wave's facets, looped until dry at L5. L4/L5 also emit a `--min-sources 2` shortlist.
Higher levels spawn more subagents and cost more tokens — L5 is bounded only by the
token budget. **PDF acquisition scales with the level too** — `fetch_pdfs.py --top` of
10 / 30 / 50 / 100, and `all` (the whole corpus) at L5.

### Ranking

The default merge ranking is a five-layer weighted score: provenance, impact,
recency, access/completeness, and topic relevance. Goal profiles (`survey`,
`systematic`, `newest`, `seminal`, `implementation`, `pdf-corpus`) shift the layer
weights while keeping the signals separate. Use `--ranking classic` to reproduce the
older `sources_count, citations, year` sort.

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

PDFs are named `NN_<slug>.pdf` by their `corpus.json` rank, and `summary.md` numbers each
paper `[#NN]` with the same rank — so a summary entry maps directly to its `pdfs/NN_*.pdf`
file and its `manifest.json` row.

## Source Buckets

| Bucket | Databases |
|--------|-----------|
| A · Preprints | arXiv (search · semantic · citation graph) |
| B · Citations | Semantic Scholar via **Ai2 Asta** (official MCP) + paper-search-mcp |
| C · DOI / published | Crossref, OpenAlex |
| D · Life sciences | PubMed, PMC, bioRxiv, medRxiv, Europe PMC |
| E · Open access | DOAJ, CORE, BASE, OpenAIRE, Zenodo, Unpaywall, HAL |
| F · Domain | DBLP (CS), IACR (crypto), SSRN (econ/law), CiteSeerX |
| G · Web | DuckDuckGo, GitHub, crawl4ai / firecrawl |
| H · Korean (opt-in) | KISTI ScienceON — KCI-indexed papers, domestic R&D reports, patents *(needs credentials)* |

### Domain → bucket routing

| Topic domain | Always | Plus |
|---|---|---|
| Physics / materials / cond-mat | A · B · C | E · G |
| CS / ML / systems | A · B · F (DBLP) | C · G (GitHub) |
| Biology / medicine / neuro | D · B · C | E |
| Cryptography / security | A · F (IACR) · B | G (GitHub) |
| Economics / social science / law | F (SSRN) · B · C | G |
| Math | A · B · C | F |
| Interdisciplinary / unknown | A · B · C · D | E · G |
| Korean-language / domestic (KCI, R&D, policy) | H · C · B | E · G |

**Bucket H — KISTI ScienceON** is an opt-in Korean-language source covering KCI-indexed
journal papers, domestic R&D reports, and Korean patents — the blind spot the other
(English-centric) buckets leave. It activates only when `KISTI_CLIENT_ID` /
`KISTI_AUTH_KEY` / `KISTI_MAC` are set (spec:
[`references/kisti.md`](./skills/scholar-megasearch/references/kisti.md)); runs without
those credentials simply skip it. Merge dedup is Unicode-aware, so DOI-less Korean
records survive on their Hangul title. Route it for Korean-language or domestic-trend
queries, and narrow it with `KISTI_TARGET=arti,report,patent`.

Full per-bucket tool lists are in
[`skills/scholar-megasearch/references/sources.md`](./skills/scholar-megasearch/references/sources.md);
the orchestration templates (Workflow + Agent fan-out) and the record schema are in
[`references/orchestration.md`](./skills/scholar-megasearch/references/orchestration.md).

## Repository Layout

```
scholar-megasearch/
├── README.md · README.ko.md · LICENSE
├── setup/
│   ├── install.sh            # skills + venvs + MCP servers + resolved config
│   ├── requirements.txt      # pinned search/acquisition deps
│   ├── mcp.servers.json          # MCP template for ~/.claude.json
│   └── mcp.servers.codex.toml    # MCP template for ~/.codex/config.toml
└── skills/
    ├── scholar-megasearch/   # the skill
    │   ├── SKILL.md
    │   ├── references/{sources.md, orchestration.md}
    │   └── scripts/{merge_corpus.py, fetch_pdfs.py, search_local.py}
    └── arxiv-search/          # supporting venv-search skill
```

This repository contains only original MIT-licensed work (the two skills and the
setup scripts). The third-party MCP servers are **not** vendored — `setup/install.sh`
fetches the local ones (arxiv-mcp-server, paper-search-mcp) from upstream at install
time, and Semantic Scholar is the remote Ai2 Asta service. See [Attribution](#attribution).

## Notes & Limitations

- **PDF acquisition is open-access-first.** `fetch_pdfs.py` only uses free/legal
  routes (a known OA `pdf_url`, arXiv, Unpaywall) and verifies every file is a real
  `%PDF-`. Closed-access papers are flagged `needs_mcp` in the manifest; fetching
  those is left to the session's MCP download tools.
- **arXiv rate-limits heavy fan-out** (HTTP 429). Searchers stagger and lean on
  Semantic Scholar / OpenAlex when arXiv pushes back.
- **`paper-search-mcp` must be the git-main build** — the PyPI release omits
  Crossref and OpenAlex. The installer handles this.
- **Host-specific scholar gateways are best-effort** — they may be absent in
  headless/cron runs, so they are never a bucket's only source.
- **Honest synthesis.** `summary.md` reports what was actually searched and which
  sources failed; nothing is invented to fill a gap.

## Attribution

The MCP servers are third-party — installed from their upstream sources by
`setup/install.sh`, or (for Asta) used as a remote service. None of their code is
redistributed here:

- **Ai2 Asta Scientific Corpus Tool** — the official Semantic Scholar MCP by the
  [Allen Institute for AI](https://allenai.org/asta/resources/mcp), used as a remote
  service under Ai2's [Asta License Agreement](https://allenai.org/asta-corpus-license)
  and [Terms of Use](https://allenai.org/terms) (no code vendored).
- **paper-search-mcp** — [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp) (pip install from git main)
- **arxiv-mcp-server** — launched on demand via `uvx`

**Semantic Scholar data** returned through Asta is licensed **ODC-BY** and governed by the
[Semantic Scholar API license](https://www.semanticscholar.org/product/api/license): when
you publish results built on it, **attribute Semantic Scholar** (link back to
semanticscholar.org) and do **not** redistribute, sell, or sublicense the raw data.
Individual papers/abstracts may carry their own licenses (e.g. CC BY-NC).

Original work in this repository (the `scholar-megasearch` and `arxiv-search` skills
and the setup scripts) is released under the [MIT License](./LICENSE) — this covers our
code only, not the third-party services or the data they return.
