# Normalization Triage Guide

## Evidence Model

Treat normalization as a sequence of distinct artifacts:

1. **Source record** - an ontology or identifier system publishes a label,
   synonym, cross-reference, or relationship.
2. **Babel concordance edge** - Babel extracts or generates a subject,
   predicate, object, and provenance source from an input.
3. **Babel clique** - clique-building rules decide which identifiers are
   equivalent and select preferred identifiers, labels, and semantic types.
4. **NodeNorm response** - a deployment serves a particular Babel build with
   particular request options and optional conflation.
5. **Name Resolver document** - a search index exposes names and synonyms for
   finding a candidate CURIE; it can reflect conflated or separately indexed
   data.
6. **ARA response** - an ARA normalizes source identifiers while constructing
   its TRAPI knowledge graph.
7. **ARS merge** - merged processing can combine or rewrite nodes from ARA
   children.
8. **UI rendering** - the UI chooses which identifier, label, category, and
   count to display.

Evidence from a later layer does not identify which earlier layer introduced
the value. Find the first layer where observed behavior differs from expected
behavior.

## Clique Versus Concordance

Use two explicit sets:

- `C0`: identifiers in the starting CURIE's live NodeNorm
  `equivalent_identifiers` list.
- `R`: identifiers reachable through recursive Babel concordance from the
  starting CURIE.

For every identifier in `R`, query the same NodeNorm deployment and classify
it:

| Classification | Meaning |
| --- | --- |
| `starting clique` | Its preferred clique identifier equals the starting clique's preferred identifier, or it is explicitly in `C0`. |
| `other clique` | NodeNorm resolves it, but to a different preferred clique identifier. |
| `unresolved` | NodeNorm returns `null` for the identifier. |
| `unavailable` | The lookup failed; this is not the same as unresolved. |

`R` can be much larger than `C0`. The difference `R - C0` is useful for finding
nearby mappings, alternate cliques, and unresolved identifiers, but those
identifiers are not members of the starting clique merely because they are
reachable.

## Mapping Route Accounting

Represent each concordance assertion as a separate row:

| From | Predicate | To | Babel provenance source | Role |
| --- | --- | --- | --- | --- |
| identifier | source predicate | identifier | input filename or source name | direct, bridge, or duplicate assertion |

Apply these rules:

- Preserve the stored subject and object direction even if graph traversal uses
  the edge in reverse.
- Count parallel edges separately when their provenance source or predicate
  differs.
- A direct mapping asserted by two sources is two evidence edges but one
  endpoint pair.
- A route through an intermediate identifier is distinct from a direct edge.
- A route containing sources A and B is a mixed-source route, not a route "from
  A" alone.
- The provenance filename identifies the Babel input that supplied the row. It
  does not by itself prove that the source's current public record still
  contains the assertion.
- A shortest path proves connectivity, not uniqueness. Search the recursive
  edge list for additional direct edges and alternate bridge identifiers.

When proposing a clique split, identify every independent route that still
connects the disputed concepts. Removing one edge is insufficient if another
direct edge or bridge remains.

## Name And Type Drift

Analyze these independently:

### Preferred identifier

Determine whether clique membership is correct before evaluating which member
should lead the clique. A surprising preferred prefix may be a prioritization
problem rather than an equivalence problem.

### Preferred label

Compare:

- the source label on each equivalent identifier;
- Babel's selected clique label;
- NodeNorm's `id.label`;
- the ARA knowledge-graph node name; and
- the label rendered by the UI.

The preferred identifier and preferred label can originate from different
records. Matching names do not establish identity.

### Semantic types

Record both the clique-level NodeNorm types and any per-identifier types.
Determine whether an unexpectedly broad or shifted type originates in a source
record, Babel's type aggregation, a request option, an ARA rewrite, or UI
compression.

### Name Resolver

Use Name Resolver to find candidate CURIEs, not to prove equivalence. Preserve
the query text and any conflation-related request behavior. A search synonym
can be present even when the corresponding identifier is outside the
unconflated NodeNorm clique.

## Layer Attribution

### Authoritative source assertion

Choose this when the source record itself contains the disputed equivalence,
cross-reference, label, synonym, or semantic type and Babel faithfully carries
it forward. Recommend upstream correction or an explicit Babel exclusion when
upstream correction is not practical.

### Babel concordance extraction or predicate interpretation

Choose this when Babel creates an equivalence-strength concordance edge from a
source relation that is absent, weaker, broader, narrower, related-only, or
otherwise unsuitable for identity.

### Babel clique construction or preferred-term selection

Choose this when the concordance rows are represented correctly but clique
construction, conflict handling, type separation, identifier priority, or
preferred-label selection produces the bad result.

### NodeNorm load, service, or deployment

Choose this when the expected Babel output exists but the service is stale,
partially loaded, unavailable, or serving a different build. State the exact
environment and versions. A bug fixed in Babel is not fixed for users until
the affected NodeNorm environment serves that build.

### Request options or conflation

Choose this when results differ because of `conflate`,
`drug_chemical_conflate`, `individual_types`, taxon inclusion, or another
request option. For chemical identity, evaluate the base clique with
drug-chemical conflation disabled.

### Name Resolver indexing or search presentation

Choose this when NodeNorm clique membership and preferred values are correct
but Name Resolver search terms, ranking, counts, or displayed synonyms are
wrong or misleading.

### ARA-specific normalization

Choose this when live NodeNorm gives the expected result but one ARA child
already contains a different normalized identifier, name, or category. Preserve
the child PK, source identifier, and normalized node.

### ARS merge or post-processing

Choose this when ARA children are correct and the anomaly first appears in an
intermediate or final merged response.

### UI presentation

Choose this when the stored final TRAPI response is correct and only the
rendered identifier, label, category, count, or grouping is wrong.

## Retrieval Failures

- Explicit JSON `null`: the service answered and did not normalize that CURIE.
- Missing response key: the service response is incomplete or follows a
  different contract; report it separately.
- HTTP, DNS, timeout, or invalid JSON error: the evidence is unavailable.
- Version mismatch between Babel Explorer and NodeNorm: the cross-reference and
  clique comparison is invalid for a conclusion-bearing run.

Keep partial successful evidence, but never replace a failed comparison with an
assumption.

## Report Template

```markdown
## Conclusion

<First faulty layer and direct finding.>

## Observed Behavior

- Environment and retrieval time:
- Answer or issue:
- Input identifier:
- Observed preferred identifier, label, and types:
- Expected distinction or equivalence:

## Served Clique

| Environment | Babel version | Preferred ID | Preferred label | Members | Difference |
| --- | --- | --- | --- | ---: | --- |

## Mapping Routes

| Route | From | Predicate | To | Babel source | Source-record check |
| --- | --- | --- | --- | --- | --- |

## Recursive Classification

| Identifier | Label | Classification | Clique leader |
| --- | --- | --- | --- |

## Layer Diagnosis

<Evidence for the first faulty layer and evidence ruling out later layers.>

## Next Action

<Exact mapping, rule, build, deployment, request, ARA, merge stage, or UI field
to change; list all independent routes that must be addressed.>
```
