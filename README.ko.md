<h1 align="center">scholar-megasearch</h1>

<p align="center">
  <strong>Claude Code를 위한 대규모 멀티소스 학술 논문 검색.</strong><br>
  <em>20개 이상의 학술 DB에 서브에이전트를 팬아웃해, 모든 결과를 하나의 중복제거된 코퍼스로 병합하고 원본 PDF까지 확보하는 단일 스킬.</em>
</p>

<p align="center">
  <a href="./README.md">English README</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/SKILL.md">SKILL.md</a>
  &nbsp;·&nbsp;
  <a href="./skills/scholar-megasearch/references/sources.md">소스 카탈로그</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="License">
  <img src="https://img.shields.io/github/stars/TaewoooPark/scholar-megasearch?style=flat-square&logo=github&logoColor=white&labelColor=000000&color=333333&cacheSeconds=3600" alt="GitHub stars">
  <img src="https://img.shields.io/github/last-commit/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="Last commit">
  <img src="https://img.shields.io/github/languages/top/TaewoooPark/scholar-megasearch?style=flat-square&labelColor=000000&color=333333&cacheSeconds=3600" alt="Top language">
  &nbsp;
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

## 무엇인가

`scholar-megasearch`는 단일 Claude Code 스킬 **scholar-megasearch**와, 그것을 구동하는
데 필요한 보조 스킬·MCP 서버를 하나로 묶은 패키지다. DB를 하나씩 조회하는 대신,
주제를 여러 facet으로 분해하고 각 **소스 버킷**을 독립 서브에이전트에 할당해 병렬로
팬아웃한다. 모든 검색 결과는 하나의 스키마로 정규화되어 DOI → arXiv-id → 정규화 제목
순으로 중복제거되고, 여러 DB가 함께 잡아낸 정도(corroboration)로 랭킹되어 인용 가능한
리포트로 합성된다. 상위 논문들은 무료·합법 경로로 **원본 PDF**까지 확보한다.

핵심은 출처 추적이 동반된 넓은 커버리지다. "찾은 논문 5편"이 아니라, 각 항목이 어떤
DB에서 나왔는지 기록된 단일 랭킹 코퍼스와 디스크에 저장된 PDF를 얻는다.

## 동작 방식

```
주제
  │  3~8개 facet 서브쿼리로 분해
  ▼
┌─────────────────────────────────────────────────────────────┐
│  팬아웃 — 소스 버킷당 서브에이전트 1개 (병렬)                  │
│                                                               │
│  A arXiv        B Semantic Scholar   C Crossref / OpenAlex    │
│  D PubMed/PMC   E DOAJ·CORE·BASE     F DBLP·IACR·SSRN         │
│  G 웹 / GitHub / 회색문헌                                     │
└─────────────────────────────────────────────────────────────┘
  │  각자 raw/<bucket>.json 작성  (중복제거 안 함)
  ▼
merge_corpus.py   →  중복제거(DOI→arXiv→제목) + 병합 + 랭킹  →  corpus.json / corpus.md
  ▼
fetch_pdfs.py     →  pdf_url → arXiv → Unpaywall OA → MCP 폴백  →  pdfs/ + manifest.json
  ▼
합성              →  summary.md  (테마 · 핵심 · 최신 · 공백)
```

오케스트레이션은 가능할 때 결정론적 **Workflow**로 실행되고, 그렇지 않으면 직접
**Agent** 팬아웃으로 폴백한다. 도메인 → 버킷 라우팅 표가 주제(물리·생명과학·CS·암호학·
경제학·수학·학제간)에 맞는 4~7개 버킷을 자동 선택한다.

## 번들 구성

