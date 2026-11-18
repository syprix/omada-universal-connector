"""Redacted, bounded validation for site Internet load-balance settings."""

from __future__ import annotations

from collections.abc import Mapping


class SiteInternetLoadBalanceSummaryError(ValueError):
    """The source response is not a bounded load-balance settings object."""


_FIELDS = frozenset((
    "weights", "appOptRouting", "linkBackup", "method", "primaryWans",
    "backupWan", "backupMode", "mode", "timeRangeId", "virtualWanWeights",
))
_VIRTUAL_WEIGHT_FIELDS = frozenset((
    "virtualWanId", "weight", "name", "physicalWanId",
))
_MAX_ARRAY = 256
_MAX_WEIGHT = 2_147_483_647


def project_site_internet_load_balance(value: object) -> dict[str, object]:
    """Return safe flags and counts, never port, virtual-WAN, or schedule IDs."""
    if not isinstance(value, Mapping) or len(value) > 32:
        raise SiteInternetLoadBalanceSummaryError("load-balance result must be an object")

    missing = invalid = unknown = 0
    truncated = False
    for key in ("weights", "appOptRouting", "linkBackup"):
        if key not in value:
            missing += 1
    unknown += sum(key not in _FIELDS for key in value)

    flags: dict[str, bool | None] = {}
    for field, output in (("appOptRouting", "application_optimized_routing_enabled"),
                          ("linkBackup", "link_backup_enabled")):
        raw = value.get(field)
        if type(raw) is bool:
            flags[output] = raw
        else:
            flags[output] = None
            if field in value:
                invalid += 1

    weight_count = invalid_weight_count = 0
    weights = value.get("weights")
    if weights is None:
        if "weights" in value:
            invalid += 1
    elif not isinstance(weights, list) or len(weights) > _MAX_ARRAY:
        invalid += 1
        truncated = isinstance(weights, list) and len(weights) > _MAX_ARRAY
    else:
        for weight in weights:
            if type(weight) is int and 1 <= weight <= _MAX_WEIGHT:
                weight_count += 1
            else:
                invalid_weight_count += 1
                invalid += 1

    primary_wans = value.get("primaryWans")
    primary_wan_count = None
    if "primaryWans" in value:
        if isinstance(primary_wans, list) and len(primary_wans) <= _MAX_ARRAY:
            valid_primary_wans = [item for item in primary_wans
                                  if isinstance(item, str) and len(item) <= 256]
            primary_wan_count = len(valid_primary_wans)
            invalid += len(primary_wans) - primary_wan_count
        else:
            invalid += 1
            truncated = isinstance(primary_wans, list) and len(primary_wans) > _MAX_ARRAY

    virtual_count = invalid_virtual_count = 0
    virtual_weights = value.get("virtualWanWeights")
    if "virtualWanWeights" in value:
        if isinstance(virtual_weights, list) and len(virtual_weights) <= _MAX_ARRAY:
            for row in virtual_weights:
                if not isinstance(row, Mapping) or len(row) > 16:
                    invalid += 1
                    invalid_virtual_count += 1
                    continue
                unknown += sum(key not in _VIRTUAL_WEIGHT_FIELDS for key in row)
                if not isinstance(row.get("virtualWanId"), str) or len(row["virtualWanId"]) > 256:
                    missing += 1
                    invalid_virtual_count += 1
                    continue
                weight = row.get("weight")
                if weight is not None and (type(weight) is not int or
                                           not 0 <= weight <= _MAX_WEIGHT):
                    invalid += 1
                    invalid_virtual_count += 1
                    continue
                virtual_count += 1
        else:
            invalid += 1
            truncated = isinstance(virtual_weights, list) and len(virtual_weights) > _MAX_ARRAY

    code_counts: dict[str, dict[str, int]] = {}
    for field, allowed in (("backupMode", (0, 1)), ("mode", (0, 1, 2))):
        counts = {str(code): 0 for code in allowed}
        raw = value.get(field)
        if field in value:
            if type(raw) is int and raw in allowed:
                counts[str(raw)] = 1
            elif type(raw) is int:
                unknown += 1
            else:
                invalid += 1
        code_counts[field] = counts

    optional_presence: dict[str, bool | None] = {}
    for field in ("method", "backupWan", "timeRangeId"):
        if field not in value:
            optional_presence[field] = None
        elif isinstance(value[field], str) and len(value[field]) <= 256:
            optional_presence[field] = bool(value[field])
        else:
            optional_presence[field] = None
            invalid += 1

    return {
        "data": {
            **flags,
            "weight_count": weight_count,
            "invalid_weight_count": invalid_weight_count,
            "primary_wan_count": primary_wan_count,
            "valid_virtual_wan_count": virtual_count,
            "invalid_virtual_wan_count": invalid_virtual_count,
            "documented_mode_code_counts": code_counts,
            "optional_setting_presence": optional_presence,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
