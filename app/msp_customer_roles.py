"""Identity-free summary for MSP customer roles."""
from __future__ import annotations

from typing import Any

MAX_ROLES = 1_000
ROLE_TYPES = {0: "standard", 1: "customer", 2: "msp"}
ROLE_SOURCES = {0: "default", 1: "controller_created", 2: "msp_created"}


class MspCustomerRolesError(ValueError):
    """Raised when the documented customer-role result is outside bounds."""


def project_msp_customer_roles(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_ROLES:
        raise MspCustomerRolesError("response_invalid")
    role_types = {name: 0 for name in ROLE_TYPES.values()}
    role_sources = {name: 0 for name in ROLE_SOURCES.values()}
    default_count = 0
    role_count = 0
    invalid_count = 0
    unknown_field_count = 0
    privilege_role_count = 0
    allowed = {"id", "name", "type", "defaultRole", "source", "privilege"}
    for row in result:
        if not isinstance(row, dict) or len(row) > 12:
            raise MspCustomerRolesError("response_invalid")
        unknown_field_count += len(set(row) - allowed)
        valid = True
        role_type = row.get("type")
        source = row.get("source")
        default = row.get("defaultRole")
        if type(role_type) is int and role_type in ROLE_TYPES:
            role_types[ROLE_TYPES[role_type]] += 1
        else:
            invalid_count += 1
            valid = False
        if type(source) is int and source in ROLE_SOURCES:
            role_sources[ROLE_SOURCES[source]] += 1
        else:
            invalid_count += 1
            valid = False
        if type(default) is bool:
            default_count += int(default)
        else:
            invalid_count += 1
            valid = False
        for key in ("id", "name"):
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 256):
                invalid_count += 1
                valid = False
        privilege = row.get("privilege")
        if privilege is not None:
            if not isinstance(privilege, dict) or len(privilege) > 2_048:
                invalid_count += 1
                valid = False
            else:
                privilege_role_count += 1
        role_count += int(valid)
    return {
        "data": {
            "role_count": role_count,
            "role_types": role_types,
            "role_sources": role_sources,
            "default_role_count": default_count,
            "privilege_defined_role_count": privilege_role_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(invalid_count or unknown_field_count),
    }
