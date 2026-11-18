"""Bounded counts from the deprecated site WLAN-group list endpoint."""

from __future__ import annotations

from collections.abc import Mapping


class SiteWlanGroupSummaryError(ValueError):
    """The WLAN-group response is not a bounded list."""


_FIELDS = frozenset((
    "wlanId", "id", "name", "primary", "clone", "cloneWlanId", "site", "resource",
))
_MAX_GROUPS = 500


def project_site_wlan_groups(value: object) -> dict[str, object]:
    """Count group flags and documented source codes without exposing identities."""
    if not isinstance(value, list):
        raise SiteWlanGroupSummaryError("WLAN-group result must be a list")

    reported = len(value)
    truncated = reported > _MAX_GROUPS
    rows = value[:_MAX_GROUPS]
    missing = invalid = unknown = valid = 0
    primary_true = primary_false = primary_unreported = 0
    clone_true = clone_false = clone_unreported = 0
    resource_counts = {"0": 0, "1": 0, "2": 0}
    resource_unknown = resource_unreported = 0

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            invalid += 1
            primary_unreported += 1
            clone_unreported += 1
            resource_unreported += 1
            continue
        valid += 1
        unknown += sum(field not in _FIELDS for field in row)
        for field in ("primary", "clone"):
            if field not in row:
                if field == "primary":
                    primary_unreported += 1
                else:
                    clone_unreported += 1
            elif type(row[field]) is not bool:
                invalid += 1
                if field == "primary":
                    primary_unreported += 1
                else:
                    clone_unreported += 1
            elif field == "primary" and row[field]:
                primary_true += 1
            elif field == "primary":
                primary_false += 1
            elif row[field]:
                clone_true += 1
            else:
                clone_false += 1

        if "resource" not in row:
            resource_unreported += 1
        elif type(row["resource"]) is not int:
            invalid += 1
            resource_unreported += 1
        elif str(row["resource"]) in resource_counts:
            resource_counts[str(row["resource"])] += 1
        else:
            resource_unknown += 1

    if truncated:
        invalid += 1
    return {
        "data": {
            "reported_group_count": reported,
            "valid_group_record_count": valid,
            "primary_group_flag_counts": {
                "enabled_count": primary_true,
                "disabled_count": primary_false,
                "unreported_count": primary_unreported,
            },
            "clone_flag_counts": {
                "enabled_count": clone_true,
                "disabled_count": clone_false,
                "unreported_count": clone_unreported,
            },
            "resource_code_counts": resource_counts,
            "unknown_resource_code_count": resource_unknown,
            "unreported_resource_count": resource_unreported,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or resource_unknown or truncated),
    }
