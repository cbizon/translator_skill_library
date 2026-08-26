#!/usr/bin/env python3
"""Inspect an entity across merged and individual ARA TRAPI responses."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable


def trapi_message(response: dict[str, Any]) -> dict[str, Any]:
    fields = response.get("fields")
    if isinstance(fields, dict):
        data = fields.get("data")
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            return data["message"]
    message = response.get("message")
    if isinstance(message, dict):
        return message
    raise KeyError("Response has no TRAPI message")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def summarize_value(value: Any) -> dict[str, Any]:
    encoded = canonical_json(value)
    summary: dict[str, Any] = {
        "type": type_name(value),
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16],
    }
    if isinstance(value, list):
        summary["length"] = len(value)
        summary["preview"] = value[:3]
    elif isinstance(value, dict):
        summary["key_count"] = len(value)
        summary["keys"] = sorted(value)[:10]
    else:
        summary["value"] = value
    return summary


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def semantic_attribute_key(attribute: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(attribute.get("attribute_type_id")),
        str(attribute.get("original_attribute_name")),
        canonical_json(attribute.get("value")),
    )


def duplicate_attributes(attributes: Any) -> list[dict[str, Any]]:
    if not isinstance(attributes, list):
        return []
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for attribute in attributes:
        if isinstance(attribute, dict):
            groups[semantic_attribute_key(attribute)].append(attribute)
    duplicates = []
    for values in groups.values():
        if len(values) < 2:
            continue
        exemplar = values[0]
        duplicates.append(
            {
                "count": len(values),
                "attribute_type_id": exemplar.get("attribute_type_id"),
                "original_attribute_name": exemplar.get("original_attribute_name"),
                "value": summarize_value(exemplar.get("value")),
            }
        )
    return sorted(
        duplicates,
        key=lambda item: (
            -item["count"],
            str(item["original_attribute_name"]),
            str(item["attribute_type_id"]),
        ),
    )


def duplicate_json_items(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    encoded = [canonical_json(value) for value in values]
    counts = Counter(encoded)
    first_values = {}
    for value, key in zip(values, encoded, strict=True):
        first_values.setdefault(key, value)
    return [
        {
            "count": count,
            "value": summarize_value(first_values[key]),
        }
        for key, count in sorted(counts.items())
        if count > 1
    ]


def find_node_ids(
    nodes: dict[str, Any],
    entity: str,
) -> list[str]:
    if entity in nodes:
        return [entity]
    needle = entity.casefold()
    exact = [
        node_id
        for node_id, node in nodes.items()
        if isinstance(node, dict)
        and isinstance(node.get("name"), str)
        and node["name"].casefold() == needle
    ]
    if exact:
        return sorted(exact)
    partial = [
        node_id
        for node_id, node in nodes.items()
        if isinstance(node, dict)
        and isinstance(node.get("name"), str)
        and needle in node["name"].casefold()
    ]
    return sorted(partial)


def result_contains_node(result: dict[str, Any], node_id: str) -> bool:
    node_bindings = result.get("node_bindings") or {}
    if not isinstance(node_bindings, dict):
        return False
    for bindings in node_bindings.values():
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            if isinstance(binding, dict) and binding.get("id") == node_id:
                return True
    return False


def string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item


def support_graphs_from_edge(edge: dict[str, Any]) -> list[str]:
    graph_ids = []
    attributes = edge.get("attributes") or []
    if not isinstance(attributes, list):
        return graph_ids
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get("attribute_type_id") != "biolink:support_graphs":
            continue
        graph_ids.extend(string_values(attribute.get("value")))
    return graph_ids


def analysis_seed_ids(
    result: dict[str, Any],
) -> tuple[set[str], set[str], list[dict[str, Any]]]:
    edge_ids: set[str] = set()
    graph_ids: set[str] = set()
    analysis_summaries = []
    analyses = result.get("analyses") or []
    if not isinstance(analyses, list):
        return edge_ids, graph_ids, analysis_summaries
    for analysis_index, analysis in enumerate(analyses):
        if not isinstance(analysis, dict):
            continue
        bindings = analysis.get("edge_bindings") or {}
        duplicate_bindings = []
        if isinstance(bindings, dict):
            for qedge_id, qedge_bindings in bindings.items():
                ids = []
                if isinstance(qedge_bindings, list):
                    ids = [
                        binding["id"]
                        for binding in qedge_bindings
                        if isinstance(binding, dict)
                        and isinstance(binding.get("id"), str)
                    ]
                edge_ids.update(ids)
                counts = Counter(ids)
                repeated = [
                    {"edge_id": edge_id, "count": count}
                    for edge_id, count in sorted(counts.items())
                    if count > 1
                ]
                if repeated:
                    duplicate_bindings.append(
                        {"qedge_id": qedge_id, "duplicates": repeated}
                    )
        support_graphs = list(string_values(analysis.get("support_graphs")))
        graph_ids.update(support_graphs)
        analysis_summaries.append(
            {
                "analysis_index": analysis_index,
                "resource_id": analysis.get("resource_id"),
                "score": analysis.get("score"),
                "direct_edge_ids": sorted(
                    {
                        binding["id"]
                        for qedge_bindings in bindings.values()
                        if isinstance(qedge_bindings, list)
                        for binding in qedge_bindings
                        if isinstance(binding, dict)
                        and isinstance(binding.get("id"), str)
                    }
                )
                if isinstance(bindings, dict)
                else [],
                "support_graph_ids": support_graphs,
                "duplicate_edge_bindings": duplicate_bindings,
            }
        )
    return edge_ids, graph_ids, analysis_summaries


def reachable_support(
    message: dict[str, Any],
    seed_edge_ids: set[str],
    seed_graph_ids: set[str],
) -> dict[str, Any]:
    knowledge_graph = message.get("knowledge_graph") or {}
    edges = knowledge_graph.get("edges") or {}
    auxiliary_graphs = message.get("auxiliary_graphs") or {}
    if not isinstance(edges, dict):
        edges = {}
    if not isinstance(auxiliary_graphs, dict):
        auxiliary_graphs = {}

    pending_edges = deque(sorted(seed_edge_ids))
    pending_graphs = deque(sorted(seed_graph_ids))
    seen_edges: set[str] = set()
    seen_graphs: set[str] = set()
    missing_edges: set[str] = set()
    missing_graphs: set[str] = set()

    while pending_edges or pending_graphs:
        while pending_graphs:
            graph_id = pending_graphs.popleft()
            if graph_id in seen_graphs:
                continue
            seen_graphs.add(graph_id)
            graph = auxiliary_graphs.get(graph_id)
            if not isinstance(graph, dict):
                missing_graphs.add(graph_id)
                continue
            for edge_id in graph.get("edges") or []:
                if isinstance(edge_id, str) and edge_id not in seen_edges:
                    pending_edges.append(edge_id)

        if pending_edges:
            edge_id = pending_edges.popleft()
            if edge_id in seen_edges:
                continue
            seen_edges.add(edge_id)
            edge = edges.get(edge_id)
            if not isinstance(edge, dict):
                missing_edges.add(edge_id)
                continue
            for graph_id in support_graphs_from_edge(edge):
                if graph_id not in seen_graphs:
                    pending_graphs.append(graph_id)

    edge_attribute_duplicates = []
    edge_source_duplicates = []
    for edge_id in sorted(seen_edges):
        edge = edges.get(edge_id)
        if not isinstance(edge, dict):
            continue
        attribute_duplicates = duplicate_attributes(edge.get("attributes"))
        if attribute_duplicates:
            edge_attribute_duplicates.append(
                {"edge_id": edge_id, "duplicates": attribute_duplicates}
            )
        source_duplicates = duplicate_json_items(edge.get("sources"))
        if source_duplicates:
            edge_source_duplicates.append(
                {"edge_id": edge_id, "duplicates": source_duplicates}
            )

    auxiliary_edge_duplicates = []
    for graph_id in sorted(seen_graphs):
        graph = auxiliary_graphs.get(graph_id)
        if not isinstance(graph, dict):
            continue
        duplicates = duplicate_json_items(graph.get("edges"))
        if duplicates:
            auxiliary_edge_duplicates.append(
                {"graph_id": graph_id, "duplicates": duplicates}
            )

    return {
        "reachable_edge_ids": sorted(seen_edges),
        "reachable_support_graph_ids": sorted(seen_graphs),
        "missing_edge_ids": sorted(missing_edges),
        "missing_support_graph_ids": sorted(missing_graphs),
        "duplicate_edge_attributes": edge_attribute_duplicates,
        "duplicate_edge_sources": edge_source_duplicates,
        "duplicate_auxiliary_graph_edges": auxiliary_edge_duplicates,
    }


def inspect_node(
    message: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    knowledge_graph = message.get("knowledge_graph") or {}
    nodes = knowledge_graph.get("nodes") or {}
    node = nodes.get(node_id) or {}
    results = message.get("results") or []
    matching_results = [
        (index, result)
        for index, result in enumerate(results)
        if isinstance(result, dict) and result_contains_node(result, node_id)
    ]

    seed_edge_ids: set[str] = set()
    seed_graph_ids: set[str] = set()
    result_summaries = []
    for result_index, result in matching_results:
        edge_ids, graph_ids, analyses = analysis_seed_ids(result)
        seed_edge_ids.update(edge_ids)
        seed_graph_ids.update(graph_ids)
        result_summaries.append(
            {
                "result_index": result_index,
                "analyses": analyses,
            }
        )

    support = reachable_support(message, seed_edge_ids, seed_graph_ids)
    return {
        "node_id": node_id,
        "name": node.get("name"),
        "categories": node.get("categories") or [],
        "attribute_count": len(node.get("attributes") or []),
        "duplicate_node_attributes": duplicate_attributes(node.get("attributes")),
        "matching_result_count": len(matching_results),
        "matching_results": result_summaries,
        **support,
    }


def inspect_context(
    payload: dict[str, Any],
    entity: str,
    parent_pk: str | None = None,
) -> dict[str, Any]:
    reports = []
    errors = []
    for query in payload.get("translator_queries") or []:
        if parent_pk is not None and query.get("parent_pk") != parent_pk:
            continue
        for response_record in query.get("responses") or []:
            try:
                message = trapi_message(response_record["response"])
                knowledge_graph = message.get("knowledge_graph") or {}
                nodes = knowledge_graph.get("nodes") or {}
                if not isinstance(nodes, dict):
                    raise TypeError("TRAPI knowledge_graph.nodes is not an object")
                node_ids = find_node_ids(nodes, entity)
                reports.append(
                    {
                        "environment": query.get("environment"),
                        "parent_pk": query.get("parent_pk"),
                        "role": response_record.get("role"),
                        "actor_agent": response_record.get("actor_agent"),
                        "child_pk": response_record.get("child_pk"),
                        "merge_stage": response_record.get("merge_stage"),
                        "merged_through_actor": response_record.get(
                            "merged_through_actor"
                        ),
                        "result_count": len(message.get("results") or []),
                        "matched_node_ids": node_ids,
                        "nodes": [
                            inspect_node(message, node_id) for node_id in node_ids
                        ],
                    }
                )
            except Exception as exc:  # noqa: BLE001 - retain response-level errors.
                errors.append(
                    {
                        "environment": query.get("environment"),
                        "parent_pk": query.get("parent_pk"),
                        "role": response_record.get("role"),
                        "actor_agent": response_record.get("actor_agent"),
                        "child_pk": response_record.get("child_pk"),
                        "merge_stage": response_record.get("merge_stage"),
                        "merged_through_actor": response_record.get(
                            "merged_through_actor"
                        ),
                        "error": str(exc),
                    }
                )
    return {
        "repository": payload.get("repository"),
        "issue": (payload.get("primary") or {}).get("issue"),
        "entity": entity,
        "parent_pk_filter": parent_pk,
        "reports": reports,
        "inspection_errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect an entity across merged and ARA TRAPI responses."
    )
    parser.add_argument("context", type=Path, help="Collected issue context JSON")
    parser.add_argument("--entity", required=True, help="Entity name or CURIE")
    parser.add_argument(
        "--parent-pk",
        help="Inspect only this parent PK when context contains multiple queries.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    try:
        payload = json.loads(args.context.read_text(encoding="utf-8"))
        report = inspect_context(payload, args.entity, args.parent_pk)
        if args.parent_pk and not report["reports"]:
            raise ValueError(f"Parent PK not found in context: {args.parent_pk}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        matched_responses = sum(
            bool(item["matched_node_ids"]) for item in report["reports"]
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "responses_inspected": len(report["reports"]),
                    "responses_with_matches": matched_responses,
                    "inspection_errors": len(report["inspection_errors"]),
                },
                sort_keys=True,
            )
        )
        return 2 if report["inspection_errors"] else 0
    except Exception as exc:  # noqa: BLE001 - command must fail visibly.
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
