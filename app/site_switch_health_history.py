"""Redacted site-level switch health timeline projection."""
from __future__ import annotations

import re
from collections.abc import Mapping

from .switch_health_timeline import (
    SwitchHealthTimelineError, project_switch_health_timeline,
)


_MAX_SWITCHES = 64
_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}\Z")
_INT64_MAX = 2**63 - 1


class SiteSwitchHealthHistoryError(ValueError):
    def __init__(self, code: str = "site_switch_health_history_response_invalid") -> None:
        super().__init__(code)
        self.code = code


def _mac_key(value: object) -> str | None:
    if not isinstance(value, str) or not _MAC.fullmatch(value):
        return None
    return re.sub(r"[:-]", "", value).casefold()


def project_site_switch_health_history(
        raw: object, refs_by_mac: Mapping[str, list[str]], switch_refs: list[str],
        start_ms: int, end_ms: int, *, max_switches: int = _MAX_SWITCHES
        ) -> dict[str, object]:
    """Map the documented MAC timeline rows to site-bound opaque switch refs."""
    if (not isinstance(raw, dict) or len(raw) > 32 or
            any(not isinstance(key, str) or len(key) > 128 for key in raw) or
            type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX or
            end_ms - start_ms != 86_400_000 or
            type(max_switches) is not int or not 1 <= max_switches <= _MAX_SWITCHES or
            not isinstance(switch_refs, list) or len(switch_refs) > 10_000 or
            any(not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{24}", ref)
                for ref in switch_refs)):
        raise SiteSwitchHealthHistoryError()

    ordered_refs = sorted(set(switch_refs))
    queried_refs = ordered_refs[:max_switches]
    deferred_refs = ordered_refs[max_switches:]
    mac_to_ref: dict[str, str] = {}
    ambiguous_macs: set[str] = set()
    for key, refs in refs_by_mac.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{12}", key) or
                not isinstance(refs, list) or
                any(not isinstance(ref, str) or
                    not re.fullmatch(r"[0-9a-f]{24}", ref) or ref not in queried_refs
                    for ref in refs)):
            raise SiteSwitchHealthHistoryError()
        if len(refs) == 1:
            mac_to_ref[key] = refs[0]
        elif len(refs) > 1:
            ambiguous_macs.add(key)

    timeline = raw.get("timeline")
    missing_fields: list[str] = []
    omitted_fields: set[str] = set()
    omitted_count = 0
    projected_by_ref: dict[str, dict[str, object]] = {}
    root_extras = sum(key != "timeline" for key in raw)
    if root_extras:
        omitted_fields.add("unknown_fields")
        omitted_count += root_extras
    if "timeline" not in raw:
        missing_fields.append("timeline")
    elif not isinstance(timeline, list) or len(timeline) > _MAX_SWITCHES:
        omitted_fields.add("timeline")
        omitted_count += 1
    else:
        for row in timeline:
            if not isinstance(row, dict) or len(row) > 8:
                omitted_fields.add("invalid_timeline_rows")
                omitted_count += 1
                continue
            key = _mac_key(row.get("mac"))
            ref = mac_to_ref.get(key or "")
            if ref is None or ref in projected_by_ref:
                omitted_fields.add("unmapped_or_duplicate_switch_rows")
                omitted_count += 1
                continue
            extras = sum(name not in {"mac", "scores"} for name in row)
            if extras:
                omitted_fields.add("unknown_fields")
                omitted_count += extras
            try:
                projected = project_switch_health_timeline(
                    {"scores": row.get("scores")} if "scores" in row else {},
                    start_ms, end_ms)
            except SwitchHealthTimelineError:
                raise SiteSwitchHealthHistoryError() from None
            projected_by_ref[ref] = {
                "switch_ref": ref,
                "scores": projected["data"]["scores"],
                "partial": projected["partial"],
                "missing_fields": projected["missing_fields"],
                "omitted_field_count": projected["omitted_field_count"],
                "omitted_fields": projected["omitted_fields"],
            }

    missing_refs = [ref for ref in queried_refs if ref not in projected_by_ref]
    if missing_refs:
        omitted_fields.add("missing_switch_rows")
        omitted_count += len(missing_refs)
    if deferred_refs:
        omitted_fields.add("switch_limit_exceeded")
        omitted_count += len(deferred_refs)
    if ambiguous_macs:
        omitted_fields.add("ambiguous_inventory_mapping")
        omitted_count += len(ambiguous_macs)
    data = [projected_by_ref[ref] for ref in queried_refs if ref in projected_by_ref]
    partial = bool(missing_fields or omitted_count or
                   any(item["partial"] for item in data))
    return {
        "status": "ok", "resource": "site_switch_health_history",
        "window_start_ms": start_ms, "window_end_ms": end_ms,
        "query_time_unit": "milliseconds_documented_not_live_verified",
        "source": "controller_switch_health_timeline",
        "device_limit": max_switches,
        "devices_considered": len(ordered_refs),
        "devices_queried": len(queried_refs),
        "devices_returned": len(data),
        "missing_switch_refs": missing_refs,
        "unqueried_switch_refs": deferred_refs,
        "data": data,
        "partial": partial,
        "missing_fields": missing_fields,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted_fields),
    }
