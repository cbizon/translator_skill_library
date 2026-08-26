---
name: translator-one-hop-questions
description: Build, validate, run, and inspect one-hop Biomedical Data Translator TRAPI questions through ARS. Use when the user asks for entity-to-entity lookups such as diseases caused by a gene, genes that can cause or are associated with a disease, chemicals or drugs that affect, upregulate, or downregulate genes, drugs that treat a disease, phenotypes of a gene or disease, or genes related to a clinical disease category. This skill starts from an environment, one input entity, an output Biolink category, and an optional Biolink predicate or predicate phrase.
---

# Translator One-Hop Questions

## Purpose

Use this skill to turn a constrained one-hop biomedical question into a TRAPI
query, submit it to Translator ARS, wait for completion, and summarize the
returned answers.

The v1 scope is one known input entity and one output entity type. Set-valued
clinical feature questions, answer coalescing, direct ARA submission, and
Retriever-only lookup are future extensions, not default behavior here. When a
question depends on predicate choice, use the predicate-widening guidance below
before concluding that no data exist.

## Required Inputs

Collect these before submitting a query:

- Translator environment: `ci`, `test`, `prod`, or `dev`. Default to `ci` only
  when the user does not care which environment is used.
- Input entity: a name or CURIE.
- Input category when known, such as `biolink:Gene`, `biolink:Disease`,
  `biolink:Drug`, `biolink:ChemicalEntity`, or `biolink:PhenotypicFeature`.
- Output category, such as `biolink:Disease` or `biolink:Gene`.
- Optional predicate, such as `biolink:causes`, `biolink:contributes_to`,
  `biolink:associated_with`, `biolink:treats`, or a short phrase like
  `causes`.
- Optional QEdge qualifier constraints, especially for chemical-to-gene
  questions where the biological meaning is stored on `biolink:affects`
  edges as object aspect and direction qualifiers.

Do not infer a predicate or edge direction silently. If the user gives a broad
word such as "related" and the expected predicate is unclear, ask or omit the
predicate intentionally and say that the query is predicate-open.

## Predicate Direction

Biolink predicates have a subject-to-object orientation. Normalize the user's
relation phrase to a Biolink predicate, then place the known input entity on the
correct side of that predicate.

Examples:

- "What diseases are caused by BRCA1?" uses `biolink:causes` with the input
  gene as the subject and the unknown disease as the object.
- "What genes can cause cystic fibrosis?" uses `biolink:causes` with the
  unknown gene as the subject and the input disease as the object.
- "What genes are associated with asthma?" usually uses
  `biolink:associated_with` or `biolink:contributes_to` with the unknown gene as
  the subject and the input disease as the object, unless the user chooses a
  different predicate.

If a phrase maps to a Biolink inverse pair, use the predicate that the live
Biolink model actually defines and orient the query graph according to the
model's subject/object semantics. For example, if the user says "causes" but
the supported model term is inverse wording such as "caused by", use the model
term and reverse the edge as needed. Do not invent an unsupported inverse
predicate. If the predicate cannot be confidently matched to Biolink, validate
against the live Biolink model or ask the user before submitting.

For symmetric predicates such as `biolink:related_to`, do not run both edge
directions just to cover symmetry. Choose the direction implied by the user's
question and the input/output categories, then validate that shape against
Retriever metadata. Only test the mirror direction when the initial direction is
unsupported, when the user explicitly asks for a directionality comparison, or
when investigating a suspected category-orientation modeling issue.

## Chemical-Gene Directional Qualifiers

Chemical-to-gene "up" and "down" questions are usually represented as
`ChemicalEntity --biolink:affects--> Gene` with qualifiers, not as predicates
such as `biolink:increases_expression_of`.

For questions such as "what chemicals upregulate ADRB2?", put the unknown
chemical on the subject side and the known gene on the object side:

```json
{
  "subject": "output",
  "object": "input",
  "predicates": ["biolink:affects"],
  "constraints": {
    "qualifiers": [
      {
        "biolink:object_aspect_qualifier": "activity_or_abundance",
        "biolink:object_direction_qualifier": "increased"
      }
    ]
  }
}
```

Qualifier defaults:

- Use `object_aspect_qualifier = activity_or_abundance` for broad "upregulate",
  "downregulate", "up genes", or "down genes" wording.
- Use the narrower aspect when the user names it: `expression`, `activity`,
  `abundance`, `degradation`, etc.
