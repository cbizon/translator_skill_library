---
name: translator-set-input-queries
description: Build, validate, run, and inspect Biomedical Data Translator set-input TRAPI queries against Answer Coalesce. Use when the user asks for multi-input or set-valued Translator questions, phenotype or disease-or-phenotype set queries, chemical sets affecting or regulating genes with QEdge qualifiers, query graph member_ids, set_interpretation MANY/ALL/BATCH, Answer Coalesce CI, or responses that should summarize answers supported by multiple Name Resolver/Babel input CURIEs.
---

# Translator Set Input Queries

## Purpose

Use this skill to build and submit set-input TRAPI queries to Answer Coalesce,
then summarize the returned coalesced answers. This is separate from the
one-hop ARS skill: the input is a set of CURIEs on one query node, represented
with `member_ids` and `set_interpretation`, and the request goes directly to
Answer Coalesce unless the user explicitly asks for another route.

Default service:

```text
https://answer-coalesce.ci.transltr.io/
```

Read `references/answer-coalesce-api.md` when endpoint details, payload shape,
or examples are needed.

## Required Inputs

Collect these before submitting a live query:

- Input member CURIEs resolved through Translator Name Resolver/Babel. If the
  user provides names instead of CURIEs, resolve each name and keep the
  returned preferred CURIE and type information. Do not replace a resolver
  result with an external ontology ID just because the label sounds like an HPO
  phenotype.
- One input category for the set node. Choose the smallest Biolink superclass
  that covers every resolved member, such as `biolink:PhenotypicFeature`,
  `biolink:Disease`, `biolink:DiseaseOrPhenotypicFeature`, or `biolink:Gene`.
- Output category, such as `biolink:Disease`, `biolink:Gene`, or
  `biolink:ChemicalEntity`.
- Predicate, such as `biolink:has_phenotype`,
  `biolink:genetically_associated_with`, or `biolink:related_to`.
- Edge direction: whether the set input node is the predicate subject or
  object. Do not infer direction silently when the wording is ambiguous.
- Optional QEdge qualifier constraints, especially for chemical-to-gene
  questions where regulation or activity meaning is represented on
  `biolink:affects` edges as object aspect and direction qualifiers.
- Set interpretation. Default to `MANY` for coalesced multi-feature lookups
  unless the user asks for `ALL` or `BATCH`.

Use CI by default because the user supplied the CI endpoint. Use another base
URL only when explicitly requested.

## Name Resolver And Category Selection

Translator databases and Answer Coalesce operate over Babel-normalized
identifier cliques. Name Resolver is the source of truth for both the member
CURIEs and the member types that should go into the query.

For a list of clinical features, do not assume every item has or should have an
HPO identifier. Some user-provided "phenotype" phrases resolve to disease
cliques with a preferred MONDO identifier, UMLS identifier, or another Babel
preferred CURIE. Use the Name Resolver result if it is the intended clinical
concept.

When the resolved members do not all share the same narrow type, choose one
query-node category: the smallest Biolink parent class that covers all of them.
For mixed disease and phenotype lists, use:

```text
biolink:DiseaseOrPhenotypicFeature
```

Do not put multiple categories on the set input node to cover mixed members.
Do not split the member list into separate disease and phenotype set nodes
unless the user explicitly asks for a different query graph.

When Name Resolver returns multiple plausible candidates for a phrase, inspect
the labels, synonyms, preferred CURIEs, and types. For long clinical lists, it
is acceptable to proceed with the clearly intended top candidate for each item,
but report any low-confidence or unresolved mappings separately.

## Query Graph Pattern

Represent the set-valued input as one query node named `input`:

```json
{
  "categories": ["biolink:PhenotypicFeature"],
  "ids": ["uuid:1"],
  "member_ids": ["HP:0002378", "HP:0002019", "HP:0007146"],
  "set_interpretation": "MANY"
}
```

The `ids` value is a synthetic set identifier. Keep it stable within the query;
do not replace it with one of the member CURIEs.

The `categories` array should contain one category: the selected common
Biolink parent for the full member set. For example, use
`["biolink:DiseaseOrPhenotypicFeature"]` when the resolved member list contains
both disease and phenotype concepts.

Use one output node named `output`, and one edge named `edge_0`. If the input
set is the predicate subject, use `input -> output`. If the input set is the
predicate object, use `output -> input`.

For QEdge qualifiers, use modern TRAPI `constraints.qualifiers` with one
qualifier set object whose keys are Biolink qualifier type CURIEs and whose
values are qualifier values:

