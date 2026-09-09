---
name: translator-normalization-triage
description: Triage Biomedical Data Translator normalization issues involving odd identifier groupings, unexpected preferred names, surprising semantic types, apparent concept drift, or entities that are incorrectly merged or split in answers. Use whenever a GitHub issue, Translator result URL or PK, CURIE, Name Resolver result, or answer node is primarily suspicious because of clique membership, labels, synonyms, categories, conflation, or normalization behavior. Trace the evidence through source mappings, Babel concordance and clique construction, NodeNorm deployments, Name Resolver, ARA responses, ARS merging, and UI presentation.
---

# Translator Normalization Triage

## Purpose

Identify the first layer where a normalization anomaly appears and show the
exact identifier-mapping evidence that produces it. Keep source assertions,
Babel reachability, served NodeNorm clique membership, Name Resolver search
terms, answer normalization, and UI presentation separate.

This skill is read-only by default. Do not comment on, assign, label, close, or
otherwise mutate a GitHub issue unless the user explicitly asks.

## Trigger Boundary

Use this skill when the primary symptom is any of the following:

- identifiers that appear wrongly grouped into one clique;
- identifiers that should be grouped but normalize separately;
- an unexpected preferred CURIE, name, synonym, category, or taxon;
- a disease, phenotype, gene, protein, drug, chemical, or other concept that
  seems to change meaning in a Translator answer;
- different labels or cliques across Translator environments;
- a suspicious Name Resolver result that may reflect normalization or
  conflation; or
- a report that an answer node combines distinct concepts.

Use ordinary Translator issue triage instead when the identifiers and node
properties are not suspicious and the issue is primarily about an edge,
predicate, provenance record, ranking, timeout, or UI interaction.

## Workflow

1. **State the anomaly precisely.**
   Record the exact input CURIE, observed canonical CURIE, label, categories,
   environment, result URL or PK, and what distinction or equivalence the
   reporter expected. Do not begin from names alone when an identifier is
   available.

2. **Preserve the answer evidence before querying normalization services.**
   For a Feedback issue, use `translator-issue-triage` to collect the issue and
   linked result evidence. For an ARS PK or Translator result URL, use
   `translator-pk-inspector`. For a Babel, NodeNormalization, Name Resolver, or
   other component issue, read the full issue, comments, linked issues, and
   linked pull requests directly; do not force it through a Feedback-only
   collector. Retain:
   - the original subject and object identifiers from the contributing edge;
   - the normalized knowledge-graph node identifier, label, and categories;
   - the ARA child and ARS merge stage where the value first appears; and
   - the exact NodeNorm request options when they are available.

3. **Use Name Resolver only for candidate selection.**
   When the user supplies a name, query Name Resolver and present the candidate
   CURIEs for selection. A Name Resolver synonym or
   `clique_identifier_count` is not proof of current NodeNorm clique
   membership. Once a CURIE is selected, continue with its exact identifier.

4. **Query the reported NodeNorm deployment.**
   Fetch `/status` and `/get_normalized_nodes` for the exact CURIE and preserve
   the full `equivalent_identifiers`, preferred identifier, preferred label,
   types, taxa, and request flags. Compare another deployment when version or
   environment drift is plausible; compare all current deployments when the
   issue claims shared or inconsistent behavior.

   Treat an explicit `null`, a missing response key, and a retrieval failure as
   three different outcomes. Do not turn a failed request into a negative
   normalization result.

5. **Separate the served clique from the recursive concordance.**
   The starting NodeNorm clique is the set returned in
   `equivalent_identifiers`. The recursive Babel concordance is a larger
   evidence graph and can contain identifiers that are in other cliques or in
   no served clique. Reachability in the recursive graph does not prove
   membership in the starting clique.

   When Babel Explorer is available, run it from its checkout or installed
   project:

   ```bash
   uv run --project /path/to/babel-explorer \
     babel-explorer test-concord CURIE \
     --nodenorm-url NODENORM_URL \
     --format json

   uv run --project /path/to/babel-explorer \
     babel-explorer xrefs CURIE \
     --recurse \
     --labels \
     --nodenorm-url NODENORM_URL \
     --format json
   ```

   Use a Babel release that matches the NodeNorm `/status` response.
   Do not pass `--allow-version-mismatch` for a conclusion-bearing run.

