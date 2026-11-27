"""Redacted coverage for the documented site access-control configuration."""
from __future__ import annotations

from typing import Any


MAX_SOURCE_FIELDS = 16
MAX_POLICY_ENTRIES = 500
MISSING_ACCESS_CONTROL_RESULT = object()

FLAG_FIELDS = (
    ("preAuthAccessEnable", "pre_auth_access_enabled"),
    ("freeAuthClientEnable", "free_auth_client_enabled"),
)
POLICY_FIELDS = (
    ("preAuthAccessPolicies", "pre_auth_access_policies"),
    ("freeAuthClientPolicies", "free_auth_client_policies"),
)


class SiteAccessControlPolicyCoverageError(ValueError):
    """The top-level controller response exceeds the safe documented shape."""


def _policy_list_coverage(result: dict[str, Any], field: str) -> dict[str, object]:
    if field not in result:
        return {"present": False, "form_valid": None, "entry_count": None,
                "state": "missing"}
    value = result[field]
    if not isinstance(value, list):
        return {"present": True, "form_valid": False, "entry_count": None,
                "state": "invalid"}

    # Deliberately use only the list length. Policy entries may contain
    # identities and network values; this reader never iterates or indexes them.
    count = len(value)
    if count > MAX_POLICY_ENTRIES:
        state = "over_limit"
    elif count == 0:
        state = "empty"
    else:
        state = "nonempty"
    return {"present": True, "form_valid": True,
            "entry_count": min(count, MAX_POLICY_ENTRIES),
            "state": state}


def project_site_access_control_policy_coverage(result: Any) -> dict[str, object]:
    """Return only two documented flags and bounded policy-list shape/counts."""
    if result is MISSING_ACCESS_CONTROL_RESULT:
        source: dict[str, Any] = {}
        source_state = "missing"
    elif isinstance(result, dict) and len(result) <= MAX_SOURCE_FIELDS:
        source = result
        source_state = "present"
    else:
        raise SiteAccessControlPolicyCoverageError("response_invalid")

    flags: dict[str, bool | None] = {}
    flag_coverage: dict[str, dict[str, bool]] = {}
    missing = 0
    invalid = 0
    over_limit = 0
    for field, output in FLAG_FIELDS:
        present = field in source
        value = source.get(field)
        valid = present and type(value) is bool
        flags[output] = value if valid else None
        flag_coverage[output] = {"present": present, "type_valid": valid}
        if not present:
            missing += 1
        elif not valid:
            invalid += 1

    policy_coverage = {
        output: _policy_list_coverage(source, field)
        for field, output in POLICY_FIELDS
    }
    for field, output in POLICY_FIELDS:
        coverage = policy_coverage[output]
        if not coverage["present"]:
            missing += 1
        elif coverage["state"] == "invalid":
            invalid += 1
        elif coverage["state"] == "over_limit":
            over_limit += 1

    documented = {field for field, _ in FLAG_FIELDS + POLICY_FIELDS}
    unknown = len(source) - sum(field in source for field in documented)
    return {
        "source_state": source_state,
        "data": flags,
        "flag_coverage": flag_coverage,
        "policy_list_coverage": policy_coverage,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "over_limit_field_count": over_limit,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or over_limit or unknown),
        "policy_contents_inspected": False,
    }