```json
{
  "subject": "input",
  "object": "output",
  "predicates": ["biolink:affects"],
  "constraints": {
    "qualifiers": [
      {
        "biolink:object_aspect_qualifier": "activity",
        "biolink:object_direction_qualifier": "increased"
      }
    ]
  }
}
```

Example HPO phenotype set to disease, matching the Answer Coalesce CI OpenAPI
example:

```json
{
  "message": {
    "query_graph": {
      "nodes": {
        "input": {
          "categories": ["biolink:PhenotypicFeature"],
          "ids": ["uuid:1"],
          "member_ids": ["HP:0002378", "HP:0002019", "HP:0007146"],
          "set_interpretation": "MANY"
        },
        "output": {
          "categories": ["biolink:Disease"]
        }
      },
      "edges": {
        "edge_0": {
          "subject": "input",
          "object": "output",
          "predicates": ["biolink:has_phenotype"]
        }
      }
    }
  }
}
```

## Chemical-Gene Directional Qualifiers

Chemical-to-gene "up", "down", "increases activity", and "decreases
expression" questions are usually represented as
`ChemicalEntity --biolink:affects--> Gene` with qualifiers, not as invented
predicates such as `biolink:increases_activity_of` or
`biolink:increases_expression_of`.

For "what genes does this chemical set increase activity of?", use the chemical
set as the subject and the unknown gene as the object:

```json
{
  "subject": "input",
  "object": "output",
  "predicates": ["biolink:affects"],
  "constraints": {
    "qualifiers": [
      {
        "biolink:object_aspect_qualifier": "activity",
        "biolink:object_direction_qualifier": "increased"
      }
    ]
  }
}
```

Qualifier defaults:

- Use `object_aspect_qualifier = activity_or_abundance` for broad
  "upregulate", "downregulate", "up genes", or "down genes" wording.
- Use the narrower aspect when the user names it: `expression`, `activity`,
  `abundance`, `degradation`, etc.
- Use `object_direction_qualifier = increased` for up/increase wording and
  `decreased` for down/decrease wording. Biolink also permits `upregulated` and
  `downregulated`; if canonical `increased` or `decreased` returns no usable
  results and the exact direction value seems likely to be the issue, try the
  corresponding regulated value as a separate, explicitly reported run.
- Add `biolink:qualified_predicate = biolink:causes` only when the user asks for
  causal wording or when a known data-source pattern requires that qualifier.
  Do not add it silently if it would overconstrain the lookup.

If a chemical-gene qualified `biolink:affects` query has no usable results and
the user did not ask for exact qualifiers only, try the same predicate without
qualifier constraints before broadening to another predicate. Keep the member
set, output category, edge direction, endpoint, and set interpretation fixed
across fallback runs, and report every query shape separately.

## Workflow

1. Resolve each user-provided member term through Name Resolver/Babel unless it
   is already a CURIE that the user wants to use as-is.
2. Record the selected resolver label, preferred CURIE, and returned Biolink
   types for every member.
3. Select the single smallest common Biolink parent category that covers all
   selected members.
4. Normalize the rest of the question into output category, predicate, edge
   direction, qualifier constraints when needed, and set interpretation. For
   non-obvious predicate phrases, validate against the live Biolink model or ask
   the user before submitting; do not invent inverse or directional predicate
   names.
5. Validate that categories, predicates, and qualifier type ids use `biolink:`
   prefixes and that the member list is not empty.
6. Build the TRAPI payload with `member_ids` on the input QNode and a synthetic
   `ids` value such as `uuid:1`.
7. Prefer a build-only pass first when direction, predicate, qualifiers, or
   member IDs need user review.
8. Submit to `POST /query` for ordinary synchronous runs.
9. Use `POST /asyncquery` only when the user expects a long-running query or
   provides a callback; poll `/query/status/{job_id}` and fetch
   `/query/result/{job_id}`.
10. Summarize the TRAPI response from `message.results`,
   `message.knowledge_graph`, and `message.auxiliary_graphs`.

Do not claim there are no answers if the service fails, times out, returns
malformed JSON, or logs an error. Report that failure directly.

## Result Edge Reporting

Do not describe answers only in terms of the requested query predicate. Inspect
the returned TRAPI and report what the data actually support:

- For each result row, inspect `result.analyses[].edge_bindings` to identify the
  KG edge or edges bound to `edge_0`.
- Report the bound edge subject, predicate, object, source, and
  `biolink:knowledge_level` when present.
- If a bound edge has `biolink:support_graphs`, inspect the named
  `message.auxiliary_graphs` entries and report the supporting direct edge(s).
- For broad or fallback queries, summarize counts by the actual returned KG
  predicates, not only by the query predicate.
