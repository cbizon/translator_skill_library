#!/usr/bin/env python3
"""Collect a Feedback issue, related issues, and linked Translator ARS responses."""

from __future__ import annotations

import argparse
import ast
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPOSITORY = "NCATSTranslator/Feedback"
ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/NCATSTranslator/Feedback/issues/(\d+)"
    r"(?:[/?#].*)?$",
    re.IGNORECASE,
)
ISSUE_REFERENCE_RE = re.compile(r"(?<![\w/])#(\d+)\b")
FULL_ISSUE_REFERENCE_RE = re.compile(
    r"https?://github\.com/NCATSTranslator/Feedback/issues/(\d+)",
    re.IGNORECASE,
)
TRANSLATOR_URL_RE = re.compile(
    r"https://(?:"
    r"transltr-bma-ui-dev\.ncats\.io|"
    r"ui\.ci\.transltr\.io|"
    r"ui\.test\.transltr\.io|"
    r"ui\.transltr\.io"
    r")[^\s<>\"']+",
    re.IGNORECASE,
)
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
ENVIRONMENTS = {
    "dev": {
        "ui_hosts": {"transltr-bma-ui-dev.ncats.io"},
        "ars_base": "https://ars.dev.transltr.io",
    },
    "ci": {
        "ui_hosts": {"ui.ci.transltr.io"},
        "ars_base": "https://ars.ci.transltr.io",
    },
    "test": {
        "ui_hosts": {"ui.test.transltr.io"},
        "ars_base": "https://ars.test.transltr.io",
    },
    "prod": {
        "ui_hosts": {"ui.transltr.io"},
        "ars_base": "https://ars.transltr.io",
    },
}


def parse_issue(value: str) -> int:
    if value.isdigit():
        number = int(value)
    else:
        match = ISSUE_URL_RE.match(value)
        if not match:
            raise ValueError(
                "Issue input must be a number or an "
                "NCATSTranslator/Feedback issue URL"
            )
        number = int(match.group(1))
    if number < 1:
        raise ValueError("Issue number must be positive")
    return number


def run_gh_api(endpoint: str, *, paginate: bool = False) -> Any:
    command = ["gh", "api"]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    command.append(endpoint)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("The GitHub CLI 'gh' is not installed") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"gh api failed for {endpoint}: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh api returned invalid JSON for {endpoint}") from exc


def compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "body": issue.get("body") or "",
        "state": issue.get("state"),
        "state_reason": issue.get("state_reason"),
        "html_url": issue.get("html_url"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "closed_at": issue.get("closed_at"),
        "author": (issue.get("user") or {}).get("login"),
        "labels": [
            label.get("name")
            for label in issue.get("labels") or []
            if isinstance(label, dict)
        ],
        "assignees": [
            assignee.get("login")
            for assignee in issue.get("assignees") or []
            if isinstance(assignee, dict)
        ],
    }


def compact_comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "author": (comment.get("user") or {}).get("login"),
        "author_association": comment.get("author_association"),
        "body": comment.get("body") or "",
        "html_url": comment.get("html_url"),
        "created_at": comment.get("created_at"),
        "updated_at": comment.get("updated_at"),
    }


