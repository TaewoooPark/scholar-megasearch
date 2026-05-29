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
query through its bucket's tools (load schemas via ToolSearch first), normalize hits
into the schema, and **write one JSON file** to `<run>/raw/<bucket>.json`. It must NOT
dedupe or rank — that is `merge_corpus.py`'s job.

## Preferred: Workflow tool (requires "workflow" opt-in)

Use this when the user opted into workflows. Buckets fan out, each searcher writes its
raw file, then a single merge + synthesis. Searcher agents reach MCP tools via ToolSearch.
The merge runs as a Bash step after the workflow returns (workflow agents have no shared
FS guarantees for the script) — so have each agent RETURN its records too, via schema.

```js
export const meta = {
  name: 'scholar-megasearch',
  description: 'Fan out academic search across source buckets, merge into one corpus',
  phases: [{ title: 'Search' }, { title: 'Synthesize' }],
}
// args = { topic, facets: ["subquery 1", ...], buckets: [{key, prompt}, ...] }
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
const perBucket = await parallel(args.buckets.map(b => () =>
  agent(
    `You are the "${b.key}" searcher in a literature megasearch on: ${args.topic}\n` +
    `${b.prompt}\n\nRun EACH of these subqueries through your tools and collect hits:\n` +
    args.facets.map((f,i)=>`  ${i+1}. ${f}`).join('\n') +
    `\n\nLoad tool schemas with ToolSearch first. Aim for 20-40 hits per subquery. ` +
    `Set "source" to a short tag and "query" to the subquery on every record. ` +
    `Return ALL records (do not dedupe).`,
    { label: `search:${b.key}`, phase: 'Search', schema: REC_SCHEMA }
  ).then(r => ({ bucket: b.key, results: (r && r.results) || [] }))
))
const all = perBucket.filter(Boolean)
log(`collected ${all.reduce((n,b)=>n+b.results.length,0)} raw records from ${all.length} buckets`)
return { raw: all }   // main loop writes these to raw/*.json then runs merge_corpus.py
```

After the workflow returns, write each `raw[i]` to `<run>/raw/<bucket>.json` and run
`merge_corpus.py`. Then do the synthesis (see SKILL.md step 5).

For a deeper run, add a **citation-snowball** round: feed the top ~10 DOIs/arXiv ids from
the first corpus back in as seeds (`citation_graph`, `search_openalex` cited-by) and merge
the second wave into the same corpus.

## Fallback: Agent fan-out (always available, no opt-in)

When the user did not opt into workflows, spawn searchers with the Agent tool in a single
message (one `Agent` call per bucket, run concurrently). Give each the same per-bucket
prompt as above and instruct it to **write its raw file directly** to
`<run>/raw/<bucket>.json`. Then run `merge_corpus.py <run>/raw`.

Agent prompt skeleton (one per bucket):
> You are the "{bucket}" searcher. Topic: {topic}. Tools/bucket: {bucket tools from
> sources.md}. Load schemas via ToolSearch. Run each subquery: {facets}. Normalize every
> hit to the record schema (set source+query). Write the JSON list to
> `{run}/raw/{bucket}.json`. Report only the count written.

## Scaling knobs
- **facets**: 3–8 subqueries (synonyms, sub-aspects, method vs. phenomenon, key authors).
- **buckets**: 4–7 from the routing table in `sources.md`.
- **depth**: 1 round (fast) → add citation-snowball + a completeness-critic agent
  ("what subtopic or seminal author is missing from this corpus?") for exhaustive runs.
- per-source hit cap lives in the agent prompt ("20-40 per subquery").
