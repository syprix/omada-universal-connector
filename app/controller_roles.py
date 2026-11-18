"""Redacted aggregate projections for controller-wide role GET responses."""
from __future__ import annotations

from typing import Any


MAX_ROLES = 500
MAX_PRIVILEGE_FIELDS = 64
_ROW_FIELDS = {"id", "name", "type", "defaultRole", "source", "privilege"}
_PRIVILEGE_FIELDS = {
    "license", "globalDashboard", "dashboard", "devices", "adopt", "addDevices",
    "addAdoptDevice", "manualUpgrade", "globalLog", "log", "licenseBind", "users",
    "roles", "samlUsers", "samlRoles", "samlSsos", "globalSetting", "exportData",
    "globalExportData", "exportGlobalLog", "globalCluster", "hotspot", "statics",
    "map", "clients", "insight", "report", "network", "deviceAccount", "anomaly",
    "analyze", "siteAnalyze", "globalSecurity", "globalWebhook", "globalMapToken",
    "siteTemplate", "firmwareManager", "sdWan", "siteHome", "deviceRecovery",
    "siteNetwork", "siteDevice", "siteMaintain", "aiAssi",
}


class ControllerRolesError(ValueError):
    """Raised when a documented role response is not safely bounded."""


def project_controller_roles(result: Any, *, includes_privilege: bool) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_ROLES:
        raise ControllerRolesError("response_invalid")
    type_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    permission_counts = {"0": 0, "1": 0, "2": 0}
    default_count = 0
    id_present = 0
    name_present = 0
    privilege_present = 0
    missing = 0
    invalid = 0
    unknown = 0

    for row in result:
        if not isinstance(row, dict):
            invalid += 1
            continue
        known = _ROW_FIELDS if includes_privilege else _ROW_FIELDS - {"privilege"}
        unknown += len(set(row) - known)
        role_id = row.get("id")
        if role_id is None:
            missing += 1
        elif isinstance(role_id, str):
            id_present += int(bool(role_id))
        else:
            invalid += 1
        name = row.get("name")
        if name is None:
            missing += 1
        elif isinstance(name, str):
            name_present += int(bool(name))
        else:
            invalid += 1

        for field, counts, labels in (
            ("type", type_counts, {0: "standard", 1: "customer", 2: "msp"}),
            ("source", source_counts, {0: "default", 1: "controller_or_customer", 2: "msp"}),
        ):
            value = row.get(field)
            if value is None:
                missing += 1
            elif type(value) is int and value in labels:
                label = labels[value]
                counts[label] = counts.get(label, 0) + 1
            elif type(value) is int and 0 <= value <= 2_147_483_647:
                counts["unknown"] = counts.get("unknown", 0) + 1
                unknown += 1
            else:
                invalid += 1

        default_role = row.get("defaultRole")
        if default_role is None:
            missing += 1
        elif type(default_role) is bool:
            default_count += int(default_role)
        else:
            invalid += 1

        if includes_privilege:
            privilege = row.get("privilege")
            if privilege is None:
                missing += 1
            elif isinstance(privilege, dict) and len(privilege) <= MAX_PRIVILEGE_FIELDS:
                privilege_present += 1
                unknown += len(set(privilege) - _PRIVILEGE_FIELDS)
                for field, value in privilege.items():
                    if field not in _PRIVILEGE_FIELDS:
                        continue
                    if type(value) is int and value in (0, 1, 2):
                        permission_counts[str(value)] += 1
                    else:
                        invalid += 1
            else:
                invalid += 1

    return {
        "data": {
            "role_count": len(result),
            "type_counts": type_counts,
            "source_counts": source_counts,
            "default_role_count": default_count,
            "role_id_present_count": id_present,
            "role_name_present_count": name_present,
            "privilege_object_present_count": privilege_present,
            "permission_code_counts": permission_counts if includes_privilege else None,
            "missing_count": missing,
            "invalid_count": invalid,
            "unknown_field_count": unknown,
        },
        "partial": bool(missing or invalid or unknown),
    }