def compact_backlink(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event") != "cross-referenced":
        return None
    source = event.get("source") or {}
    if source.get("type") != "issue":
        return None
    issue = source.get("issue") or {}
    repository = (issue.get("repository") or {}).get("full_name")
    if not repository:
        repository_url = issue.get("repository_url") or ""
        marker = "api.github.com/repos/"
        if marker in repository_url:
            repository = repository_url.split(marker, 1)[1]
    number = issue.get("number")
    if not isinstance(number, int) or not repository:
        return None
    return {
        "repository": repository,
        "number": number,
        "title": issue.get("title"),
        "html_url": issue.get("html_url"),
        "state": issue.get("state"),
        "created_at": event.get("created_at"),
        "actor": (event.get("actor") or {}).get("login"),
    }


def fetch_issue_backlinks(number: int) -> list[dict[str, Any]]:
    pages = run_gh_api(
        f"repos/{REPOSITORY}/issues/{number}/timeline?per_page=100",
        paginate=True,
    )
    if not isinstance(pages, list):
        raise TypeError(f"Timeline response for issue {number} is not a list")
    backlinks = []
    seen: set[tuple[str, int]] = set()
    for page in pages:
        if not isinstance(page, list):
            raise TypeError(f"Timeline page for issue {number} is not a list")
        for event in page:
            backlink = compact_backlink(event)
            if backlink is None:
                continue
            key = (backlink["repository"], backlink["number"])
            if key in seen:
                continue
            seen.add(key)
            backlinks.append(backlink)
    return sorted(
        backlinks,
        key=lambda item: (item["repository"], item["number"]),
    )


def fetch_issue_bundle(
    number: int,
    *,
    include_backlinks: bool = False,
) -> dict[str, Any]:
    issue = run_gh_api(f"repos/{REPOSITORY}/issues/{number}")
    pages = run_gh_api(
        f"repos/{REPOSITORY}/issues/{number}/comments?per_page=100",
        paginate=True,
    )
    if not isinstance(pages, list):
        raise TypeError(f"Comments response for issue {number} is not a list")
    comments = []
    for page in pages:
        if not isinstance(page, list):
            raise TypeError(f"Comments page for issue {number} is not a list")
        comments.extend(compact_comment(comment) for comment in page)
    return {
        "issue": compact_issue(issue),
        "comments": comments,
        "backlinks": fetch_issue_backlinks(number) if include_backlinks else [],
    }


def labeled_texts(bundle: dict[str, Any]) -> list[tuple[str, str]]:
    issue = bundle["issue"]
    number = issue["number"]
    texts = [(f"issue #{number} body", issue.get("body") or "")]
    texts.extend(
        (
            f"issue #{number} comment by {comment.get('author') or 'unknown'}",
            comment.get("body") or "",
        )
        for comment in bundle["comments"]
    )
    return texts


def extract_referenced_issue_numbers(
    bundle: dict[str, Any],
    *,
    exclude: int,
) -> list[int]:
    numbers: set[int] = set()
    for _, text in labeled_texts(bundle):
        numbers.update(int(value) for value in ISSUE_REFERENCE_RE.findall(text))
        numbers.update(int(value) for value in FULL_ISSUE_REFERENCE_RE.findall(text))
    numbers.discard(exclude)
    return sorted(numbers)


def environment_from_host(host: str) -> str:
    normalized = host.lower().split(":", 1)[0]
    for environment, config in ENVIRONMENTS.items():
        if normalized in config["ui_hosts"]:
            return environment
    raise ValueError(f"Unrecognized Translator UI host: {host}")


def clean_translator_url(value: str) -> str:
    return html.unescape(value).rstrip(".,;:!?)]}")


def extract_translator_queries(
    bundles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    queries: dict[tuple[str, str], dict[str, Any]] = {}
    for bundle in bundles:
        for source, text in labeled_texts(bundle):
            for raw_url in TRANSLATOR_URL_RE.findall(text):
                url = clean_translator_url(raw_url)
                parsed = urllib.parse.urlparse(url)
                environment = environment_from_host(parsed.netloc)
                pk_values = urllib.parse.parse_qs(parsed.query).get("q") or []
                if not pk_values or not UUID_RE.match(pk_values[0]):
                    continue
                parent_pk = pk_values[0]
                key = (environment, parent_pk)
                record = queries.setdefault(
                    key,
                    {
                        "environment": environment,
                        "parent_pk": parent_pk,
                        "urls": [],
                        "sources": [],
                    },
                )
                if url not in record["urls"]:
                    record["urls"].append(url)
                if source not in record["sources"]:
                    record["sources"].append(source)
    return sorted(
        queries.values(),
        key=lambda item: (item["environment"], item["parent_pk"]),
    )


def message_url(
    environment: str,
    pk: str,
    *,
    trace: bool = False,
    format_json: bool = False,
) -> str:
    base = ENVIRONMENTS[environment]["ars_base"]
    url = f"{base}/ars/api/messages/{urllib.parse.quote(pk)}"
    params = {}
    if trace:
        params["trace"] = "y"
    if format_json:
        params["format"] = "json"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def fetch_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "translator-issue-triage/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Response from {url} was not JSON: {exc}") from exc


def actor_agent(child: dict[str, Any]) -> str:
    actor = child.get("actor") or {}
    if not isinstance(actor, dict):
        return ""
    value = actor.get("agent")
    return value if isinstance(value, str) else ""


def child_role(agent: str) -> str | None:
    normalized = agent.lower()
    if normalized.startswith("ara"):
        return "ara"
    if normalized.startswith("ars"):
        return "merged"
    return None


def parse_merged_versions(value: Any) -> list[tuple[str, str]]:
    if value in (None, ""):
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError("ARS merged_versions_list is malformed") from exc
    if not isinstance(parsed, list):
        raise TypeError("ARS merged_versions_list is not a list")

    versions = []
    for item in parsed:
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise TypeError("ARS merged_versions_list contains an invalid entry")
        versions.append((item[0], item[1]))
    return versions


def collect_ars_query(query: dict[str, Any], timeout: float) -> dict[str, Any]:
    environment = query["environment"]
    parent_pk = query["parent_pk"]
    parent_url = message_url(environment, parent_pk, trace=True)
    parent = fetch_json(parent_url, timeout)
    children = parent.get("children")
    if not isinstance(children, list):
        raise TypeError(f"ARS parent {parent_pk} has no list-valued children")

    responses = []
    errors = []
    for child in children:
        if not isinstance(child, dict):
            continue
        agent = actor_agent(child)
        role = child_role(agent)
        if role is None:
            continue
        child_pk = child.get("message")
        if not isinstance(child_pk, str) or not child_pk:
            errors.append(
                {
                    "actor_agent": agent,
                    "role": role,
                    "error": "Child has no non-empty message PK",
                }
            )
            continue
        url = message_url(environment, child_pk, format_json=True)
        try:
            response = fetch_json(url, timeout)
        except Exception as exc:  # noqa: BLE001 - retain per-child failure details.
            errors.append(
                {
                    "actor_agent": agent,
                    "role": role,
                    "child_pk": child_pk,
                    "url": url,
                    "error": str(exc),
                }
            )
            continue
        responses.append(
            {
                "role": role,
                "actor_agent": agent,
                "child_pk": child_pk,
                "url": url,
                "ars_child": child,
                "response": response,
            }
        )

    try:
        merge_versions = parse_merged_versions(parent.get("merged_versions_list"))
    except Exception as exc:  # noqa: BLE001 - retain malformed metadata.
        merge_versions = []
        errors.append({"role": "merge_stage", "error": str(exc)})

    response_by_pk = {item["child_pk"]: item for item in responses}
    for stage_index, (stage_pk, merged_through_actor) in enumerate(
        merge_versions,
        start=1,
    ):
        existing = response_by_pk.get(stage_pk)
        if existing is not None:
            existing["merge_stage"] = stage_index
            existing["merged_through_actor"] = merged_through_actor
            continue
        url = message_url(environment, stage_pk, format_json=True)
        try:
            response = fetch_json(url, timeout)
        except Exception as exc:  # noqa: BLE001 - retain stage failure details.
            errors.append(
                {
                    "actor_agent": "ars-ars-agent",
                    "role": "merge_stage",
                    "child_pk": stage_pk,
                    "merge_stage": stage_index,
                    "merged_through_actor": merged_through_actor,
                    "url": url,
                    "error": str(exc),
                }
            )
            continue
        record = {
            "role": "merge_stage",
            "actor_agent": "ars-ars-agent",
            "child_pk": stage_pk,
            "merge_stage": stage_index,
            "merged_through_actor": merged_through_actor,
            "url": url,
            "ars_child": None,
            "response": response,
        }
        responses.append(record)
        response_by_pk[stage_pk] = record

    if not any(item["role"] == "merged" for item in responses):
        errors.append({"role": "merged", "error": "No merged ARS child was fetched"})
    if not any(item["role"] == "ara" for item in responses):
        errors.append({"role": "ara", "error": "No ARA child was fetched"})

    role_order = {"merge_stage": 0, "merged": 1, "ara": 2}
    responses.sort(
        key=lambda item: (
            role_order.get(item["role"], 99),
            item.get("merge_stage", 0),
            item.get("actor_agent", ""),
        )
    )

    return {
        **query,
        "parent_url": parent_url,
        "parent_metadata": parent,
        "responses": responses,
        "retrieval_errors": errors,
    }


def write_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect an NCATSTranslator/Feedback issue and linked ARS responses."
        )
    )
    parser.add_argument("issue", help="Feedback issue number or GitHub issue URL")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds. Default: 60.",
    )
    parser.add_argument(
        "--no-referenced-issues",
        action="store_true",
        help="Do not fetch directly referenced or backlinked Feedback issues.",
    )
    parser.add_argument(
        "--max-referenced-issues",
        type=int,
        default=5,
        help="Maximum referenced or backlinked issues to fetch. Default: 5.",
    )
    args = parser.parse_args()

    try:
        issue_number = parse_issue(args.issue)
        primary_bundle = fetch_issue_bundle(
            issue_number,
            include_backlinks=not args.no_referenced_issues,
        )
        referenced_bundles = []
        if not args.no_referenced_issues:
            text_references = extract_referenced_issue_numbers(
                primary_bundle,
                exclude=issue_number,
            )
            reference_kinds: dict[int, set[str]] = {
                number: {"text_reference"} for number in text_references
            }
            for backlink in primary_bundle["backlinks"]:
                if backlink["repository"] != REPOSITORY:
                    continue
                number = backlink["number"]
                if number == issue_number:
                    continue
                reference_kinds.setdefault(number, set()).add(
                    "timeline_backlink"
                )
            references = sorted(reference_kinds)
            if len(references) > args.max_referenced_issues:
                raise RuntimeError(
                    f"Issue references or is backlinked from "
                    f"{len(references)} Feedback issues; "
                    f"limit is {args.max_referenced_issues}"
                )
            for number in references:
                bundle = fetch_issue_bundle(number)
                bundle["reference_kinds"] = sorted(reference_kinds[number])
                referenced_bundles.append(bundle)

        bundles = [primary_bundle, *referenced_bundles]
        query_links = extract_translator_queries(bundles)
        ars_queries = []
        top_level_errors = []
        for query in query_links:
            try:
                ars_queries.append(collect_ars_query(query, args.timeout))
            except Exception as exc:  # noqa: BLE001 - retain per-query failures.
                top_level_errors.append(
                    {
                        "environment": query["environment"],
                        "parent_pk": query["parent_pk"],
                        "error": str(exc),
                    }
                )

        payload = {
            "repository": REPOSITORY,
            "input": args.issue,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "primary": primary_bundle,
            "referenced_issues": referenced_bundles,
            "translator_queries": ars_queries,
            "retrieval_errors": top_level_errors,
        }
        write_json(payload, args.output)

        child_error_count = sum(
            len(query["retrieval_errors"]) for query in ars_queries
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "issue": issue_number,
                    "backlinks": len(primary_bundle["backlinks"]),
                    "referenced_issues": len(referenced_bundles),
                    "translator_queries": len(ars_queries),
                    "responses": sum(
                        len(query["responses"]) for query in ars_queries
                    ),
                    "retrieval_errors": len(top_level_errors) + child_error_count,
                },
                sort_keys=True,
            )
        )
        return 2 if top_level_errors or child_error_count else 0
    except Exception as exc:  # noqa: BLE001 - command must fail visibly.
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