| 경로 | 역할 |
|------|------|
| `skills/scholar-megasearch/` | 오케스트레이션 스킬 — `SKILL.md`, 소스 카탈로그, 오케스트레이션 템플릿, 검증된 스크립트 3종(`merge_corpus.py`, `fetch_pdfs.py`, `search_local.py`). |
| `skills/arxiv-search/` | 보조 스킬 — venv 기반 arXiv / Semantic Scholar / DuckDuckGo 검색 패턴. |
| `skills/semantic-scholar-mcp/` | Semantic Scholar MCP 서버 (벤더링 — [출처](#출처-attribution) 참조). |
| `setup/install.sh` | 스킬 설치, venv 빌드, MCP 서버 3종 설치, 해석된 MCP 설정 출력. |
| `setup/requirements.txt` | 검색/획득 venv의 고정 버전 Python 의존성. |
| `setup/mcp.servers.json` | `~/.claude.json`용 MCP 서버 등록 템플릿. |

pip/uvx로 설치 가능한 MCP 서버(`paper-search-mcp`, `arxiv-mcp-server`)는 벤더링하지
않고, 설치 스크립트가 고정/검증된 버전으로 소스에서 재구성한다.

## 설치

```bash
git clone https://github.com/TaewoooPark/scholar-megasearch.git
cd scholar-megasearch
bash setup/install.sh you@example.com      # Unpaywall OA + arXiv 예의용 이메일
```

스크립트는 스킬을 `~/.claude/skills/`에 설치하고, `~/.claude/skill_venv`와
`~/.claude/paper_search_mcp_venv`를 빌드하며, `paper-search-mcp`를 git main에서
설치하고(PyPI 빌드는 Crossref/OpenAlex 미포함), `setup/mcp.servers.resolved.json`을
생성한다. 그 파일의 `mcpServers` 항목을 `~/.claude.json`에 병합한 뒤 Claude Code를
재시작하면 된다.

> Python 3.11+ 와 [`uv`](https://astral.sh/uv) 필요 (`uvx arxiv-mcp-server`용).

## 사용법

Claude Code 안에서 자연어로 스킬을 트리거한다:

```
도메인월 측정 논문 방대하게 검색해줘, PDF까지
spin–orbit torque switching 모든 DB에서 다 찾고 PDF까지 받아줘
```

또는 스크립트를 직접 실행:

```bash
# 소스별 결과 파일을 하나의 랭킹 코퍼스로 병합
python3 ~/.claude/skills/scholar-megasearch/scripts/merge_corpus.py \
  ./literature_search/<주제>_<날짜>/raw \
  -o corpus.json --md corpus.md --min-sources 2

# 상위 25편 원본 PDF 확보
python3 ~/.claude/skills/scholar-megasearch/scripts/fetch_pdfs.py \
  corpus.json -o ./pdfs --email you@example.com --top 25
```

## 산출물

모든 결과는 작업 디렉토리의 `./literature_search/<주제>_<날짜>/` 아래에 저장된다:

```
literature_search/<주제>_<날짜>/
├── raw/<bucket>.json     # 소스별 검색 결과 (서브에이전트당 1파일)
├── corpus.json           # 중복제거·랭킹·출처추적 코퍼스
├── corpus.md             # 사람이 읽는 다이제스트
├── pdfs/                  # 확보한 원본 PDF + manifest.json
└── summary.md            # 합성 리뷰
```

## 소스 버킷

| 버킷 | DB |
|--------|-----------|
| A · 프리프린트 | arXiv (검색 · 시맨틱 · 인용 그래프) |
| B · 인용 | Semantic Scholar (2억+, 인용수) |
| C · DOI / 출판본 | Crossref, OpenAlex |
| D · 생명과학 | PubMed, PMC, bioRxiv, medRxiv, Europe PMC |
| E · 오픈액세스 | DOAJ, CORE, BASE, OpenAIRE, Zenodo, Unpaywall, HAL |
| F · 도메인 특화 | DBLP (CS), IACR (암호), SSRN (경제/법), CiteSeerX |
| G · 웹 | DuckDuckGo, GitHub, crawl4ai / firecrawl |

버킷별 전체 도구 목록과 도메인 → 버킷 라우팅 표는
[`skills/scholar-megasearch/references/sources.md`](./skills/scholar-megasearch/references/sources.md)에 있다.

## 출처 (Attribution)

- **semantic-scholar-mcp**는
  [JackKuo666/semanticscholar-MCP-Server](https://github.com/JackKuo666/semanticscholar-MCP-Server)에서
  벤더링했으며 상위 저장소의 README를 유지한다.
- **paper-search-mcp** ([openags/paper-search-mcp](https://github.com/openags/paper-search-mcp))와
  **arxiv-mcp-server**는 `setup/install.sh`가 상위 소스에서 설치한다.

이 저장소의 원본 작업(`scholar-megasearch`·`arxiv-search` 스킬과 설치 스크립트)은
[MIT License](./LICENSE)로 배포된다.
