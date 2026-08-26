# Answer Coalesce API Reference

## Current CI Service

Base URL:

```text
https://answer-coalesce.ci.transltr.io/
```

Live OpenAPI observed on 2026-06-06:

- Title: `Answer coalesce`
- Service version: `3.1.0`
- TRAPI version: `1.5.0`
- Translator component: `KP`
- Team: `Ranking Agent`
- Infores: `infores:answer-coalesce`

Primary endpoints:

- `POST /query`: synchronous query. Request body is a TRAPI Response-like
  object with at least `message.query_graph`.
- `POST /asyncquery`: asynchronous query. Request body has `message`, optional
  `callback`, and optional `parameters`. Returns a job id immediately.
- `GET /query/jobs`: list active jobs.
- `GET /query/status/{job_id}`: check asynchronous job status.
- `GET /query/result/{job_id}`: fetch completed asynchronous result in the same
  response format as `/query`.

## Set QNode Fields

The input set node uses TRAPI QNode fields:

```json
{
  "categories": ["biolink:PhenotypicFeature"],
  "ids": ["uuid:1"],
  "member_ids": ["HP:0002378", "HP:0002019", "HP:0007146"],
  "set_interpretation": "MANY"
}
```

Supported `set_interpretation` enum values in the CI schema:

- `BATCH`
- `ALL`
- `MANY`

Use `MANY` for the usual Answer Coalesce use case where a set of clinical
features, genes, or other CURIEs should support enriched/coalesced answers.
Use `ALL` or `BATCH` only when the user explicitly asks for that semantics or
when reproducing a known workflow.

## QEdge Qualifier Constraints

Answer Coalesce accepts the same TRAPI QEdge `constraints.qualifiers` shape used
by one-hop Translator queries. Use one qualifier set object whose keys are
Biolink qualifier type CURIEs and whose values are qualifier values:

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

For chemical-gene regulation questions, prefer qualified `biolink:affects` over
invented directional predicates. Common object qualifier values:

- Broad up/down regulation: `object_aspect_qualifier =
  activity_or_abundance`; `object_direction_qualifier = increased` or
  `decreased`.
- Expression-specific: use `expression` as the object aspect.
- Activity-specific: use `activity` as the object aspect.
- Add `biolink:qualified_predicate = biolink:causes` only when causal wording
  or a known source pattern requires it.

## Name Resolver And Categories

Use Translator Name Resolver/Babel outputs as the source of truth for member
CURIEs and types. Do not replace Name Resolver-selected identifiers with
external ontology lookups. Babel may choose a preferred identifier from MONDO,
UMLS, HP, NCIT, or another namespace depending on the clique.

For the input QNode, use one category only: the smallest Biolink superclass
that covers every resolved member. For a clinical list that mixes disease and
phenotype concepts, use:

```json
"categories": ["biolink:DiseaseOrPhenotypicFeature"]
```

Do not add both `biolink:Disease` and `biolink:PhenotypicFeature` to the input
node. Do not split a single clinical feature list into separate set nodes
unless the user explicitly asks for that query shape.

## Example Payloads

### Phenotype Set To Disease

This pattern mirrors the CI OpenAPI default and the linked multi-CURIE
notebook pattern.

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

### Gene Set To Chemical Entity

The linked `MultiCurieQueries.ipynb` shows this common shape:

```json
{
  "message": {
    "query_graph": {
      "nodes": {
        "input": {
          "categories": ["biolink:Gene"],
          "ids": ["uuid:1"],
          "member_ids": ["NCBIGene:5297", "NCBIGene:5298", "NCBIGene:5290"],
          "set_interpretation": "MANY"
        },
        "output": {
          "categories": ["biolink:ChemicalEntity"]
        }
      },
      "edges": {
        "edge_0": {
          "subject": "output",
          "object": "input",
          "predicates": ["biolink:related_to"]
        }
      }
    }
  }
}
```

### Chemical Set To Increased Gene Activity

Resolve the chemicals with Translator Name Resolver/Babel first, then put the
resolved chemical member CURIEs in `member_ids`:

```json
{
  "message": {
    "query_graph": {
      "nodes": {
        "input": {
          "categories": ["biolink:ChemicalEntity"],
          "ids": ["uuid:1"],
          "member_ids": ["<resolved chemical CURIE 1>", "<resolved chemical CURIE 2>"],
          "set_interpretation": "MANY"
        },
        "output": {
          "categories": ["biolink:Gene"]
        }
      },
      "edges": {
        "edge_0": {
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
      }
    }
  }
}
```

## Notes From Linked Notebooks

- `documentation/AnswerCoalescence.ipynb` demonstrates older property and graph
  coalescence endpoints under `https://answercoalesce.renci.org/1.4/coalesce/`.
  Do not use those endpoints for current CI set-input queries unless the user
  asks to reproduce that older notebook behavior.
- `documentation/MultiCurieQueries.ipynb` demonstrates the current multi-CURIE
  query graph construction pattern: synthetic `ids`, `member_ids`,
  `set_interpretation="MANY"`, one `input` node, one `output` node, and one
  `edge_0`.
- Some notebook helper examples pass booleans as strings. Do not copy that
  pattern; use explicit `--input-role subject` or `--input-role object` and
  inspect the generated edge before submission.

## Result Inspection

Inspect these response fields:

- `message.results`: result list.
- `result.node_bindings["output"]`: output CURIE bindings.
- `result.analyses[].score`: ranking score when present.
- `result.analyses[].edge_bindings["edge_0"]`: KG edge IDs supporting the
  query edge.
- `message.knowledge_graph.nodes`: output labels and categories.
- `message.knowledge_graph.edges`: actual returned predicates, attributes, and
  sources.
- `message.auxiliary_graphs`: enrichment/support graphs.

Common edge attributes to surface when present:

- `biolink:p_value`
- `biolink:qualified_predicate`
- `biolink:object_aspect_qualifier`
- `biolink:object_direction_qualifier`
- enrichment or support-graph attributes
- provenance/source attributes
