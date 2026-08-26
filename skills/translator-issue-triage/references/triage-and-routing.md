# Translator Feedback Triage And Routing

## Triage Standard

Answer these questions in order:

1. What exact behavior does the issue report?
2. Can it be reproduced in the linked environment and PK?
3. Does it occur in the merged response, one ARA response, several ARA
   responses, or only the UI?
4. What exact result, binding, edge, attribute, source, original identifier, or
   support path demonstrates the behavior?
5. Where does the behavior first appear?
6. Which component owns that first faulty transformation?

Do not skip from a suspicious final result directly to a component assignment.

## Related Issue Traversal

- Read directly referenced Feedback issues and GitHub timeline backlinks before
  diagnosing the primary issue.
- A backlink from another Feedback issue can contain the direct root-cause,
  fix, or deployment discussion even when the primary issue has no comments.
- If a component issue links back to a Feedback issue for the same entity or
  behavior, follow that backlink one hop and read its comments.
- Prefer a component-owner statement backed by a fix or live comparison over a
  newly inferred mechanism. Do not post a redundant diagnosis.

## Layer Attribution

### ARS merger or post-ARA processing

Evidence pattern:

- Individual ARA payloads each contain one correct copy.
- The merged ARS response contains repeated copies or a malformed combination.

State that the defect first appears in the merged response. Do not blame an ARA
merely because its data contributed to the merge.

When `merged_versions_list` is available, compare each intermediate merge stage
to identify which added response first introduced or amplified the defect.

### ARA-specific processing

Evidence pattern:

- The malformed result exists in one ARA child and not in the other children.
- The ARA's direct edge bindings or support graphs contain the defect before
  merging.

Name the exact actor and child PK. Distinguish the ARA from its Shepherd wrapper
when the payload identifies both.

### Retriever, ingest, or source data

Evidence pattern:

- Multiple ARA children contain the same problematic concrete edge.
- Provenance identifies a shared primary knowledge source or Retriever path.

Inspect the full edge, `sources`, `original_subject`, and `original_object`.
Separate a bad source assertion from a transformation introduced during ingest.

### Node Normalization

Evidence pattern:

- Original identifiers describe the expected source assertion.
- Normalized subject or object identifiers represent a different concept.
- The incorrect concepts occur in the same normalization clique.

Show both original and normalized identifiers. Verify the live Node
Normalization response before attributing the issue.

### UI

Evidence pattern:

- The merged TRAPI payload contains the correct result or attribute.
- The UI omits, duplicates, mislabels, or cannot display it.

Quote the relevant payload field and state that the data is present upstream.

### Fixed but not deployed

Evidence pattern:

- A component issue or related Feedback issue identifies the root cause and
  fix.
- A newer or experimental environment contains the fix, while the environment
  named by the primary issue still reproduces the old behavior.

State both the code/build status and the deployment status. Route the issue to
the existing owner, and do not describe stale deployed data as a newly
discovered defect.

## Assignment Rules

- Preserve all existing assignees.
- Assign only when the evidence identifies a component and a GitHub login is
  supported by repository evidence.
- Find ownership evidence in this order:
  1. Existing assignees or explicit mentions on the issue.
  2. Directly referenced Feedback issues about the same component.
  3. Recent Feedback issues with the same component label or diagnosis.
  4. The component repository's maintainers or CODEOWNERS.
- Verify that a proposed login can be assigned:

  ```bash
  gh api repos/NCATSTranslator/Feedback/assignees/LOGIN
  ```

- Add the assignee; never replace or remove existing assignees.
- If the supported owner is already assigned, make no assignment mutation and
  report that the existing assignment is appropriate.
- If component ownership or login evidence is ambiguous, state the putative
  component in the comment and leave assignment unchanged.
- Do not infer personnel responsibility from names, affiliations, or unrelated
  project context.

## Comment Rules

- Re-fetch the issue and comments before posting.
- Do not repeat findings already posted.
- If the user requests a draft, dry run, or read-only investigation, do not post
  or change assignees.
- Lead with the direct conclusion.
- Include the environment and PKs needed to reproduce.
- Compare merged and individual ARA behavior explicitly.
- Include exact JSON only when it proves the conclusion. A complete edge is
  appropriate when its attributes, original identifiers, or sources are
  load-bearing.
- Use ordinary TRAPI terms: result, edge, edge binding, support graph, source.
  Do not invent shorthand.
- Qualify attribution with phrases such as "first appears in," "points to," or
  "is at least partially" when evidence is not complete.
- If the data does not support a diagnosis, post what was checked, what failed,
  and what evidence is still needed.

## Example Reasoning Patterns

### Duplicate merged attributes

Merged Gabapentin node attributes occur three times, while ARAX, BTE, and
ARAGORN each contain one copy. This verifies the report and points to the merge
layer rather than any individual ARA.

### Incorrect normalized phenotype edge

An edge is normalized as Sturge-Weber syndrome `has_phenotype` breast carcinoma,
but its original subject is an OMIM identifier for another syndrome. This
points to a normalization clique problem when the live clique combines those
diseases.

### UI feature request

The edge already contains `biolink:clinical_approval_status=off_label_use`, but
the UI does not show it. This is a UI presentation gap, not missing source data.
