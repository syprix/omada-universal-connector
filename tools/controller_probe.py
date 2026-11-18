#!/usr/bin/env python3
"""Verify a pinned, read-only controller connection without exposing inventory."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Protocol


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError  # noqa: E402


class SiteReader(Protocol):
    def list_sites(self) -> dict[str, object]: ...


def probe(client: SiteReader) -> dict[str, object]:
    """Return only the result of one fixed site-inventory read."""
    result = client.list_sites()
    count = result.get("count") if isinstance(result, dict) else None
    if type(count) is not int or count < 0:
        raise OpenApiError("openapi_response_invalid")
    return {
        "status": "ok",
        "controller": "reachable",
        "site_count": count,
        "read_only": True,
    }


def main() -> int:
    try:
        client = OmadaOpenApiClient(OpenApiConfig.from_env())
        result = probe(client)
    except OpenApiError as exc:
        result = {"status": "error", "error": exc.code, "read_only": True}
    except Exception:
        result = {"status": "error", "error": "controller_probe_failed", "read_only": True}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
