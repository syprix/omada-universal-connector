"""Privacy-preserving projection for the documented duplicate-SSID read."""

from __future__ import annotations

from typing import Any

MAX_DUPLICATE_NAMES = 256
INT64_MAX = 2**63 - 1


class DuplicateSsidProjectionError(ValueError):
    """The upstream duplicate-SSID summary has an invalid shape or value."""


def project_duplicate_ssid_summary(result: Any, expected_site_id: str) -> dict[str, object]:
    """Return counts only; never return SSID names or the controller site ID."""
    if not isinstance(result, dict) or not isinstance(expected_site_id, str):
        raise DuplicateSsidProjectionError("response_invalid")

    known = {"ssidNameMap", "duplicateSsidNames", "siteId"}
    unknown_field_count = sum(1 for key in result if key not in known)
    partial = unknown_field_count > 0
    out: dict[str, object] = {"unknown_field_count": unknown_field_count}

    source_map = result.get("ssidNameMap")
    if source_map is None:
        out["duplicate_name_map_entries"] = None
        out["duplicate_ssid_count_sum"] = None
        partial = True
    else:
        if not isinstance(source_map, dict) or len(source_map) > MAX_DUPLICATE_NAMES:
            raise DuplicateSsidProjectionError("response_invalid")
        total = 0
        for name, count in source_map.items():
            if not isinstance(name, str) or not name or len(name) > 128:
                raise DuplicateSsidProjectionError("response_invalid")
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= INT64_MAX:
                raise DuplicateSsidProjectionError("response_invalid")
            total += count
            if total > INT64_MAX:
                raise DuplicateSsidProjectionError("response_invalid")
        out["duplicate_name_map_entries"] = len(source_map)
        out["duplicate_ssid_count_sum"] = total

    source_names = result.get("duplicateSsidNames")
    if source_names is None:
        out["duplicate_name_count"] = None
        partial = True
    else:
        if not isinstance(source_names, list) or len(source_names) > MAX_DUPLICATE_NAMES:
            raise DuplicateSsidProjectionError("response_invalid")
        if any(not isinstance(name, str) or not name or len(name) > 128
               for name in source_names):
            raise DuplicateSsidProjectionError("response_invalid")
        out["duplicate_name_count"] = len(source_names)
        if isinstance(source_map, dict) and set(source_names) != set(source_map):
            partial = True

    site_id = result.get("siteId")
    if site_id is None:
        out["site_id_match"] = None
        partial = True
    elif not isinstance(site_id, str) or site_id != expected_site_id:
        raise DuplicateSsidProjectionError("response_invalid")
    else:
        out["site_id_match"] = True

    out["partial"] = partial
    return out
