"""Bounded, read-only GitHub context collection for scan reports.

This module intentionally has no dependency on ``server.py``. Callers pass an
OAuth or personal access token explicitly; credentials are never returned in
the result or included in errors.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


API_ROOT = "https://api.github.com"
USER_AGENT = "CodebaseDoctor-local"
MAX_ITEMS = 10
DEFAULT_TIMEOUT = 8


def _request_json(url: str, token: str, timeout: float) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(2_000_000).decode("utf-8"))


def _clean_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "GitHub rejected the credential (401). Reconnect GitHub and retry."
        if exc.code == 403:
            return "GitHub denied this request (403); check repository access or API rate limits."
        if exc.code == 404:
            return "GitHub could not find this repository or the credential cannot access it (404)."
        return f"GitHub API request failed (HTTP {exc.code})."
    if isinstance(exc, (TimeoutError, urllib.error.URLError)):
        return "GitHub API could not be reached before the request timed out."
    return "GitHub returned an invalid or unexpected response."


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    return {
        "number": item.get("number"),
        "title": item.get("title") or "(untitled)",
        "state": item.get("state"),
        "author": user.get("login"),
        "url": item.get("html_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "closed_at": item.get("closed_at"),
        "labels": [
            label.get("name") for label in item.get("labels", [])
            if isinstance(label, dict) and label.get("name")
        ],
        "draft": bool(item.get("draft", False)),
    }


def _get_section(
    path: str, token: str, timeout: float, errors: list[dict[str, str]], section: str
) -> Any:
    try:
        return _request_json(f"{API_ROOT}{path}", token, timeout)
    except Exception as exc:  # Each section is best-effort; preserve the rest of the report.
        errors.append({"section": section, "message": _clean_error(exc)})
        return None


def fetch_github_report(
    full_name: str, token: str = "", *, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fetch a compact repository profile plus recent PRs, issues and contributors.

    ``full_name`` must be ``owner/repository``. Up to six GitHub API requests
    are made (repository, languages, PRs, issues, contributors); PR history is
    fetched in separate open/closed requests, so the total is six. Every
    request has a timeout and item counts are capped at ten.

    Returns stable keys even when individual endpoints fail. ``errors`` holds
    section-level, credential-safe messages; no exception text or token is
    exposed. This is read-only and does not modify the repository.
    """
    full_name = (full_name or "").strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", full_name):
        raise ValueError("full_name must be a GitHub owner/repository name")
    timeout = max(1.0, min(float(timeout), 20.0))
    token = (token or "").strip()
    owner, repo = full_name.split("/", 1)
    base = f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}"
    errors: list[dict[str, str]] = []

    # All endpoints are independent. Run them together so a slow endpoint does
    # not add its timeout to every other section's latency.
    endpoints = {
        "repository": base,
        "languages": base + "/languages",
        "pull_requests_open": base + f"/pulls?state=open&sort=updated&direction=desc&per_page={MAX_ITEMS}",
        "pull_requests_closed": base + f"/pulls?state=closed&sort=updated&direction=desc&per_page={MAX_ITEMS}",
        "issues": base + f"/issues?state=all&sort=updated&direction=desc&per_page={MAX_ITEMS}",
        "contributors": base + f"/contributors?per_page={MAX_ITEMS}",
    }
    with ThreadPoolExecutor(max_workers=len(endpoints), thread_name_prefix="github-report") as pool:
        futures = {
            section: pool.submit(_get_section, path, token, timeout, errors, section)
            for section, path in endpoints.items()
        }
        results = {section: future.result() for section, future in futures.items()}
    metadata = results["repository"]
    languages = results["languages"]
    pulls_open = results["pull_requests_open"]
    pulls_closed = results["pull_requests_closed"]
    issues_raw = results["issues"]
    contributors_raw = results["contributors"]

    if not isinstance(metadata, dict):
        metadata = {}
    license_info = metadata.get("license") if isinstance(metadata.get("license"), dict) else None
    license_summary = None
    if license_info:
        license_summary = {
            "key": license_info.get("key"),
            "name": license_info.get("name"),
            "spdx_id": license_info.get("spdx_id"),
            "url": license_info.get("html_url"),
        }
    breakdown = languages if isinstance(languages, dict) else {}
    breakdown = {str(name): int(size) for name, size in breakdown.items() if isinstance(size, (int, float))}
    language_total = sum(breakdown.values())
    language_percentages = {
        name: round(size * 100 / language_total, 1) if language_total else 0.0
        for name, size in breakdown.items()
    }

    def pull_items(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        return [_summary(item) for item in raw[:MAX_ITEMS] if isinstance(item, dict)]

    issues: list[dict[str, Any]] = []
    if isinstance(issues_raw, list):
        for item in issues_raw:
            # The issues endpoint also returns pull requests. Exclude those.
            if isinstance(item, dict) and "pull_request" not in item:
                issues.append(_summary(item))
                if len(issues) >= MAX_ITEMS:
                    break

    contributors: list[dict[str, Any]] = []
    if isinstance(contributors_raw, list):
        for item in contributors_raw[:MAX_ITEMS]:
            if isinstance(item, dict):
                contributors.append({
                    "login": item.get("login"),
                    "contributions": item.get("contributions"),
                    "url": item.get("html_url"),
                })

    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "full_name": metadata.get("full_name") or full_name,
        "repository": {
            "description": metadata.get("description"),
            "url": metadata.get("html_url"),
            "visibility": metadata.get("visibility") or ("private" if metadata.get("private") else "public"),
            "private": metadata.get("private"),
            "archived": metadata.get("archived"),
            "stars": metadata.get("stargazers_count"),
            "forks": metadata.get("forks_count"),
            "open_issues_count": metadata.get("open_issues_count"),
            "default_branch": metadata.get("default_branch"),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "pushed_at": metadata.get("pushed_at"),
            "license": license_summary,
            "topics": metadata.get("topics", []) if isinstance(metadata.get("topics", []), list) else [],
        },
        "languages": {"bytes": breakdown, "percentages": language_percentages, "total_bytes": language_total},
        "pull_requests": {"open": pull_items(pulls_open), "closed": pull_items(pulls_closed)},
        "issues": issues,
        "contributors": contributors,
        "errors": errors,
    }
