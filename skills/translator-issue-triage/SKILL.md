---
name: translator-issue-triage
description: Investigate NCATSTranslator/Feedback GitHub issues using live issue context and Biomedical Data Translator ARS/TRAPI evidence. Use when given a Feedback issue number or URL and asked to triage, diagnose, reproduce, comment on, or assign the issue; especially when the issue links Translator result pages, ARS primary keys, ARA responses, merged results, suspicious edges, duplicate attributes, provenance, normalization, ingest, UI, or component behavior.
---

# Translator Issue Triage

## Purpose

Turn a Feedback issue number or URL into a concise, evidence-backed diagnosis.
Inspect the issue, linked Translator queries, merged ARS response, individual ARA
responses, relevant TRAPI bindings and support graphs, then post one useful
comment and assign the issue when component ownership is supported.

## Workflow

Run bundled helper commands from this skill directory, which is the directory
containing this `SKILL.md`. Do not assume a user-specific installation path.

1. Normalize the input to an issue in `NCATSTranslator/Feedback`. Reject links
   to other repositories instead of silently operating on them.
2. Collect the issue, comments, directly referenced Feedback issues, GitHub
   timeline backlinks, Translator URLs, ARS parent metadata, intermediate merge
   stages, final merged child response, and every ARA child:

   ```bash
   uv run --isolated --no-project python \
     scripts/collect_issue_context.py \
     1356 \
     --output /tmp/feedback-1356.json
   ```

   A nonzero exit with an output file means one or more live retrievals failed.
   Read `retrieval_errors`; do not interpret a failed fetch as an empty result.
3. Read the issue, comments, and collected related issues before choosing what
   to inspect. Timeline backlinks often contain the direct component-owner
   discussion that is absent from the primary issue. Follow an explicit
   component-issue backlink to a Feedback issue when it concerns the same
   entity or behavior. Extract the entity, result, edge, attribute, predicate,
   or behavior named by the issue. Prioritize Translator links found in the
   primary issue. Treat queries from related issues as historical or
   comparative context unless the issue explicitly asks about them.
4. For a named entity or CURIE, compare the merged response with every ARA:

   ```bash
   uv run --isolated --no-project python \
     scripts/inspect_entity.py \
     /tmp/feedback-1356.json \
     --entity Gabapentin \
     --parent-pk aa6aa027-55d9-4259-8997-b2980e63658b \
     --output /tmp/feedback-1356-gabapentin.json
   ```

   The report identifies matching results, direct bindings, recursively
   reachable support edges, and duplicate attributes. Use `jq` against the
   collected raw payload when the issue requires a complete edge or another
   exact payload slice.
5. Determine where the problem first appears:
   - Merged only: merger or post-ARA processing.
   - One ARA only: that ARA or its ARA-specific Shepherd path.
   - All ARAs: inspect shared Retriever, ingest, normalization, and source data.
   - Payload correct but display wrong or absent: UI.
6. Read [references/triage-and-routing.md](references/triage-and-routing.md)
   before naming a faulty component, assigning an issue, or posting a comment.
7. Re-fetch current comments immediately before posting. Do not add a duplicate
   comment if the same finding is already present.
8. Post exactly one concise comment unless the user explicitly requests
   multiple comments. End every posted comment with the required disclaimer
   shown in [Comment Shape](#comment-shape). Invocation of this skill with an
   issue number or URL is permission to post the triage comment and add
   justified assignees.
9. Add, but never remove or replace, assignees only when ownership evidence is
   clear. Do not close, reopen, label, edit, or delete issue content unless the
   user explicitly asks.

If the user says `dry-run`, `draft`, `read-only`, or otherwise asks not to
mutate GitHub, return the proposed comment and assignment recommendation
without posting or changing assignees.

## Evidence Rules

- Start with the direct finding, then give the minimum payload evidence needed
  to verify it.
- Keep the visible portion of the comment scannable: state the finding,
  attribution, and requested action before any supporting detail.
- Put lengthy or optional evidence inside GitHub `<details>` blocks. Good
  candidates include per-ARA comparisons, PK inventories, support-graph traces,
  duplicate-attribute tables, and exact JSON.
- Never hide the primary finding, component attribution, required action,
  uncertainty that changes the conclusion, or a retrieval failure inside a
  `<details>` block.
- State the environment, parent PK, merged child PK, and relevant ARA child PKs.
- Use intermediate merge stages when available to identify the first merge that
  introduced the behavior.
- Distinguish observation from attribution. Say "the duplication first appears
  in the merged response" before saying "this points to the ARS merger."
- Trace result `node_bindings` and `analyses.edge_bindings`; recursively follow
  `support_graphs` through auxiliary graphs when the relevant edge is indirect.
- Include the complete edge, including attributes and sources, when that edge is
  load-bearing evidence. Do not replace fields with prose or ellipses. Put a
  lengthy complete edge inside a `<details>` block after summarizing its
  significance visibly.
- Compare semantic attributes by type, original name, and value. Ignore
  serializer-only differences such as added null fields.
- Preserve contradictory evidence and retrieval failures. Never manufacture a
  result or component diagnosis.
- Prefer an existing component-owner explanation, fix commit, or deployment
  status from a related issue over a new inference. Distinguish "fixed in code"
  from "deployed in this environment."

## Comment Shape

Use a short structure appropriate to the finding:

```markdown
I reproduced this using CI parent PK `<pk>`.

- **Finding:** <direct finding>
- **First appears in:** <layer or response>
- **Likely owner/action:** <component and reason, or next step>

<details>
<summary>Supporting evidence and identifiers</summary>

- Environment: `<environment>`
- Parent PK: `<parent-pk>`
- Merged child PK: `<merged-child-pk>`
- `<ARA actor>` child PK: `<ara-child-pk>` - <finding>

<exact JSON slice, complete edge, or other lengthy evidence when needed>

</details>

NOTE: This post has been auto-generated by the translator triage agent. If you find problems with the post, please make an issue at [cbizon/translator_skill_library](https://github.com/cbizon/translator_skill_library/issues).
```

Avoid dumping entire TRAPI responses. Link the original issue/query and quote
only the exact data needed to support the conclusion. Use one collapsed
`<details>` block by default; use a second only when it separates meaningfully
different evidence, and omit collapsed sections when there is no substantial
detail to hide. Give every block a specific `<summary>` rather than a generic
"Details" label. Preserve the disclaimer text and link exactly in every posted
comment, outside all collapsed sections.

## GitHub Mutations

Use authenticated `gh` commands. Write substantial comment text to a temporary
file to avoid shell quoting damage:

```bash
gh issue comment 1356 \
  --repo NCATSTranslator/Feedback \
  --body-file /tmp/feedback-1356-comment.md
```

For a supported assignment:

```bash
gh issue edit 1356 \
  --repo NCATSTranslator/Feedback \
  --add-assignee LOGIN
```

Report the resulting comment URL and confirmed assignee changes. Surface any
mutation failure directly.