- For qualified chemical-gene `biolink:affects` queries, report returned
  semantic qualifier values from KG edge `qualifiers` or qualifier-like edge
  attributes, especially `qualified_predicate`, `object_aspect_qualifier`, and
  `object_direction_qualifier`.

## Helper Script

Prefer the bundled helper for routine payload construction and submission:

Run these commands from this skill directory, which is the directory containing
this `SKILL.md`. Do not assume a user-specific installation path.

```bash
uv run --isolated --no-project python scripts/run_set_input_query.py \
  --member-id HP:0002378 \
  --member-id HP:0002019 \
  --member-id HP:0007146 \
  --input-category biolink:PhenotypicFeature \
  --output-category biolink:Disease \
  --predicate biolink:has_phenotype \
  --input-role subject \
  --output /tmp/ac_hpo_disease.json
```

For build-only review:

```bash
uv run --isolated --no-project python scripts/run_set_input_query.py \
  --member-ids HP:0002378,HP:0002019,HP:0007146 \
  --input-category biolink:PhenotypicFeature \
  --output-category biolink:Disease \
  --predicate biolink:has_phenotype \
  --input-role subject \
  --build-only
```

For a gene set to chemical query:

```bash
uv run --isolated --no-project python scripts/run_set_input_query.py \
  --member-ids NCBIGene:5297,NCBIGene:5298,NCBIGene:5290 \
  --input-category biolink:Gene \
  --output-category biolink:ChemicalEntity \
  --predicate biolink:related_to \
  --input-role object \
  --output /tmp/ac_gene_chemical.json
```

For a chemical set that increases gene activity, use qualified
`biolink:affects`:

```bash
uv run --isolated --no-project python scripts/run_set_input_query.py \
  --member-ids <resolved-chemical-curie-1>,<resolved-chemical-curie-2> \
  --input-category biolink:ChemicalEntity \
  --output-category biolink:Gene \
  --predicate biolink:affects \
  --input-role subject \
  --object-aspect-qualifier activity \
  --object-direction-qualifier increased \
  --output /tmp/ac_chemical_set_gene_activity_increased.json
```

The helper defaults to `set_interpretation=MANY` and
`base_url=https://answer-coalesce.ci.transltr.io`. Use `--async-query` for
`/asyncquery`, `--member-file` for one CURIE per line, `--qualifier TYPE=VALUE`
for additional QEdge qualifier constraints, and `--limit` to control the printed
summary length.

## Output Expectations

Report:

- Answer Coalesce base URL and endpoint used.
- Input category, output category, predicate, edge direction, set
  interpretation, member count, and any qualifier constraints.
- The selected Name Resolver mapping for each member: original phrase, chosen
  label, chosen CURIE, and selected type. For long lists, keep the table
  compact but include all unresolved or low-confidence mappings.
- HTTP/job status and any TRAPI logs.
- Result count, knowledge graph node count, edge count, and auxiliary graph
  count.
- A compact ranked table with one row per output answer and these columns, in
  this order: `id`, `name`, `p value`, and `number of matched inputs`. For
  set-input answers, compute
  `number of matched inputs` from the distinct input `member_ids` that support
  the output through bound edges or their support graphs. If multiple result
  rows for the same output have p-values, report the first-ranked p-value. If no
  p-value is present, leave that cell blank rather than substituting score.
- For chemical-gene directional `biolink:affects` queries, inspect and report
  row-level qualifier values in the surrounding text when they materially affect
  interpretation, especially `qualified_predicate`,
  `object_aspect_qualifier`, and `object_direction_qualifier`.
- Any support graphs or enrichment auxiliary graphs that materially explain the
  answer, especially when a p-value or enriched property drives the ranking.

Do not filter answers to a preferred identifier namespace unless the user asks
for that secondary view. Translator's returned output bindings are the source
of truth for what the service answered.

## Guardrails

- Do not use the older notebook-only `/1.4/coalesce/property` or
  `/1.4/coalesce/graph` endpoints for new set-input queries unless the user is
  explicitly reproducing that older workflow.
- Do not use broad exception handling that hides HTTP, JSON, or schema
  failures.
- Do not silently change predicate direction to force results. If the submitted
  direction is questionable, show the payload and ask before running.
- Do not invent predicate CURIEs from surface wording. For chemical-gene
  regulation or activity questions, start with qualified `biolink:affects`
  before predicate broadening.
- Do not silently drop qualifier constraints to force results. If qualifier
  fallback is appropriate, run and report the qualified and unqualified query
  shapes separately.
- Do not summarize only the requested predicate; inspect returned edge bindings
  and report the predicates and qualifiers actually bound in the knowledge
  graph.
