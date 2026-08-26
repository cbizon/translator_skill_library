#!/usr/bin/env python3
"""Run a one-hop Biomedical Data Translator query through ARS."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ENVIRONMENTS = {
    "dev": {
        "ars_base": "https://ars.dev.transltr.io",
        "ui_base": "https://transltr-bma-ui-dev.ncats.io",
    },
    "ci": {
        "ars_base": "https://ars.ci.transltr.io",
        "ui_base": "https://ui.ci.transltr.io",
    },
    "test": {
        "ars_base": "https://ars.test.transltr.io",
        "ui_base": "https://ui.test.transltr.io",
    },
    "prod": {
        "ars_base": "https://ars.transltr.io",
        "ui_base": "https://ui.transltr.io",
    },
}

NAME_RESOLVER_BASE = "https://name-resolution-sri.renci.org"

RETRIEVER_BASES = {
    "dev": "https://dev.retriever.biothings.io",
    "ci": "https://retriever.ci.transltr.io",
    "test": "https://retriever.ci.transltr.io",
    "prod": "https://retriever.ci.transltr.io",
}

PREDICATE_ALIASES = {
    "associated with": "biolink:associated_with",
    "associated_with": "biolink:associated_with",
    "association": "biolink:associated_with",
    "affects": "biolink:affects",
    "caused by": "biolink:causes",
    "causes": "biolink:causes",
    "cause": "biolink:causes",
    "causing": "biolink:causes",
    "contributes to": "biolink:contributes_to",
    "contributes_to": "biolink:contributes_to",
    "contribution": "biolink:contributes_to",
    "has phenotype": "biolink:has_phenotype",
    "has_phenotype": "biolink:has_phenotype",
    "phenotype": "biolink:has_phenotype",
    "regulates": "biolink:regulates",
    "regulate": "biolink:regulates",
    "related to": "biolink:related_to",
    "related_to": "biolink:related_to",
    "treats": "biolink:treats",
    "treat": "biolink:treats",
    "treated by": "biolink:treats",
}

CHEMICAL_GENE_DIRECTIONAL_ALIASES = {
    "up": ("activity_or_abundance", "increased"),
    "upregulate": ("activity_or_abundance", "increased"),
    "upregulates": ("activity_or_abundance", "increased"),
    "upregulated": ("activity_or_abundance", "increased"),
    "up regulate": ("activity_or_abundance", "increased"),
    "up regulates": ("activity_or_abundance", "increased"),
    "up regulated": ("activity_or_abundance", "increased"),
    "increase expression": ("expression", "increased"),
    "increases expression": ("expression", "increased"),
    "increased expression": ("expression", "increased"),
    "increases expression of": ("expression", "increased"),
    "increase activity": ("activity", "increased"),
    "increases activity": ("activity", "increased"),
    "increased activity": ("activity", "increased"),
    "increases activity of": ("activity", "increased"),
    "increase abundance": ("abundance", "increased"),
    "increases abundance": ("abundance", "increased"),
    "increased abundance": ("abundance", "increased"),
    "increases abundance of": ("abundance", "increased"),
    "down": ("activity_or_abundance", "decreased"),
    "downregulate": ("activity_or_abundance", "decreased"),
    "downregulates": ("activity_or_abundance", "decreased"),
    "downregulated": ("activity_or_abundance", "decreased"),
    "down regulate": ("activity_or_abundance", "decreased"),
    "down regulates": ("activity_or_abundance", "decreased"),
    "down regulated": ("activity_or_abundance", "decreased"),
    "decrease expression": ("expression", "decreased"),
    "decreases expression": ("expression", "decreased"),
    "decreased expression": ("expression", "decreased"),
    "decreases expression of": ("expression", "decreased"),
    "decrease activity": ("activity", "decreased"),
    "decreases activity": ("activity", "decreased"),
    "decreased activity": ("activity", "decreased"),
    "decreases activity of": ("activity", "decreased"),
    "decrease abundance": ("abundance", "decreased"),
    "decreases abundance": ("abundance", "decreased"),
    "decreased abundance": ("abundance", "decreased"),
    "decreases abundance of": ("abundance", "decreased"),
}

CHEMICAL_CATEGORIES = {
    "biolink:ChemicalEntity",
    "biolink:Drug",
}

GENE_CATEGORIES = {
    "biolink:Gene",
    "biolink:GeneOrGeneProduct",
}

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
}

DIRECTION_QUALIFIER_ALIASES = {
    "up": "increased",
    "upregulate": "increased",
    "upregulates": "increased",
    "upregulated": "increased",
    "up regulate": "increased",
    "up regulates": "increased",
    "up regulated": "increased",
    "increase": "increased",
    "increases": "increased",
    "increased": "increased",
    "down": "decreased",
    "downregulate": "decreased",
    "downregulates": "decreased",
    "downregulated": "decreased",
    "down regulate": "decreased",
    "down regulates": "decreased",
    "down regulated": "decreased",
    "decrease": "decreased",
    "decreases": "decreased",
    "decreased": "decreased",
}

PENDING_STATUSES = {
    "accepted",
    "created",
    "queued",
    "running",
    "submitted",
    "processing",
    "in progress",
}

DEFAULT_RETRIEVER_TIER = 0


class QueryError(RuntimeError):
    """Raised for failures that should be visible to the caller."""


def prefixed_biolink(value: str, *, kind: str) -> str:
    if not value:
        raise QueryError(f"Empty {kind}")
    if value.startswith("biolink:"):
        return value
    if ":" in value:
        raise QueryError(f"{kind} must be a Biolink CURIE, got {value!r}")
    return f"biolink:{value}"


def normalize_predicate(raw: str | None) -> str | None:
    if raw is None or raw.strip() == "":
        return None
    value = raw.strip()
    if value.startswith("biolink:"):
        return value
    normalized = value.lower().replace("-", " ").replace("_", " ")
    if normalized in PREDICATE_ALIASES:
        return PREDICATE_ALIASES[normalized]
    if ":" in value:
        raise QueryError(f"Predicate must be a Biolink predicate, got {value!r}")
    return f"biolink:{value.replace(' ', '_')}"


def normalized_phrase(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").replace("_", " ").split())


def qedge_category_pair(
    input_category: str | None,
    output_category: str,
    input_role: str,
) -> tuple[str | None, str | None]:
    if input_role == "subject":
        return input_category, output_category
    if input_role == "object":
        return output_category, input_category
    raise QueryError("--input-role must be subject or object")


def is_chemical_to_gene_query(subject_category: str | None, object_category: str | None) -> bool:
    return subject_category in CHEMICAL_CATEGORIES and object_category in GENE_CATEGORIES


def normalize_predicate_for_query(
    raw: str | None,
    *,
    subject_category: str | None,
    object_category: str | None,
) -> str | None:
    if raw and is_chemical_to_gene_query(subject_category, object_category):
        if normalized_phrase(raw) in CHEMICAL_GENE_DIRECTIONAL_ALIASES:
            return "biolink:affects"
    return normalize_predicate(raw)


def normalize_qualifier_type(raw: str) -> str:
    if not raw:
        raise QueryError("Empty qualifier type")
    if raw.startswith("biolink:"):
        return raw
    normalized = normalized_phrase(raw)
    normalized = normalized.replace(" ", "_")
    if normalized in QUALIFIER_TYPE_ALIASES:
        return QUALIFIER_TYPE_ALIASES[normalized]
    if ":" in raw:
        raise QueryError(f"Qualifier type must be a Biolink CURIE, got {raw!r}")
    return f"biolink:{normalized}"


def normalize_aspect_qualifier(raw: str) -> str:
    normalized = normalized_phrase(raw)
    return ASPECT_QUALIFIER_ALIASES.get(normalized, normalized.replace(" ", "_"))


def normalize_direction_qualifier(raw: str) -> str:
    normalized = normalized_phrase(raw)
    return DIRECTION_QUALIFIER_ALIASES.get(normalized, normalized.replace(" ", "_"))


def parse_qualifier(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise QueryError(f"Qualifier must be TYPE=VALUE, got {raw!r}")
    qualifier_type, qualifier_value = raw.split("=", 1)
    qualifier_type = normalize_qualifier_type(qualifier_type.strip())
    qualifier_value = qualifier_value.strip()
    if not qualifier_value:
        raise QueryError(f"Qualifier {raw!r} has an empty value")
    if qualifier_type.endswith("_direction_qualifier"):
        qualifier_value = normalize_direction_qualifier(qualifier_value)
    elif qualifier_type.endswith("_aspect_qualifier"):
        qualifier_value = normalize_aspect_qualifier(qualifier_value)
    elif qualifier_type == "biolink:qualified_predicate":
        normalized = normalize_predicate(qualifier_value)
        if normalized is None:
            raise QueryError(f"Empty qualified predicate in qualifier {raw!r}")
        qualifier_value = normalized
    return qualifier_type, qualifier_value


def build_qualifier_constraints(
    args: argparse.Namespace,
    *,
    subject_category: str | None,
    object_category: str | None,
) -> dict[str, str] | None:
    qualifiers: dict[str, str] = {}
    if args.predicate and is_chemical_to_gene_query(subject_category, object_category):
        chemical_gene_match = CHEMICAL_GENE_DIRECTIONAL_ALIASES.get(normalized_phrase(args.predicate))
        if chemical_gene_match:
            aspect, direction = chemical_gene_match
            qualifiers["biolink:object_aspect_qualifier"] = aspect
            qualifiers["biolink:object_direction_qualifier"] = direction

    if args.qualified_predicate:
        qualified_predicate = normalize_predicate(args.qualified_predicate)
        if qualified_predicate is None:
            raise QueryError("Empty --qualified-predicate")
        qualifiers["biolink:qualified_predicate"] = qualified_predicate
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
    return qualifiers or None


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> Any:
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "translator-one-hop-questions/0.1",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise QueryError(f"HTTP {exc.code} for {url}: {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise QueryError(f"Request failed for {url}: {exc}") from exc
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise QueryError(f"Non-JSON response from {url}: {body[:1000]}") from exc


def lookup_name(
    name: str,
    *,
    category: str | None,
    limit: int,
    timeout: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "string": name,
        "autocomplete": "false",
        "limit": str(limit),
    }
    if category:
        params["biolink_type"] = prefixed_biolink(category, kind="input category")
    url = f"{NAME_RESOLVER_BASE}/lookup?{urllib.parse.urlencode(params)}"
    results = request_json(url, timeout=timeout)
    if not isinstance(results, list):
        raise QueryError("Name Resolver response was not a list")
    return results


def resolve_input(args: argparse.Namespace) -> dict[str, Any]:
    input_category = (
        prefixed_biolink(args.input_category, kind="input category")
        if args.input_category
        else None
    )
    if args.input_curie:
        return {
            "curie": args.input_curie,
            "label": args.entity or args.input_curie,
            "types": [input_category] if input_category else [],
            "source": "explicit",
        }
    if not args.entity:
        raise QueryError("Provide --entity or --input-curie")
    if ":" in args.entity and " " not in args.entity and not args.force_name_resolution:
        return {
            "curie": args.entity,
            "label": args.entity,
            "types": [input_category] if input_category else [],
            "source": "curie",
        }
    candidates = lookup_name(
        args.entity,
        category=input_category,
        limit=args.resolver_limit,
        timeout=args.http_timeout,
    )
    if not candidates:
        raise QueryError(f"Name Resolver returned no candidates for {args.entity!r}")
    if args.allow_first_resolver_match or len(candidates) == 1:
        selected = candidates[0]
        return {
            "curie": selected["curie"],
            "label": selected.get("label") or selected["curie"],
            "types": selected.get("types", []),
            "score": selected.get("score"),
            "source": "name_resolver",
            "candidates": candidates,
        }
    raise QueryError(
        "Name Resolver returned multiple candidates. Select one and rerun with "
        "--input-curie. Candidates:\n"
        + json.dumps(candidates, indent=2, sort_keys=True)
    )


def build_query(
    *,
    input_curie: str,
    input_category: str | None,
    output_category: str,
    predicate: str | None,
    qualifier_constraints: dict[str, str] | None,
    input_role: str,
    retriever_tier: int,
) -> dict[str, Any]:
    input_node: dict[str, Any] = {"ids": [input_curie]}
    if input_category:
        input_node["categories"] = [input_category]
    output_node: dict[str, Any] = {"categories": [output_category]}

    nodes = {
        "input": input_node,
        "output": output_node,
    }
    if input_role == "subject":
        subject = "input"
        object_ = "output"
    elif input_role == "object":
        subject = "output"
        object_ = "input"
    else:
        raise QueryError("--input-role must be subject or object")

    edge: dict[str, Any] = {"subject": subject, "object": object_}
    if predicate:
        edge["predicates"] = [predicate]
    if qualifier_constraints:
        edge["constraints"] = {"qualifiers": [qualifier_constraints]}

    return {
        "message": {
            "query_graph": {
                "nodes": nodes,
                "edges": {
                    "e0": edge,
                },
            },
        },
        "parameters": {
            "tier": retriever_tier,
        },
    }


def validate_query(query: dict[str, Any]) -> None:
    try:
        qgraph = query["message"]["query_graph"]
        nodes = qgraph["nodes"]
        edge = qgraph["edges"]["e0"]
    except KeyError as exc:
        raise QueryError(f"TRAPI query is missing required key {exc}") from exc

    for node_id in (edge.get("subject"), edge.get("object")):
        if node_id not in nodes:
            raise QueryError(f"Query edge references missing node {node_id!r}")

    for node_id, node in nodes.items():
        categories = node.get("categories", [])
        if categories and not isinstance(categories, list):
            raise QueryError(f"Node {node_id} categories must be a list")
        for category in categories:
            if not str(category).startswith("biolink:"):
                raise QueryError(f"Node {node_id} category is not Biolink-prefixed: {category}")

    predicates = edge.get("predicates", [])
    if predicates and not isinstance(predicates, list):
        raise QueryError("Edge predicates must be a list")
    for predicate in predicates:
        if not str(predicate).startswith("biolink:"):
            raise QueryError(f"Predicate is not Biolink-prefixed: {predicate}")
    constraints = edge.get("constraints")
    if constraints:
        if not predicates or len(predicates) != 1:
            raise QueryError("Qualifier constraints require exactly one query predicate")
        if not isinstance(constraints, dict):
            raise QueryError("Edge constraints must be an object")
        qualifiers = constraints.get("qualifiers")
        if not isinstance(qualifiers, list) or not qualifiers:
            raise QueryError("Edge constraints.qualifiers must be a non-empty list")
        for qualifier_set in qualifiers:
            if not isinstance(qualifier_set, dict) or not qualifier_set:
                raise QueryError("Each qualifier constraint set must be a non-empty object")
            for qualifier_type, qualifier_value in qualifier_set.items():
                if not str(qualifier_type).startswith("biolink:"):
                    raise QueryError(
                        f"Qualifier type is not Biolink-prefixed: {qualifier_type}"
                    )
                if not isinstance(qualifier_value, str) or not qualifier_value:
                    raise QueryError(
                        f"Qualifier {qualifier_type} must have a non-empty string value"
                    )


def retriever_base(env: str) -> str:
    try:
        return RETRIEVER_BASES[env].rstrip("/")
    except KeyError as exc:
        raise QueryError(f"No Retriever base configured for environment {env!r}") from exc


def fetch_retriever_metadata(env: str, timeout: int) -> dict[str, Any]:
    payload = request_json(f"{retriever_base(env)}/meta_knowledge_graph", timeout=timeout)
    if not isinstance(payload, dict):
        raise QueryError("Retriever meta_knowledge_graph response was not an object")
    edges = payload.get("edges")
    if not isinstance(edges, list):
        raise QueryError("Retriever meta_knowledge_graph response has no edge list")
    return payload


def qedge_categories(query: dict[str, Any]) -> tuple[str, str, str | None]:
    qgraph = query["message"]["query_graph"]
    nodes = qgraph["nodes"]
    edge = qgraph["edges"]["e0"]
    subject_node = nodes[edge["subject"]]
    object_node = nodes[edge["object"]]
    subject_categories = subject_node.get("categories") or []
    object_categories = object_node.get("categories") or []
    if not subject_categories or not object_categories:
        raise QueryError("Retriever metadata validation requires subject and object categories")
    predicate = None
    predicates = edge.get("predicates") or []
    if predicates:
        predicate = predicates[0]
    return subject_categories[0], object_categories[0], predicate


def retriever_predicate_options(
    metadata: dict[str, Any],
    *,
    subject_category: str,
    object_category: str,
) -> list[str]:
    predicates = {
        edge["predicate"]
        for edge in metadata["edges"]
        if edge.get("subject") == subject_category and edge.get("object") == object_category
    }
    return sorted(predicates)


def qedge_qualifier_types(query: dict[str, Any]) -> set[str]:
    edge = query["message"]["query_graph"]["edges"]["e0"]
    constraints = edge.get("constraints") or {}
    qualifiers = constraints.get("qualifiers") or []
    qualifier_types: set[str] = set()
    for qualifier_set in qualifiers:
        if isinstance(qualifier_set, dict):
            qualifier_types.update(str(qualifier_type) for qualifier_type in qualifier_set)
    return qualifier_types


def retriever_qualifier_options(
    metadata: dict[str, Any],
    *,
    subject_category: str,
    object_category: str,
    predicate: str,
) -> list[str]:
    qualifier_types: set[str] = set()
    for edge in metadata["edges"]:
        if (
            edge.get("subject") == subject_category
            and edge.get("object") == object_category
            and edge.get("predicate") == predicate
        ):
            for qualifier in edge.get("qualifiers") or []:
                if isinstance(qualifier, dict) and qualifier.get("qualifier_type_id"):
                    qualifier_types.add(str(qualifier["qualifier_type_id"]))
    return sorted(qualifier_types)


def validate_retriever_metadata(
    *,
    env: str,
    query: dict[str, Any],
    timeout: int,
    require_predicate: bool,
) -> dict[str, Any]:
    subject_category, object_category, predicate = qedge_categories(query)
    metadata = fetch_retriever_metadata(env, timeout=timeout)
    predicate_options = retriever_predicate_options(
        metadata,
        subject_category=subject_category,
        object_category=object_category,
    )
    supported = predicate is None or predicate in predicate_options
    qualifier_types = qedge_qualifier_types(query)
    qualifier_options = (
        retriever_qualifier_options(
            metadata,
            subject_category=subject_category,
            object_category=object_category,
            predicate=predicate,
        )
        if predicate
        else []
    )
    unsupported_qualifier_types = sorted(qualifier_types - set(qualifier_options))
    result = {
        "retriever_base": retriever_base(env),
        "subject_category": subject_category,
        "object_category": object_category,
        "predicate": predicate,
        "supported": supported,
        "supported_predicates": predicate_options,
        "qualifier_types": sorted(qualifier_types),
        "supported_qualifier_types": qualifier_options,
    }
    if require_predicate and predicate is None:
        raise QueryError("Retriever metadata validation requires a predicate")
    if predicate is not None and not supported:
        raise QueryError(
            "Retriever metadata does not support "
            f"{subject_category} --{predicate}--> {object_category}. "
            f"Supported predicates: {', '.join(predicate_options) or '(none)'}"
        )
    if qualifier_types and predicate is None:
        raise QueryError("Retriever metadata validation requires a predicate for qualifiers")
    if unsupported_qualifier_types:
        raise QueryError(
            "Retriever metadata does not support qualifier type(s) for "
            f"{subject_category} --{predicate}--> {object_category}: "
            f"{', '.join(unsupported_qualifier_types)}. "
            f"Supported qualifier types: {', '.join(qualifier_options) or '(none)'}"
        )
    return result


def submit_query(env: str, query: dict[str, Any], timeout: int) -> dict[str, Any]:
    url = f"{ENVIRONMENTS[env]['ars_base']}/ars/api/submit"
    submitted = request_json(url, method="POST", payload=query, timeout=timeout)
    if not isinstance(submitted, dict):
        raise QueryError("ARS submit response was not an object")
    if "pk" not in submitted:
        raise QueryError(f"ARS submit response did not contain pk: {submitted}")
    return submitted


def message_url(env: str, pk: str, *, trace: bool = False, format_json: bool = False) -> str:
    url = f"{ENVIRONMENTS[env]['ars_base']}/ars/api/messages/{urllib.parse.quote(pk)}"
    params = {}
    if trace:
        params["trace"] = "y"
    if format_json:
        params["format"] = "json"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def fetch_message(env: str, pk: str, *, timeout: int, trace: bool = False) -> dict[str, Any]:
    payload = request_json(message_url(env, pk, trace=trace), timeout=timeout)
    if not isinstance(payload, dict):
        raise QueryError(f"ARS message {pk} was not an object")
    return payload


def child_pk(child: dict[str, Any]) -> str | None:
    message = child.get("message")
    return message if isinstance(message, str) and message else None


def child_status(child: dict[str, Any]) -> str:
    status = child.get("status")
    return str(status).lower() if status is not None else ""


def is_terminal_parent(parent: dict[str, Any]) -> bool:
    children = parent.get("children")
    if not isinstance(children, list) or not children:
        status = str(parent.get("status", "")).lower()
        return status not in PENDING_STATUSES and bool(status)
    statuses = [child_status(child) for child in children if isinstance(child, dict)]
    return bool(statuses) and not any(status in PENDING_STATUSES for status in statuses)


def poll_parent(env: str, pk: str, *, args: argparse.Namespace) -> dict[str, Any]:
    deadline = time.time() + args.poll_timeout
    latest: dict[str, Any] | None = None
    while time.time() <= deadline:
        latest = fetch_message(env, pk, timeout=args.http_timeout, trace=True)
        if is_terminal_parent(latest):
            return latest
        time.sleep(args.poll_interval)
    if latest is None:
        raise QueryError(f"Timed out before fetching parent message {pk}")
    latest["_poll_timeout"] = True
    return latest


def trapi_message_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = payload.get("message")
    if isinstance(message, dict) and (
        "results" in message or "query_graph" in message or "knowledge_graph" in message
    ):
        return message
    if "fields" in payload and isinstance(payload["fields"], dict):
        data = payload["fields"].get("data")
        if isinstance(data, dict):
            nested = data.get("message")
            if isinstance(nested, dict):
                return nested
    return None


def output_bindings(trapi_message: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    results = trapi_message.get("results", [])
    kg_nodes = trapi_message.get("knowledge_graph", {}).get("nodes", {})
    bindings: list[dict[str, Any]] = []
    if not isinstance(results, list):
        return bindings
    for result in results[:limit]:
        if not isinstance(result, dict):
            continue
        node_bindings = result.get("node_bindings", {})
        output_binding = node_bindings.get("output", [])
        if not output_binding:
            continue
        first_binding = output_binding[0]
        if not isinstance(first_binding, dict):
            continue
        output_id = first_binding.get("id")
        node = kg_nodes.get(output_id, {}) if isinstance(kg_nodes, dict) else {}
        analyses = result.get("analyses", [])
        score = None
        if analyses and isinstance(analyses[0], dict):
            score = analyses[0].get("score")
        bindings.append(
            {
                "id": output_id,
                "name": node.get("name") if isinstance(node, dict) else None,
                "categories": node.get("categories") if isinstance(node, dict) else None,
                "score": score,
            }
        )
    return bindings


def fetch_child_summaries(env: str, parent: dict[str, Any], *, args: argparse.Namespace) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    children = parent.get("children", [])
    if not isinstance(children, list):
        return summaries
    for child in children:
        if not isinstance(child, dict):
            continue
        actor = child.get("actor", {})
        actor_agent = actor.get("agent") if isinstance(actor, dict) else None
        if not (isinstance(actor_agent, str) and actor_agent.startswith("ara")):
            continue
        pk = child_pk(child)
        summary: dict[str, Any] = {
            "actor_agent": actor_agent,
            "child_pk": pk,
            "ars_status": child.get("status"),
            "ars_code": child.get("code"),
        }
        if pk:
            try:
                payload = request_json(
                    message_url(env, pk, format_json=True),
                    timeout=args.http_timeout,
                )
                if isinstance(payload, dict):
                    trapi_message = trapi_message_from_payload(payload)
                    if trapi_message is not None:
                        results = trapi_message.get("results", [])
                        summary["result_count"] = len(results) if isinstance(results, list) else None
                        summary["top_bindings"] = output_bindings(
                            trapi_message,
                            limit=args.binding_limit,
                        )
                    else:
                        summary["payload_warning"] = "No TRAPI message found in child payload"
                else:
                    summary["payload_warning"] = "Child payload was not an object"
            except QueryError as exc:
                summary["fetch_error"] = str(exc)
        summaries.append(summary)
    return summaries


def write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=sorted(ENVIRONMENTS), default="ci")
    parser.add_argument("--entity", help="Input entity name or CURIE.")
    parser.add_argument("--input-curie", help="Selected input CURIE. Skips name lookup.")
    parser.add_argument("--input-category", help="Input Biolink category.")
    parser.add_argument("--output-category", required=True, help="Output Biolink category.")
    parser.add_argument("--predicate", help="Optional Biolink predicate or short phrase.")
    parser.add_argument(
        "--qualified-predicate",
        help="Optional qualifier value for biolink:qualified_predicate, such as causes.",
    )
    parser.add_argument(
        "--object-aspect-qualifier",
        help="Optional object aspect qualifier, such as expression, activity, or activity_or_abundance.",
    )
    parser.add_argument(
        "--object-direction-qualifier",
        help="Optional object direction qualifier, such as increased or decreased.",
    )
    parser.add_argument(
        "--qualifier",
        action="append",
        help=(
            "Additional QEdge qualifier constraint as TYPE=VALUE. May be repeated. "
            "TYPE may be a Biolink CURIE or shorthand such as object_aspect_qualifier."
        ),
    )
    parser.add_argument(
        "--input-role",
        choices=["subject", "object"],
        default="subject",
        help="Role of the input entity in the canonical Biolink predicate direction.",
    )
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument("--resolve-only", action="store_true", help="Resolve names but do not build or submit.")
    parser.add_argument("--build-only", action="store_true", help="Build query but do not submit.")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Resolve, build, and validate against Retriever metadata without ARS submission.",
    )
    parser.add_argument(
        "--skip-retriever-metadata-validation",
        action="store_true",
        help="Do not check Retriever meta_knowledge_graph before ARS submission.",
    )
    parser.add_argument(
        "--allow-first-resolver-match",
        action="store_true",
        help="Use the first Name Resolver candidate instead of requiring disambiguation.",
    )
    parser.add_argument(
        "--force-name-resolution",
        action="store_true",
        help="Run Name Resolver even if --entity looks like a CURIE.",
    )
    parser.add_argument("--resolver-limit", type=int, default=5)
    parser.add_argument("--binding-limit", type=int, default=10)
    parser.add_argument("--poll-timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--http-timeout", type=int, default=90)
    parser.add_argument(
        "--retriever-tier",
        type=int,
        choices=[0, 1],
        default=DEFAULT_RETRIEVER_TIER,
        help="Retriever tier parameter to include in the TRAPI query. Defaults to tier 0.",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_category = (
        prefixed_biolink(args.input_category, kind="input category")
        if args.input_category
        else None
    )
    output_category = prefixed_biolink(args.output_category, kind="output category")
    subject_category, object_category = qedge_category_pair(
        input_category,
        output_category,
        args.input_role,
    )
    predicate = normalize_predicate_for_query(
        args.predicate,
        subject_category=subject_category,
        object_category=object_category,
    )
    qualifier_constraints = build_qualifier_constraints(
        args,
        subject_category=subject_category,
        object_category=object_category,
    )
    resolved = resolve_input(args)
    result: dict[str, Any] = {
        "environment": args.env,
        "resolved_input": resolved,
        "input_role": args.input_role,
        "input_category": input_category,
        "output_category": output_category,
        "predicate": predicate,
        "qualifier_constraints": qualifier_constraints,
        "retriever_tier": args.retriever_tier,
    }
    if args.resolve_only:
        return result

    query = build_query(
        input_curie=resolved["curie"],
        input_category=input_category,
        output_category=output_category,
        predicate=predicate,
        qualifier_constraints=qualifier_constraints,
        input_role=args.input_role,
        retriever_tier=args.retriever_tier,
    )
    validate_query(query)
    result["query"] = query
    if not args.skip_retriever_metadata_validation:
        result["retriever_metadata_validation"] = validate_retriever_metadata(
            env=args.env,
            query=query,
            timeout=args.http_timeout,
            require_predicate=False,
        )
    if args.metadata_only:
        return result
    if args.build_only:
        return result

    submitted = submit_query(args.env, query, timeout=args.http_timeout)
    pk = submitted["pk"]
    parent = poll_parent(args.env, pk, args=args)
    child_summaries = fetch_child_summaries(args.env, parent, args=args)
    result.update(
        {
            "ars_parent_pk": pk,
            "ars_submit_response": submitted,
            "ars_parent_message": parent,
            "ui_url": f"{ENVIRONMENTS[args.env]['ui_base']}/results?l=Lookup&q={pk}",
            "child_summaries": child_summaries,
        }
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        result = run(args)
        write_output(Path(args.output), result)
    except QueryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: result[k] for k in result if k != "ars_parent_message"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
