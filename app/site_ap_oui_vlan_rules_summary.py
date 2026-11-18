"""Redacted summary of the documented AP OUI-based VLAN rules."""
from __future__ import annotations

from typing import Any


class ApOuiVlanRulesError(ValueError):
    """The controller AP OUI rule result is outside the bounded schema."""


_GRID_FIELDS = frozenset({"totalRows", "currentPage", "currentSize", "data"})
_RULE_FIELDS = frozenset({"id", "enable", "name", "ssidList", "ruleCombine"})
_SSID_FIELDS = frozenset({"ssidId", "ssidName"})
_VLAN_FIELDS = frozenset({"vlanId", "priority", "ouiProfileId", "ouiProfileName"})
_MAX_RULES = 10_000
_MAX_NESTED = 512
_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def project_site_ap_oui_vlan_rules_summary(raw: object) -> dict[str, Any]:
    """Count rule state and bindings without returning identifiers or values."""
    if not isinstance(raw, dict) or len(raw) > 12:
        raise ApOuiVlanRulesError("response_invalid")
    total = raw.get("totalRows")
    rows = raw.get("data")
    if (not _integer(total, 0, _INT64_MAX) or not isinstance(rows, list) or
            len(rows) > _MAX_RULES or len(rows) != total):
        raise ApOuiVlanRulesError("response_invalid")

    enabled = disabled = state_unknown = 0
    ssid_lists = ssid_bindings = vlan_lists = vlan_assignments = 0
    redacted = invalid = 0
    unknown = sum(1 for key in raw if key not in _GRID_FIELDS)
    priorities: dict[str, int] = {}

    for row in rows:
        if not isinstance(row, dict) or len(row) > 24:
            raise ApOuiVlanRulesError("response_invalid")
        unknown += sum(1 for key in row if key not in _RULE_FIELDS)
        redacted += sum(1 for key in ("id", "name") if key in row)
        for key in ("id", "name"):
            if key in row and not isinstance(row[key], str):
                invalid += 1

        if "enable" not in row:
            state_unknown += 1
        elif type(row["enable"]) is bool:
            enabled += int(row["enable"])
            disabled += int(not row["enable"])
        else:
            invalid += 1
            state_unknown += 1

        if "ssidList" in row:
            bindings = row["ssidList"]
            if not isinstance(bindings, list) or len(bindings) > _MAX_NESTED:
                invalid += 1
            else:
                ssid_lists += 1
                ssid_bindings += len(bindings)
                for binding in bindings:
                    if not isinstance(binding, dict) or len(binding) > 8:
                        invalid += 1
                        continue
                    unknown += sum(1 for key in binding if key not in _SSID_FIELDS)
                    for key in _SSID_FIELDS:
                        if key in binding:
                            if isinstance(binding[key], str):
                                redacted += 1
                            else:
                                invalid += 1

        if "ruleCombine" in row:
            assignments = row["ruleCombine"]
            if not isinstance(assignments, list) or len(assignments) > _MAX_NESTED:
                invalid += 1
            else:
                vlan_lists += 1
                vlan_assignments += len(assignments)
                for assignment in assignments:
                    if not isinstance(assignment, dict) or len(assignment) > 8:
                        invalid += 1
                        continue
                    unknown += sum(1 for key in assignment if key not in _VLAN_FIELDS)
                    redacted += sum(1 for key in ("ouiProfileId", "ouiProfileName")
                                    if key in assignment)
                    for required in ("vlanId", "priority", "ouiProfileId"):
                        if required not in assignment:
                            invalid += 1
                    if "vlanId" in assignment and not _integer(assignment["vlanId"], 2, 4090):
                        invalid += 1
                    if "priority" in assignment:
                        priority = assignment["priority"]
                        if _integer(priority, 0, 7):
                            key = str(priority)
                            priorities[key] = priorities.get(key, 0) + 1
                        else:
                            invalid += 1
                    if "ouiProfileId" in assignment and not isinstance(assignment["ouiProfileId"], str):
                        invalid += 1
                    if ("ouiProfileName" in assignment and
                            not isinstance(assignment["ouiProfileName"], str)):
                        invalid += 1

    return {
        "status": "ok",
        "resource": "site_ap_oui_vlan_rules_summary",
        "total_rules": total,
        "enabled_rules": enabled,
        "disabled_rules": disabled,
        "rule_state_unknown": state_unknown,
        "rules_with_ssid_list": ssid_lists,
        "ssid_binding_count": ssid_bindings,
        "rules_with_vlan_assignments": vlan_lists,
        "vlan_assignment_count": vlan_assignments,
        "priority_counts": priorities,
        "partial": bool(unknown or invalid or state_unknown or ssid_lists != total or
                         vlan_lists != total),
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
    }