- Use `object_direction_qualifier = increased` for up/increase wording and
  `decreased` for down/decrease wording. Biolink also permits `upregulated` and
  `downregulated`; if a canonical `increased` or `decreased` query returns no
  results and the exact direction value seems likely to be the issue, try the
  corresponding regulated value before dropping qualifiers.
- Add `biolink:qualified_predicate = biolink:causes` only when the user asks for
  causal wording or when the data source pattern being tested is known to use
  that qualifier. Do not add it silently if it would overconstrain the lookup.

For "what genes does chemical X upregulate?", keep the same canonical edge
direction (`input -> output`) with the chemical as subject and the gene as
object.

Before submitting, check Retriever `/meta_knowledge_graph` for the
`ChemicalEntity --biolink:affects--> Gene` shape and verify that the edge
metadata advertises the requested qualifier types, such as
`biolink:object_aspect_qualifier` and
`biolink:object_direction_qualifier`.

## Predicate Widening

A zero-result query for the expected predicate is not evidence that the target
edges are absent. The data may be modeled with a superpredicate or a nearby
predicate. Unless the user asks for an exact-predicate lookup only, use this
fallback pattern:

1. Start with the most specific predicate that matches the user's wording.
2. If the specific query uses qualifier constraints, first try the same
   predicate without qualifier constraints, unless the user asked for exact
   qualifiers only.
3. If that query returns no usable results, validate and try the next broader
   Biolink predicate supported by Retriever metadata for the same subject and
   object categories.
4. Continue moving up the predicate hierarchy until results are found or no
   supported broader predicate remains.
5. Use `biolink:related_to` as the broadest practical fallback when it is
   supported for the subject/object category pair.

Keep the input entity, output category, edge direction, environment, and
`parameters.tier = 0` fixed across fallback runs. Drop or broaden qualifiers
before changing the predicate. Change the predicate only when qualifier fallback
does not produce usable results or when metadata shows the qualified shape is
unsupported.

When comparing fallback runs, report the exact query predicate separately from
the predicates and qualifiers actually returned in the result bindings. A
successful broad query may answer the user's question because returned edges use
predicates such as `biolink:associated_with`,
`biolink:gene_associated_with_condition`, or
`biolink:occurs_together_in_literature_with`, even if the original requested
predicate returned nothing.

## Result Reconciliation Guardrail

Before saying a query had no results, only one ARA returned results, or a
fallback did not work, reconcile the ARS parent child summaries across all ARA
children. Treat the parent-level per-child `result_count` table as the first
source of truth for "which ARA returned results".

Do not infer all-ARA behavior from a single fetched child payload. If you fetch
only one child for edge-detail inspection, state that the predicate/source
details apply only to that child. If any child has `result_count > 0`, the ARS
query returned results even if other predicates, other children, or inspected
subsets returned zero.

When predicate fallback is used, keep two separate summaries:

- One table by attempted query predicate and ARA child result counts.
- One main answer table from the merged ARS result when it is available.
- Any edge-detail summary from inspected child payloads, clearly labeled by ARA.

## Merged ARS Result

Use the merged ARS result as the default source for user-facing answers. The
parent ARS message may expose it as `merged_version`; it may also appear as a
child with actor `ars-ars-agent`. Fetch that merged message and build the main
results table from its TRAPI message.

Do not build the primary answer table from individual ARA child payloads when a
merged ARS result is available. Per-ARA child payloads are for diagnostics,
edge-level follow-up, or explaining differences between ARAs. If the merged
result is missing, malformed, or has not completed, say so explicitly before
falling back to per-ARA summaries.

The standard merged-result table should be sorted by descending result score and
include:

- Rank.
- Output node label and CURIE.
- Score from the first/default result analysis.
- Predicate or predicates bound to the query edge for that answer, taken from
  the merged result's KG edge bindings.

For chemical-gene directional `biolink:affects` queries, the main merged-result
table must include the semantic qualifier values bound to the answer edge, not
just the predicate. Required columns are:

- Rank.
- Output node label.
- Output CURIE.
- Score.
- Effective predicate(s): use the bound edge's `qualified_predicate` value when
  present; otherwise use the bound edge predicate.
- `object_aspect_qualifier`.
- `object_direction_qualifier`.

