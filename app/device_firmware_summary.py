"""Bounded, grouped firmware status for one site's inventoried devices."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

MAX_FIRMWARE_DEVICES = 64
_REF = re.compile(r"[0-9a-f]{24}\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+ -]{0,95}\Z")


class DeviceFirmwareSummaryError(ValueError):
    """Inventory or firmware evidence cannot be summarized safely."""


def _version(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value != value.strip() or not _VERSION.fullmatch(value):
        raise DeviceFirmwareSummaryError("firmware_data_invalid")
    return value


def _device_type(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().casefold()
    if normalized in {"ap", "access point", "accesspoint"}:
        return "ap"
    if normalized in {"gateway", "router", "gw"}:
        return "gateway"
    if normalized in {"switch", "sw"}:
        return "switch"
    if normalized == "olt":
        return "olt"
    return "other"


def project_site_firmware_summary(site_ref: str, inventory: object,
                                  firmware_by_ref: Mapping[str, object]) -> dict[str, object]:
    """Group current/latest firmware evidence without ordering version strings."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise DeviceFirmwareSummaryError("site_ref_invalid")
    if (not isinstance(inventory, Mapping) or inventory.get("status") != "ok" or
            inventory.get("resource") != "devices" or
            not isinstance(inventory.get("items"), list) or
            type(inventory.get("count")) is not int or
            inventory.get("count") != len(inventory["items"])):
        raise DeviceFirmwareSummaryError("inventory_invalid")

    rows = inventory["items"]
    selected = rows[:MAX_FIRMWARE_DEVICES]
    omitted = max(0, len(rows) - len(selected))
    seen: set[str] = set()
    grouped: Counter[tuple[str, str, str | None, str | None, str | None, str]] = Counter()
    status_counts: Counter[str] = Counter()
    partial = omitted > 0

    for row in selected:
        if (not isinstance(row, Mapping) or not isinstance(row.get("device_ref"), str) or
                not _REF.fullmatch(row["device_ref"]) or row["device_ref"] in seen):
            raise DeviceFirmwareSummaryError("inventory_invalid")
        ref = row["device_ref"]
        seen.add(ref)
        kind = _device_type(row.get("device_type"))
        model = row.get("model")
        if model is None:
            model = "unknown"
        elif (not isinstance(model, str) or model != model.strip() or len(model) > 96 or
              not _VERSION.fullmatch(model)):
            raise DeviceFirmwareSummaryError("inventory_invalid")
        inventory_version = _version(row.get("firmware"))

        response = firmware_by_ref.get(ref)
        current: str | None = None
        latest: str | None = None
        if (not isinstance(response, Mapping) or response.get("status") != "ok" or
                response.get("resource") != "device_firmware" or
                response.get("device_ref") != ref or not isinstance(response.get("data"), Mapping)):
            status = "read_unavailable"
            partial = True
        else:
            data = response["data"]
            current = _version(data.get("current_version"))
            latest = _version(data.get("latest_version"))
            if data.get("update_available") is not None:
                raise DeviceFirmwareSummaryError("firmware_data_invalid")
            expected_difference = ((current != latest)
                                   if current is not None and latest is not None else None)
            if data.get("versions_differ") is not expected_difference:
                raise DeviceFirmwareSummaryError("firmware_data_invalid")
            if (inventory_version is not None and current is not None and
                    inventory_version != current):
                status = "inventory_disagrees"
                partial = True
            elif current is None or latest is None:
                status = "version_unknown"
                partial = True
            elif current == latest:
                status = "matches_latest"
            else:
                status = "differs_from_latest"
        status_counts[status] += 1
        grouped[(kind, model, inventory_version, current, latest, status)] += 1

    groups = [
        {"device_type": key[0], "model": key[1], "inventory_version": key[2],
         "current_version": key[3], "latest_version": key[4],
         "firmware_status": key[5], "device_count": count}
        for key, count in sorted(grouped.items(), key=lambda item: tuple(
            "" if value is None else value for value in item[0]))
    ]
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_firmware_summary",
        "site_ref": site_ref,
        "summary": {
            "inventory_device_count": len(rows),
            "checked_device_count": len(selected),
            "omitted_device_count": omitted,
            "model_firmware_group_count": len(groups),
            "firmware_status_counts": dict(sorted(status_counts.items())),
        },
        "groups": groups,
        "data_scope": {
            "latest_version_source_field": "lastFwVer",
            "version_ordering": "not_inferred_from_version_strings",
            "differs_from_latest": "versions differ; update availability is not inferred",
            "read_limit": MAX_FIRMWARE_DEVICES,
        },
        "partial": partial,
    }
