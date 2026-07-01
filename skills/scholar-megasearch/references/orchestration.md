# Orchestration: Workflow (preferred) and Agent fan-out (fallback)

## Record schema (every searcher returns this)

Subagents return a JSON list of records. All fields optional except a `title`.
`source` and `query` are required so `merge_corpus.py` can track provenance.

```json
{ "title": "...", "authors": ["..."], "year": 2024, "venue": "...",
  "doi": "10.x/y", "arxiv_id": "2401.00001", "pdf_url": "...", "url": "...",
  "citations": 0, "abstract": "...", "source": "pubmed", "query": "the subquery" }
```

A searcher agent's job: take its assigned bucket + the facet subqueries, run each
query through its bucket's tools (load schemas via the host's tool discovery first),
normalize hits
into the schema, and **write one JSON file** to `<run>/raw/<bucket>.json`. It must NOT
dedupe or rank — that is `merge_corpus.py`'s job.

## Preferred: Workflow tool (requires "workflow" opt-in)

Use this when the user opted into workflows. Buckets fan out, each searcher writes its
raw file, then a single merge + synthesis. Searcher agents reach MCP tools via the
host's tool discovery (`ToolSearch` in Claude Code, `tool_search` in Codex).
The merge runs as a Bash step after the workflow returns (workflow agents have no shared
FS guarantees for the script) — so have each agent RETURN its records too, via schema.

```js
export const meta = {
  name: 'scholar-megasearch',
  description: 'Fan out academic search across source buckets, merge into one corpus',
  phases: [{ title: 'Search' }, { title: 'Synthesize' }],
}
// args = { topic, field, goal, depth, facets: ["subquery 1", ...],
//          buckets: [{key, prompt}, ...], cap?: 30,
//          seeds?: ["10.x/y", "arXiv:2401.00001"] }
// One wave per call. cap = hits/subquery (set by the depth level, SKILL.md). When seeds is
// non-empty this is a CITATION-SNOWBALL wave (L3+): searchers expand the seeds' citations
// instead of running facet queries. The main loop chains waves and runs merge_corpus.py
// (Bash) between them — initial (all) → snowball (L3+) → critic-driven (L4+, looped at L5).
const REC_SCHEMA = {
  type: 'object', required: ['results'],
  properties: { results: { type: 'array', items: { type: 'object',
    properties: {
      title:{type:'string'}, authors:{type:'array',items:{type:'string'}},
      year:{type:'integer'}, venue:{type:'string'}, doi:{type:'string'},
      arxiv_id:{type:'string'}, pdf_url:{type:'string'}, url:{type:'string'},
      citations:{type:'integer'}, abstract:{type:'string'},
      source:{type:'string'}, query:{type:'string'} } } } } }

phase('Search')
const CAP = args.cap || 30
const snowball = Array.isArray(args.seeds) && args.seeds.length > 0
const task = snowball
  ? `\n\nThis is a CITATION-SNOWBALL wave. For EACH seed below, pull its forward (cited-by) ` +
    `and backward (references) neighbours via your citation tools (asta get_citations, ` +
    `arXiv citation_graph, OpenAlex cited-by):\n` +
    args.seeds.map((s, i) => `  ${i + 1}. ${s}`).join('\n') +
    `\n\nSet "query" to "snowball:<seed>" on every record.`
  : `\n\nRun EACH of these subqueries through your tools and collect hits:\n` +
    args.facets.map((f, i) => `  ${i + 1}. ${f}`).join('\n') +
    `\n\nSet "query" to the subquery on every record.`
const perBucket = await parallel(args.buckets.map(b => () =>
  agent(
    `You are the "${b.key}" searcher in a literature megasearch on: ${args.topic}\n` +
    `${b.prompt}${task}\n\n` +
    `Load tool schemas with the host tool discovery first. Aim for ~${CAP} hits per subquery/seed. ` +
    `Use failure recovery: preferred MCP -> alternate MCP in your bucket -> local resilient fallback ` +
    `where applicable; record failed/empty sources and continue with partial results. ` +
    `Set "source" to a short tag on every record. Return ALL records (do not dedupe).`,
    { label: `search:${b.key}`, phase: 'Search', schema: REC_SCHEMA }
  ).then(r => ({ bucket: b.key, results: (r && r.results) || [] }))
))
const all = perBucket.filter(Boolean)
log(`collected ${all.reduce((n, b) => n + b.results.length, 0)} raw records from ${all.length} buckets`)
return { raw: all }   // main loop writes these to raw/*.json then runs merge_corpus.py
```

After the workflow returns, write each `raw[i]` to `<run>/raw/<bucket>.json` and run
`merge_corpus.py --goal <goal> --topic "<topic>"`. Then do the synthesis (see SKILL.md step 5).

For deeper runs (L3+), chain extra waves: a **citation-snowball** wave feeds the top ~10
DOIs/arXiv ids from the corpus so far back in as `seeds:[...]` (the script switches to
snowball mode); L4+ then add a **completeness-critic** agent whose missing-subtopic list
becomes the next wave's facets, looped until dry at L5. Merge each wave into the same corpus.

## Fallback: Agent fan-out (always available, no opt-in)

When the user did not opt into workflows, spawn searchers with the Agent tool in a single
message (one `Agent` call per bucket, run concurrently). Give each the same per-bucket
prompt as above and instruct it to **write its raw file directly** to
`<run>/raw/<bucket>.json`. Then run `merge_corpus.py <run>/raw`.

Agent prompt skeleton (one per bucket):
> You are the "{bucket}" searcher. Topic: {topic}. Tools/bucket: {bucket tools from
> sources.md}. Load schemas via host tool discovery. Run each subquery: {facets}. Aim for ~{cap}
> hits per subquery. Use failure recovery: preferred MCP -> alternate MCP in this bucket
> -> local resilient fallback where applicable. If a source fails or returns empty, write
> `{run}/raw/{bucket}.status.json` and continue. Normalize every hit to the record schema
> (set source+query). Write the JSON list to `{run}/raw/{bucket}.json`. Report only the
> count written and failed-source names.

**Bucket H (KISTI) searcher 예시:** 한국어/국내 주제일 때만 포함. 도구: `scripts/search_local.py
kisti "<한국어 질의>"` (필요 시 `KISTI_TARGET=arti` 등으로 한정). 반환 레코드의 `source`는
`kisti-arti|kisti-report|kisti-patent`. DOI 없는 국내 보고서는 `url`(ScienceON 상세링크)로 추적.
영어 facet 대신 **한국어 facet**을 이 버킷에 배정하라.

For L3+ snowball/critic waves, reuse this skeleton with seeds or critic-named facets in
place of `{facets}`, writing each wave to a new `raw/<bucket>_w2.json` etc. before re-merging.

## Scaling knobs → depth levels (L1–L5)
These four knobs are bundled into five preset levels in `SKILL.md` (`## Depth levels`);
pick one level per run instead of tuning knobs individually.
- **facets**: 3 (L1) → 8 (L4/L5) subqueries (synonyms, sub-aspects, method vs. phenomenon, key authors).
- **buckets**: 4 (L1) → 7/all (L4/L5) from the routing table in `sources.md`.
- **hits/subquery**: ~15 (L1) → ~40 (L4/L5); passed as `cap` in the Workflow args / written into the Agent prompt.
- **waves**: 1 (L1–L2) → +citation-snowball (L3) → +completeness-critic (L4) → critic loop-until-dry (L5).