If the user requested or the query uses additional semantic qualifiers such as
`causal_mechanism_qualifier` or `species_context_qualifier`, include those as
columns as well. Do not show `qualified_predicate` as a separate column when it
is already used as the effective predicate. Do not replace these qualifier
columns with edge counts, primary sources, support graphs, or knowledge levels;
those are diagnostics and should be reported separately only when requested.

Keep the main table compact. Do not include every edge attribute by default; if
the user wants sources, support graphs, knowledge levels, or full edge details,
inspect and report those separately.

Do not filter the merged-result table to a preferred identifier namespace, such
as `NCBIGene`, unless the user explicitly asks for that filtered view.
Translator's returned output bindings are the source of truth for what the
system answered. If the result set mixes identifiers or includes terms whose
semantic type seems broader, noncanonical, or surprising, still report those
rows as returned by Translator and add a clearly labeled note or optional
secondary normalized/filtered view. Do not decide on the user's behalf which
returned terms "count" as the requested output category.

## Workflow

1. Resolve the input entity with Name Resolver.
   - If the input is already a CURIE, use it directly unless the user wants
     synonym normalization first.
   - If multiple plausible CURIEs are returned, show the candidates and ask the
     user to choose. Do not pick a CURIE silently.
2. Construct the one-hop TRAPI query graph.
   - Use modern TRAPI fields: `ids`, `categories`, and `predicates`.
   - For QEdge qualifiers, use `constraints.qualifiers` with one qualifier set
     object whose keys are Biolink qualifier type CURIEs and whose values are
     qualifier values.
   - If the input entity is the predicate subject, the edge is
     `input -> output`.
   - If the input entity is the predicate object, the edge is
     `output -> input`.
   - For symmetric predicates such as `biolink:related_to`, do not submit a
     second mirrored query unless the first direction is unsupported or the user
     asks to compare directions.
   - Include top-level `parameters.tier = 0` unless the user explicitly asks
     to test another Retriever tier.
3. Validate the query before ARS submission.
   - Ensure all categories and predicates use the `biolink:` prefix.
   - Ensure all qualifier type ids use the `biolink:` prefix.
   - Ensure the edge references existing query graph nodes.
   - Check Retriever `/meta_knowledge_graph` for the subject category, object
     category, and predicate combination. If the requested predicate is not
     supported for that subject/object shape, stop and show supported
     predicates.
   - If qualifier constraints are present, check Retriever metadata for the
     requested qualifier type ids on the same subject/predicate/object shape.
   - For non-obvious predicate phrases, check the live Biolink model before
     submission.
4. Submit the query to ARS.
5. Poll the parent ARS message until children appear terminal or the timeout is
   reached.
6. Summarize all terminal ARA child statuses and `result_count` values from the
   parent message before drawing any conclusion about zero results or which ARA
   returned answers.
7. If all ARA child result counts are zero and the query used a specific
   predicate, apply the predicate-widening workflow before reporting no results.
8. Fetch the merged ARS result from `merged_version` or the `ars-ars-agent`
   child and use it for the primary answer table.
9. Fetch ARA child payloads only when needed for diagnostics or deeper result
   details. If only a subset is fetched, label the resulting edge/source details
   as subset-specific.
10. For deeper payload inspection, use `$translator-pk-inspector` on the parent
   PK or UI URL.

## Result Edge Reporting

Do not describe answers only in terms of the requested query predicate. Inspect
the returned TRAPI and report what the data actually support:

- For each result row, inspect `result.analyses[].edge_bindings` to identify the
  KG edge or edges bound to the query edge.
- Report the bound edge subject, predicate, object, source, and
  `biolink:knowledge_level` when present.
- If a bound edge has a `biolink:support_graphs` attribute, inspect the named
  `message.auxiliary_graphs` entries and report the supporting direct edge(s).
- When a bound edge is a logical entailment to the requested ontology parent,
  distinguish it from the direct data edge to the child term. For example,
  report "result edge: gene associated_with parent disease; supporting edge:
  gene associated_with child disease plus child subclass_of parent."
- For broad fallback predicates such as `related_to`, summarize counts by the
  actual returned edge predicates, not only by the fallback predicate.

When querying a higher-level disease or clinical category, expect results may be
inferred from direct edges to subclass diseases. If so, report both the
requested parent concept and the subclass concept that supplied the direct
supporting edge.

## Helper Script

Prefer the bundled helper for routine runs:

Run these commands from this skill directory, which is the directory containing
this `SKILL.md`. Do not assume a user-specific installation path.

