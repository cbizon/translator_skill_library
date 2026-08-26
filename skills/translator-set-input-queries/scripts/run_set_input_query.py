#!/usr/bin/env python3
"""Build and optionally run an Answer Coalesce set-input TRAPI query."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://answer-coalesce.ci.transltr.io"
SET_INTERPRETATIONS = {"BATCH", "ALL", "MANY"}
KNOWLEDGE_TYPES = {"lookup", "inferred"}
QUALIFIER_TYPE_ALIASES = {
    "qualified_predicate": "biolink:qualified_predicate",
    "object_aspect": "biolink:object_aspect_qualifier",
    "object_aspect_qualifier": "biolink:object_aspect_qualifier",
    "object_direction": "biolink:object_direction_qualifier",
    "object_direction_qualifier": "biolink:object_direction_qualifier",
    "subject_aspect": "biolink:subject_aspect_qualifier",
    "subject_aspect_qualifier": "biolink:subject_aspect_qualifier",
    "subject_direction": "biolink:subject_direction_qualifier",
    "subject_direction_qualifier": "biolink:subject_direction_qualifier",
}
ASPECT_QUALIFIER_ALIASES = {
    "activity or abundance": "activity_or_abundance",
    "activity_or_abundance": "activity_or_abundance",
    "activity": "activity",
    "abundance": "abundance",
    "expression": "expression",
    "degradation": "degradation",
}
DIRECTION_QUALIFIER_ALIASES = {
    "up": "increased",
    "upregulate": "increased",
    "upregulates": "increased",
    "upregulated": "increased",
    "increase": "increased",
    "increases": "increased",
    "increased": "increased",
    "down": "decreased",
    "downregulate": "decreased",
    "downregulates": "decreased",
    "downregulated": "decreased",
    "decrease": "decreased",
    "decreases": "decreased",
    "decreased": "decreased",
}


def parse_member_args(raw_member_ids: list[str], member_file: str | None) -> list[str]:
    members: list[str] = []
    for raw in raw_member_ids:
        for value in raw.replace(",", " ").split():
            value = value.strip()
            if value:
                members.append(value)
    if member_file:
        for line in Path(member_file).read_text().splitlines():
            value = line.split("#", 1)[0].strip()
            if value:
                members.append(value)
    seen: set[str] = set()
    deduped: list[str] = []
    for member in members:
        if member not in seen:
            seen.add(member)
            deduped.append(member)
    return deduped


def require_biolink(value: str, field_name: str) -> None:
    if not value.startswith("biolink:"):
        raise SystemExit(f"{field_name} must use a biolink: prefix: {value}")


def normalize_phrase(raw: str) -> str:
    return " ".join(raw.strip().lower().replace("-", " ").replace("_", " ").split())


def normalize_qualifier_type(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise SystemExit("Empty qualifier type")
    if value.startswith("biolink:"):
        return value
    normalized = normalize_phrase(value)
    if normalized in QUALIFIER_TYPE_ALIASES:
        return QUALIFIER_TYPE_ALIASES[normalized]
    underscore = normalized.replace(" ", "_")
    if underscore in QUALIFIER_TYPE_ALIASES:
        return QUALIFIER_TYPE_ALIASES[underscore]
    raise SystemExit(f"Qualifier type must use biolink: prefix or known shorthand: {raw}")


def normalize_aspect_qualifier(raw: str) -> str:
    value = raw.strip()
    return ASPECT_QUALIFIER_ALIASES.get(normalize_phrase(value), value)


def normalize_direction_qualifier(raw: str) -> str:
    value = raw.strip()
    return DIRECTION_QUALIFIER_ALIASES.get(normalize_phrase(value), value)


def parse_qualifier(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise SystemExit(f"Qualifier must be TYPE=VALUE: {raw!r}")
    qualifier_type, qualifier_value = raw.split("=", 1)
    qualifier_type = normalize_qualifier_type(qualifier_type)
    qualifier_value = qualifier_value.strip()
    if not qualifier_value:
        raise SystemExit(f"Qualifier {qualifier_type} must have a non-empty value")
    if qualifier_type.endswith("_aspect_qualifier"):
        qualifier_value = normalize_aspect_qualifier(qualifier_value)
    elif qualifier_type.endswith("_direction_qualifier"):
        qualifier_value = normalize_direction_qualifier(qualifier_value)
    elif qualifier_type == "biolink:qualified_predicate":
        require_biolink(qualifier_value, "--qualified-predicate")
    return qualifier_type, qualifier_value


def build_qualifier_constraints(args: argparse.Namespace) -> dict[str, str] | None:
    qualifiers: dict[str, str] = {}
    if args.qualified_predicate:
        require_biolink(args.qualified_predicate, "--qualified-predicate")
        qualifiers["biolink:qualified_predicate"] = args.qualified_predicate
    if args.object_aspect_qualifier:
        qualifiers["biolink:object_aspect_qualifier"] = normalize_aspect_qualifier(
            args.object_aspect_qualifier
        )
    if args.object_direction_qualifier:
        qualifiers["biolink:object_direction_qualifier"] = normalize_direction_qualifier(
            args.object_direction_qualifier
        )
    for raw_qualifier in args.qualifier or []:
        qualifier_type, qualifier_value = parse_qualifier(raw_qualifier)
        qualifiers[qualifier_type] = qualifier_value
    if qualifiers and not args.predicate:
        raise SystemExit("QEdge qualifiers require --predicate; for chemical-gene direction use --predicate biolink:affects.")
    return qualifiers or None


def build_query(args: argparse.Namespace, members: list[str]) -> dict[str, Any]:
    if not members:
        raise SystemExit("At least one --member-id, --member-ids value, or --member-file entry is required.")
    require_biolink(args.input_category, "--input-category")
    require_biolink(args.output_category, "--output-category")
    if args.predicate:
        require_biolink(args.predicate, "--predicate")
    set_interpretation = args.set_interpretation.upper()
    if set_interpretation not in SET_INTERPRETATIONS:
        allowed = ", ".join(sorted(SET_INTERPRETATIONS))
        raise SystemExit(f"--set-interpretation must be one of: {allowed}")

    input_node: dict[str, Any] = {
        "categories": [args.input_category],
        "ids": [args.set_id],
        "member_ids": members,
        "set_interpretation": set_interpretation,
    }
    output_node: dict[str, Any] = {"categories": [args.output_category]}

    if args.input_role == "subject":
        subject = "input"
        obj = "output"
    else:
        subject = "output"
        obj = "input"

    edge: dict[str, Any] = {"subject": subject, "object": obj}
    if args.predicate:
        edge["predicates"] = [args.predicate]
    if args.knowledge_type:
        edge["knowledge_type"] = args.knowledge_type
    qualifier_constraints = build_qualifier_constraints(args)
    if qualifier_constraints:
        edge["constraints"] = {"qualifiers": [qualifier_constraints]}

    query: dict[str, Any] = {
        "message": {
            "query_graph": {
                "nodes": {"input": input_node, "output": output_node},
                "edges": {"edge_0": edge},
            }
        }
    }
    return query


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    return read_json(request, timeout)


def get_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    return read_json(request, timeout)


def read_json(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {request.full_url}:\n{body}") from exc
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise SystemExit(f"Expected a JSON object from {request.full_url}, got {type(parsed).__name__}")
    return parsed


def submit_sync(args: argparse.Namespace, query: dict[str, Any]) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/query"
    return post_json(url, query, args.http_timeout)


def submit_async(args: argparse.Namespace, query: dict[str, Any]) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/asyncquery"
    payload: dict[str, Any] = {"message": query["message"]}
    if args.callback:
        payload["callback"] = args.callback
    params: dict[str, Any] = {}
    if args.pvalue_threshold is not None:
        params["pvalue_threshold"] = args.pvalue_threshold
    if args.max_rules is not None:
        params["max_rules"] = args.max_rules
    if params:
        payload["parameters"] = params

    submitted = post_json(url, payload, args.http_timeout)
    job_id = extract_job_id(submitted)
    if not args.poll:
        return submitted

    deadline = time.monotonic() + args.timeout
    status_url = f"{args.base_url.rstrip('/')}/query/status/{job_id}"
    result_url = f"{args.base_url.rstrip('/')}/query/result/{job_id}"
    last_status: dict[str, Any] = submitted
    while time.monotonic() < deadline:
        last_status = get_json(status_url, args.http_timeout)
        status_text = json.dumps(last_status).lower()
        if any(token in status_text for token in ["complete", "completed", "done", "success", "succeeded"]):
            return get_json(result_url, args.http_timeout)
        if any(token in status_text for token in ["failed", "error"]):
            raise SystemExit(f"Async job {job_id} failed:\n{json.dumps(last_status, indent=2)}")
        time.sleep(args.poll_interval)
    raise SystemExit(f"Timed out waiting for async job {job_id}; last status:\n{json.dumps(last_status, indent=2)}")


def extract_job_id(payload: dict[str, Any]) -> str:
    for key in ("job_id", "id", "pk"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    nested = payload.get("job")
    if isinstance(nested, dict):
        for key in ("job_id", "id", "pk"):
            value = nested.get(key)
            if isinstance(value, str) and value:
                return value
    raise SystemExit(f"Could not find job id in async response:\n{json.dumps(payload, indent=2)}")


def write_payload(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        Path(output).write_text(text + "\n")
    else:
        print(text)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "__root__" in value:
        return as_list(value["__root__"])
    return [value]


def first_score(result: dict[str, Any]) -> Any:
    analyses = as_list(result.get("analyses"))
    for analysis in analyses:
        if isinstance(analysis, dict) and "score" in analysis:
            return analysis["score"]
    return ""


def binding_ids(bindings: Any) -> list[str]:
    ids: list[str] = []
    for binding in as_list(bindings):
        if isinstance(binding, dict) and isinstance(binding.get("id"), str):
            ids.append(binding["id"])
    return ids


def edge_binding_ids(result: dict[str, Any], edge_key: str = "edge_0") -> list[str]:
    ids: list[str] = []
    for analysis in as_list(result.get("analyses")):
        if not isinstance(analysis, dict):
            continue
        edge_bindings = analysis.get("edge_bindings", {})
        if isinstance(edge_bindings, dict):
            ids.extend(binding_ids(edge_bindings.get(edge_key)))
    return ids


def attr_value(attributes: Any, attr_type: str) -> Any:
    for attr in as_list(attributes):
        if not isinstance(attr, dict):
            continue
        if attr.get("attribute_type_id") == attr_type:
            return attr.get("value")
    return ""


def attr_values(attributes: Any, attr_type: str) -> list[Any]:
    values: list[Any] = []
    for attr in as_list(attributes):
        if not isinstance(attr, dict):
            continue
        if attr.get("attribute_type_id") == attr_type:
            value = attr.get("value")
            for item in as_list(value):
                if item != "" and item is not None and item not in values:
                    values.append(item)
    return values


def qualifier_values(qualifiers: Any, qualifier_type: str) -> list[Any]:
    values: list[Any] = []
    for qualifier in as_list(qualifiers):
        if not isinstance(qualifier, dict):
            continue
        if qualifier.get("qualifier_type_id") == qualifier_type:
            value = qualifier.get("qualifier_value")
            if value != "" and value is not None and value not in values:
                values.append(value)
    return values


def edge_semantic_values(edge: dict[str, Any], semantic_type: str) -> list[Any]:
    values = qualifier_values(edge.get("qualifiers"), semantic_type)
    for value in attr_values(edge.get("attributes"), semantic_type):
        if value not in values:
            values.append(value)
    return values


def query_member_ids(message: dict[str, Any]) -> set[str]:
    query_graph = message.get("query_graph")
    if not isinstance(query_graph, dict):
        return set()
    nodes = query_graph.get("nodes")
    if not isinstance(nodes, dict):
        return set()
    member_ids: set[str] = set()
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        for member_id in as_list(node.get("member_ids")):
            if isinstance(member_id, str) and member_id:
                member_ids.add(member_id)
    return member_ids


def support_graph_ids(edge: dict[str, Any]) -> list[str]:
    return [str(value) for value in attr_values(edge.get("attributes"), "biolink:support_graphs")]


def count_matched_inputs(
    edge_ids: list[str],
    member_ids: set[str],
    edges: dict[str, Any],
    auxiliary_graphs: dict[str, Any],
) -> int:
    if not member_ids:
        return 0
    matched: set[str] = set()

    def inspect_edge(edge: Any) -> None:
        if not isinstance(edge, dict):
            return
        for endpoint in (edge.get("subject"), edge.get("object")):
            if isinstance(endpoint, str) and endpoint in member_ids:
                matched.add(endpoint)

    for edge_id in edge_ids:
        edge = edges.get(edge_id)
        inspect_edge(edge)
        if not isinstance(edge, dict):
            continue
        for support_graph_id in support_graph_ids(edge):
            support_graph = auxiliary_graphs.get(support_graph_id)
            if not isinstance(support_graph, dict):
                continue
            for support_edge_id in as_list(support_graph.get("edges")):
                if isinstance(support_edge_id, str):
                    inspect_edge(edges.get(support_edge_id))
    return len(matched)


def summarize_response(payload: dict[str, Any], limit: int) -> str:
    message = payload.get("message", {})
    if not isinstance(message, dict):
        return "No TRAPI message object found in response."

    results = as_list(message.get("results"))
    kg = message.get("knowledge_graph") or {}
    if not isinstance(kg, dict):
        kg = {}
    nodes = kg.get("nodes") or {}
    edges = kg.get("edges") or {}
    aux = message.get("auxiliary_graphs") or {}
    member_ids = query_member_ids(message)

    lines = [
        f"status: {payload.get('status', '')}",
        f"results: {len(results)}",
        f"knowledge_graph_nodes: {len(nodes) if isinstance(nodes, dict) else 0}",
        f"knowledge_graph_edges: {len(edges) if isinstance(edges, dict) else 0}",
        f"auxiliary_graphs: {len(aux) if isinstance(aux, dict) else 0}",
    ]

    logs = as_list(payload.get("logs"))
    if logs:
        lines.append(f"logs: {len(logs)}")
        for log in logs[:5]:
            if isinstance(log, dict):
                lines.append(f"- {log.get('level', '')}: {log.get('message', '')}")

    rows_by_id: dict[str, dict[str, Any]] = {}
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        output_ids = binding_ids((result.get("node_bindings") or {}).get("output"))
        edge_ids = edge_binding_ids(result)
        p_values: list[Any] = []
        matched_input_count = count_matched_inputs(edge_ids, member_ids, edges, aux)
        for edge_id in edge_ids:
            edge = edges.get(edge_id) if isinstance(edges, dict) else None
            if isinstance(edge, dict):
                p_value = attr_value(edge.get("attributes"), "biolink:p_value")
                if p_value != "" and p_value not in p_values:
                    p_values.append(p_value)
        score = first_score(result)
        for output_id in output_ids or [""]:
            node = nodes.get(output_id) if isinstance(nodes, dict) else None
            label = node.get("name", "") if isinstance(node, dict) else ""
            row = rows_by_id.setdefault(
                output_id,
                {
                    "rank": index,
                    "id": output_id,
                    "name": label,
                    "p_value": "",
                    "matched_input_count": 0,
                },
            )
            row["matched_input_count"] = max(row["matched_input_count"], matched_input_count)
            if not row["p_value"] and p_values:
                row["p_value"] = p_values[0]

    if rows_by_id:
        lines.append("")
        lines.append("id\tname\tp value\tnumber of matched inputs")
        ranked_rows = sorted(rows_by_id.values(), key=lambda row: row["rank"])
        for row in ranked_rows[:limit]:
            lines.append(
                "\t".join(
                    [
                        row["id"],
                        row["name"],
                        str(row["p_value"]),
                        str(row["matched_input_count"]),
                    ]
                )
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--member-id", dest="member_ids", action="append", default=[], help="Input member CURIE; repeatable.")
    parser.add_argument("--member-ids", dest="member_ids", action="append", default=[], help="Comma- or space-separated input member CURIEs.")
    parser.add_argument("--member-file", help="File with one member CURIE per line. # comments are allowed.")
    parser.add_argument("--input-category", required=True)
    parser.add_argument("--output-category", required=True)
    parser.add_argument("--predicate")
    parser.add_argument("--qualified-predicate", help="Optional value for biolink:qualified_predicate, such as biolink:causes.")
    parser.add_argument("--object-aspect-qualifier", help="Optional object aspect qualifier, such as activity, expression, or activity_or_abundance.")
    parser.add_argument("--object-direction-qualifier", help="Optional object direction qualifier, such as increased or decreased.")
    parser.add_argument(
        "--qualifier",
        action="append",
        help=(
            "Additional QEdge qualifier constraint as TYPE=VALUE. May be repeated. "
            "TYPE may be a Biolink CURIE or shorthand such as object_aspect_qualifier."
        ),
    )
    parser.add_argument("--input-role", choices=["subject", "object"], required=True)
    parser.add_argument("--set-id", default="uuid:1")
    parser.add_argument("--set-interpretation", default="MANY")
    parser.add_argument("--knowledge-type", choices=sorted(KNOWLEDGE_TYPES))
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--async-query", action="store_true")
    parser.add_argument("--poll", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--callback")
    parser.add_argument("--pvalue-threshold", type=float)
    parser.add_argument("--max-rules", type=int)
    parser.add_argument("--timeout", type=float, default=600.0, help="Async polling timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--http-timeout", type=float, default=60.0)
    parser.add_argument("--output", help="Write JSON payload/response to this path instead of stdout.")
    parser.add_argument("--limit", type=int, default=20, help="Printed result summary limit.")
    parser.add_argument("--no-summary", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    members = parse_member_args(args.member_ids, args.member_file)
    query = build_query(args, members)

    if args.build_only:
        write_payload(query, args.output)
        return

    if args.async_query:
        response = submit_async(args, query)
    else:
        response = submit_sync(args, query)
    write_payload(response, args.output)
    if args.output and not args.no_summary:
        print(summarize_response(response, args.limit), file=sys.stderr)


if __name__ == "__main__":
    main()
