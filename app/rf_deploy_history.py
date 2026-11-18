"""Projection of the documented WLAN first-deployment flag."""
from __future__ import annotations


class RfDeployHistoryError(ValueError):
    """The deployment history response is malformed."""


def project_rf_deploy_history(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise RfDeployHistoryError()
    missing = "firstDeploy" not in raw
    value = raw.get("firstDeploy")
    valid = type(value) is bool
    return {
        "status": "ok",
        "resource": "rf_deploy_history",
        "data": {"first_deployment": value} if valid else {},
        "partial": missing or not valid or len(raw) > 1,
        "missing_fields": ["firstDeploy"] if missing else [],
        "omitted_field_count": (0 if missing or valid else 1) + max(0, len(raw) - 1),
        "omitted_fields": sorted(set(([] if valid or missing else ["invalid_value"]) +
                                     (["unknown_fields"] if len(raw) > 1 else []))),
    }