```bash
uv run --isolated --no-project python scripts/run_one_hop_query.py \
  --env ci \
  --entity BRCA1 \
  --input-category biolink:Gene \
  --output-category biolink:Disease \
  --predicate causes \
  --input-role subject \
  --output /tmp/translator_one_hop_brca1.json
```

For a disease-to-gene query where the unknown gene is the predicate subject:

```bash
uv run --isolated --no-project python scripts/run_one_hop_query.py \
  --env ci \
  --entity "cystic fibrosis" \
  --input-category biolink:Disease \
  --output-category biolink:Gene \
  --predicate causes \
  --input-role object \
  --output /tmp/translator_one_hop_cf_genes.json
```

For chemicals that broadly upregulate a known gene, use the gene as the input
object and let the helper map `upregulates` to qualified `biolink:affects`:

```bash
uv run --isolated --no-project python scripts/run_one_hop_query.py \
  --env ci \
  --entity ADRB2 \
  --input-category biolink:Gene \
  --output-category biolink:ChemicalEntity \
  --predicate upregulates \
  --input-role object \
  --output /tmp/translator_one_hop_adrb2_upregulates.json
```

For an explicit qualified chemical-gene query, pass qualifiers directly:

```bash
uv run --isolated --no-project python scripts/run_one_hop_query.py \
  --env ci \
  --input-curie NCBIGene:154 \
  --entity ADRB2 \
  --input-category biolink:Gene \
  --output-category biolink:ChemicalEntity \
  --predicate affects \
  --input-role object \
  --object-aspect-qualifier activity_or_abundance \
  --object-direction-qualifier increased \
  --output /tmp/translator_one_hop_adrb2_affects_increased.json
```

If Name Resolver returns multiple candidates, rerun with `--input-curie` after
the user selects the intended concept.

Use `--build-only` to write the TRAPI query without submitting it, and
`--resolve-only` to inspect resolver candidates.

Use `--metadata-only` to inspect Retriever-supported predicates for the resolved
subject/object category pair without submitting to ARS.

The helper includes top-level `parameters.tier = 0` in the built TRAPI payload
by default. Use `--retriever-tier 1` only when explicitly comparing Retriever
tier behavior.

## Output Expectations

Report:

- The environment and ARS parent PK.
- The resolved input CURIE and label.
- The exact query graph direction, requested predicate, and any broader
  fallback predicates attempted.
- The exact qualifier constraints used, plus any qualifier-dropping or
  qualifier-broadening fallbacks attempted.
- Whether Retriever metadata supports the subject/predicate/object shape, and
  the alternate supported predicates or qualifier types when relevant.
- The UI URL for the result when available.
- Per-ARA child status and result count for every attempted predicate before
  any top-answer narrative.
- The merged ARS result PK or an explicit statement that no merged result was
  available.
- A compact merged-result table sorted by descending score, with output label,
  CURIE, score, and bound predicate(s) for each answer.
- For chemical-gene directional `biolink:affects` queries, include row-level
  `object_aspect_qualifier` and `object_direction_qualifier` values in the main
  merged-result table, plus any requested or returned semantic qualifier values
  such as `causal_mechanism_qualifier` or `species_context_qualifier`. If a
  bound edge has `qualified_predicate`, show that value in the predicate column
  instead of the base edge predicate; do not add a separate
  `qualified_predicate` column.
- Include all merged-result output rows by default, regardless of identifier
  namespace. Only filter to canonical identifiers, such as `NCBIGene`, when the
  user asks for that; label any filtered or normalized table as secondary.
- Counts by actual returned KG predicate from the merged result for broad or
  fallback queries.
- Counts by actual returned KG qualifier values when a chemical-gene directional
  query falls back to unqualified `biolink:affects`.
- For inferred parent-category answers, the supporting direct edge and subclass
  edge from the auxiliary graph.

Do not claim that no answer exists if retrieval failed, timed out, or returned a
malformed payload. State the failure explicitly.

Do not claim that "only BTE", "only ARAX", or "only ARAGORN" returned results
unless the parent child summary shows zero results for every other ARA child.

## Future Extension Points

These are intentionally not v1 defaults:

- Automated predicate fallback inside the helper script.
- Direct submission to individual ARAs instead of ARS.
- Retriever tier 0 or tier 1 lookup-only mode.
- Answer coalescer workflows for set-valued feature queries.