6. **Classify every recursively discovered identifier.**
   For each identifier in the recursive result, query NodeNorm and mark it as:
   - in the starting clique;
   - in another named NodeNorm clique; or
   - unresolved by that deployment.

   Compare actual identifiers, not graph colors or displayed node counts.
   Verify any reported count against the length of the live NodeNorm
   `equivalent_identifiers` list.

7. **Trace all material mapping routes and preserve source per edge.**
   For a suspicious pair, inspect the direct edges between them and the
   distinct routes that connect them. Babel Explorer can show a shortest route:

   ```bash
   uv run --project /path/to/babel-explorer \
     babel-explorer xrefs CURIE_A CURIE_B \
     --paths \
     --labels \
     --nodenorm-url NODENORM_URL
   ```

   A shortest path does not establish that no other path exists. Inspect the
   recursive edge list for direct parallel assertions and materially different
   intermediate routes. Preserve each edge as:
   `subject`, `predicate`, `object`, and Babel provenance source.

   Do not collapse two overlapping edges merely because they share endpoints.
   They may be independent assertions from different sources. Conversely, do
   not call a multi-edge route independent if all rows are duplicate exports of
   the same source assertion.

8. **Check the authoritative records behind disputed edges.**
   Verify the source ontology or identifier system named by each load-bearing
   concordance edge. A shared synonym, related synonym, broad/narrow match, or
   textual description is not automatically an equivalence assertion. Keep the
   source's own relation separate from Babel's interpretation of that relation.

9. **Compare semantic behavior separately.**
   Analyze clique membership, preferred identifier, preferred label, semantic
   types, and Name Resolver synonyms as distinct outputs. A correct clique can
   still have a poor preferred name, and a plausible name does not make an
   incorrect clique valid.

10. **Attribute the first faulty layer.**
    Read [references/triage-guide.md](references/triage-guide.md) before making
    the attribution. Choose among:
    - authoritative source assertion;
    - Babel concordance extraction or predicate interpretation;
    - Babel clique construction or preferred-term selection;
    - NodeNorm load, service, or deployment version;
    - request options or conflation;
    - Name Resolver indexing or search presentation;
    - ARA-specific normalization;
    - ARS merge or post-processing;
    - UI presentation; or
    - insufficient evidence.

11. **Recommend the narrowest corrective action.**
    Name the exact source edge, Babel rule/input, deployment, request option,
    ARA, merge stage, or UI field that should change. If multiple independent
    mapping routes create the grouping, list every route that must be removed
    or corrected; removing only one will not split the clique.

## Evidence Rules

- Record endpoint URLs, retrieval timestamps, NodeNorm/Babel versions, and
  request options.
- Start from the identifier present in the answer, not a replacement selected
  by label similarity.
- Preserve complete load-bearing TRAPI nodes, edges, and identifier lists.
- Keep edge direction and predicate even when traversing concordance as an
  undirected connectivity graph.
- Distinguish a Babel provenance source from an upstream authoritative record.
- Treat multiple sources as separate evidence, not automatic corroboration.
- Do not infer clique membership from Name Resolver synonyms or recursive
  concordance reachability.
- Do not infer semantic equivalence from matching labels.
- For chemicals, compare base cliques with drug-chemical conflation disabled
  before evaluating exact identity.
- Preserve negative, contradictory, and unavailable evidence.
- Do not stop after finding the first plausible mapping path.

## Output

Lead with the first faulty layer and a one-sentence conclusion. Then provide:

1. the observed answer or issue symptom;
2. the exact starting NodeNorm clique and cross-environment differences;
3. a table of direct and indirect mapping routes with one source per edge;
4. the recursively reached identifiers classified by clique;
5. the evidence that supports or rules out each relevant layer; and
6. the narrowest next action and likely owner, with unresolved evidence stated.
