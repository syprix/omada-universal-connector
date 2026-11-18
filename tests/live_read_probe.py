"""Bounded, read-only smoke probe for a temporary local connector container.

The probe talks only to the connector HTTP API; it never contacts Omada directly.
Output is deliberately limited to status, item counts, and stable error codes.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_RESPONSE_BYTES = 262_144
MAX_SITES = 3
MAX_DEVICES = 10
MAX_EXTENDED_APS = 3
MAX_TOTAL_REQUESTS = 64
MAX_PROBE_SECONDS = 60
TIMEOUT_SECONDS = 5
ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_HTTP_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _NoRedirect)


class _RequestBudget:
    def __init__(self) -> None:
        self.deadline = time.monotonic() + MAX_PROBE_SECONDS
        self.requests = 0

    def acquire(self) -> float | None:
        remaining = self.deadline - time.monotonic()
        if self.requests >= MAX_TOTAL_REQUESTS or remaining <= 0:
            return None
        self.requests += 1
        return min(TIMEOUT_SECONDS, remaining)


def _request(base: str, token: str, path: str,
             budget: _RequestBudget | None = None) -> tuple[int, dict[str, Any] | None, str | None]:
    timeout = TIMEOUT_SECONDS
    if budget is not None:
        allocated_timeout = budget.acquire()
        if allocated_timeout is None:
            return 0, None, "probe_limit_reached"
        timeout = allocated_timeout
    request = urllib.request.Request(
        base.rstrip("/") + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with _HTTP_OPENER.open(request, timeout=timeout) as response:
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read(MAX_RESPONSE_BYTES + 1)
        finally:
            exc.close()
    except (OSError, TimeoutError, urllib.error.URLError):
        return 0, None, "connector_unreachable"
    if len(body) > MAX_RESPONSE_BYTES:
        return status, None, "response_too_large"
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return status, None, "response_invalid"
    if not isinstance(payload, dict):
        return status, None, "response_invalid"
    if status < 200 or status >= 300:
        code = payload.get("error")
        return status, None, code if isinstance(code, str) and ERROR_CODE.fullmatch(code) else "http_error"
    if payload.get("status") != "ok":
        code = payload.get("error")
        return status, None, code if isinstance(code, str) and ERROR_CODE.fullmatch(code) else "response_invalid"
    return status, payload, None


def _report(label: str, status: int, count: int | None, error: str | None) -> None:
    # Keep output free of API payloads and all user/controller identifiers.
    if error:
        print(f"{label} status={status} error={error}")
    else:
        print(f"{label} status={status} count={count if count is not None else 0}")


def _items(payload: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    rows = payload.get("items") if payload else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return None
    return rows


def _ap_candidates(rows: list[dict[str, Any]], limit: int = MAX_EXTENDED_APS) -> list[str]:
    """Select only inventory rows explicitly classified as APs, without reporting refs."""
    refs: list[str] = []
    for row in rows[:MAX_DEVICES]:
        device_ref = row.get("device_ref")
        device_type = row.get("device_type")
        if (isinstance(device_ref, str) and re.fullmatch(r"[0-9a-f]{24}", device_ref)
                and isinstance(device_type, str)
                and device_type.strip().casefold() in {"ap", "access point", "accesspoint"}):
            refs.append(device_ref)
            if len(refs) >= limit:
                break
    return refs


def _safe_result_count(resource: str, payload: dict[str, Any] | None) -> int | None:
    """Summarize a response using counts only; never return payload values or refs."""
    if payload is None:
        return None
    if resource == "site_topology":
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        if (not isinstance(nodes, list) or not isinstance(edges, list)
                or any(not isinstance(item, dict) for item in nodes + edges)):
            return None
        return len(nodes)
    if resource == "ap_mesh_statistics":
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        omitted = data.get("omitted_field_count")
        if not isinstance(omitted, int) or isinstance(omitted, bool) or omitted < 0:
            return None
        counts = [data.get(key, 0) for key in ("child_aps_count", "candidate_parents_count")]
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
            return None
        return sum(value for value in counts if isinstance(value, int) and not isinstance(value, bool))
    if resource == "ap_health":
        data = payload.get("data")
        return len(data) if isinstance(data, dict) else None
    return None


def main() -> int:
    budget = _RequestBudget()
    token_file = os.environ.get("OMADA_CONNECTOR_TOKEN_FILE", "")
    base = os.environ.get("CONNECTOR_BASE_URL", "http://127.0.0.1:8080")
    try:
        parsed_base = urllib.parse.urlsplit(base)
        local_base = (
            parsed_base.scheme == "http" and parsed_base.hostname in {"127.0.0.1", "::1"}
            and parsed_base.port is not None and parsed_base.username is None
            and parsed_base.password is None and parsed_base.path in {"", "/"}
            and not parsed_base.query and not parsed_base.fragment
        )
    except ValueError:
        local_base = False
    if not local_base:
        _report("probe", 0, None, "connector_url_invalid")
        return 1
    if not token_file:
        _report("probe", 0, None, "token_file_unconfigured")
        return 1
    try:
        with open(token_file, "r", encoding="utf-8") as handle:
            token = handle.read(4097).strip()
    except OSError:
        _report("probe", 0, None, "token_file_unavailable")
        return 1
    if not token or len(token) > 4096 or any(not (0x21 <= ord(char) <= 0x7e) for char in token):
        _report("probe", 0, None, "token_file_invalid")
        return 1

    failed = False
    status, payload, error = _request(base, token, "/v1/sites", budget)
    sites = _items(payload)
    _report("sites", status, len(sites) if sites is not None else None,
            error or (None if sites is not None else "response_invalid"))
    if error or sites is None:
        return 1

    for site in sites[:MAX_SITES]:
        site_ref = site.get("site_ref")
        if not isinstance(site_ref, str) or not re.fullmatch(r"[0-9a-f]{24}", site_ref):
            _report("site_inventory", 0, None, "response_invalid")
            failed = True
            continue
        device_rows: list[dict[str, Any]] | None = None
        for resource in ("devices", "clients"):
            status, data, error = _request(base, token, f"/v1/sites/{site_ref}/{resource}", budget)
            rows = _items(data)
            result_error = error or (None if rows is not None else "response_invalid")
            _report(resource, status, len(rows) if rows is not None else None, result_error)
            if resource in ("devices", "clients") and result_error:
                failed = True
            if resource == "devices":
                device_rows = rows
            if resource != "devices" or rows is None:
                continue
            # Try only a small bounded set; connector validation determines which
            # opaque device references are eligible APs.
            candidates = _ap_candidates(rows, limit=MAX_DEVICES)
            for part in ("radio-config", "radios", "scan-status", "channel-load"):
                successes = 0
                last_status = 0
                last_error: str | None = "no_ap_candidate"
                for device_ref in candidates:
                    last_status, ap_data, last_error = _request(
                        base, token, f"/v1/sites/{site_ref}/aps/{device_ref}/{part}", budget)
                    if last_error is None and ap_data is not None:
                        successes += 1
                        last_error = None
                        break
                _report("ap_" + part, last_status, successes, last_error)

        if os.environ.get("OMADA_PROBE_EXTENDED_READS") == "1":
            status, data, error = _request(
                base, token, f"/v1/sites/{site_ref}/topology", budget)
            result_count = _safe_result_count("site_topology", data)
            result_error = error or (None if result_count is not None else "response_invalid")
            _report("site_topology", status, result_count, result_error)
            if result_error:
                failed = True
            ap_refs = _ap_candidates(device_rows or [], limit=MAX_EXTENDED_APS)
            if not ap_refs:
                _report("ap_health", 0, None, "no_ap_candidate")
                _report("ap_mesh_statistics", 0, None, "no_ap_candidate")
                failed = True
            for device_ref in ap_refs:
                for resource in ("ap_health", "ap_mesh_statistics"):
                    suffix = "health" if resource == "ap_health" else "mesh"
                    status, data, error = _request(
                        base, token, f"/v1/sites/{site_ref}/aps/{device_ref}/{suffix}", budget)
                    result_count = _safe_result_count(resource, data)
                    result_error = error or (None if result_count is not None else "response_invalid")
                    _report(resource, status, result_count, result_error)
                    if result_error:
                        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
