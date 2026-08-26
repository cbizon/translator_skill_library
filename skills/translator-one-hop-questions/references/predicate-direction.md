# Predicate Direction Notes

Biolink predicates are directional unless the model says otherwise. A Translator
one-hop skill should normalize the user's requested relation to the canonical
Biolink predicate, then put the known entity on the canonical side of that
predicate.

## Common One-Hop Patterns

| User question shape | Input role | Output role | Predicate |
| --- | --- | --- | --- |
| diseases caused by gene | subject | object | `biolink:causes` |
| genes that cause disease | object | subject | `biolink:causes` |
| genes associated with disease | object | subject | `biolink:associated_with` |
| genes contributing to disease | object | subject | `biolink:contributes_to` |
| drugs treating disease | object | subject | `biolink:treats` |
| diseases treated by drug | subject | object | `biolink:treats` |
| phenotypes of gene or disease | subject | object | `biolink:has_phenotype` |
| chemicals upregulating or downregulating gene | object | subject | `biolink:affects` plus object aspect/direction qualifiers |
| genes upregulated or downregulated by chemical | subject | object | `biolink:affects` plus object aspect/direction qualifiers |

## Practical Rule

Do not create inverse predicate names unless Biolink defines them and the target
Translator services support them. If Biolink defines the inverse wording rather
than the user's surface wording, use the defined predicate and reverse the query
edge as needed.

When in doubt:

1. Resolve the input entity and categories.
2. Match the user phrase to a Biolink predicate.
3. Decide whether the known input entity is the canonical subject or object.
4. Check Retriever `/meta_knowledge_graph` for that subject category, predicate,
   and object category.
5. Ask the user before submitting if the direction or predicate remains
   ambiguous.

## Retriever Metadata Check

Retriever metadata is the first practical validation layer for one-hop lookup
queries. It can say whether a subject-category / predicate / object-category
shape is supported by Retriever. It does not guarantee that a specific input
CURIE has results.

For disease-to-gene questions, check both directions when appropriate:

- `biolink:Gene` -> predicate -> `biolink:Disease`
- `biolink:Disease` -> predicate -> `biolink:Gene`

If a predicate is schema-supported but returns no results for a CURIE, try other
metadata-supported predicates only after making the change explicit. For
gene-disease questions, useful alternatives may include:

- `biolink:associated_with`
- `biolink:gene_associated_with_condition`
- `biolink:contributes_to`
- `biolink:predisposes_to_condition`
- `biolink:related_to`

For chemical-gene directional questions, start with qualified
`biolink:affects` before predicate widening. Common qualifier sets include:

- Upregulates gene broadly: `biolink:object_aspect_qualifier =
  activity_or_abundance`; `biolink:object_direction_qualifier = increased`.
- Downregulates gene broadly: `biolink:object_aspect_qualifier =
  activity_or_abundance`; `biolink:object_direction_qualifier = decreased`.
- Increases/decreases expression: use `expression` as the object aspect.
- Increases/decreases activity: use `activity` as the object aspect.

If the qualified `affects` query has no usable results, try unqualified
`biolink:affects` before broadening to other Retriever-supported predicates.
