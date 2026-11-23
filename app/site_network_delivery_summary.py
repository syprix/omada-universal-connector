"""Redacted network configuration delivery progress projection."""
from __future__ import annotations

from collections.abc import Mapping


class SiteNetworkDeliveryError(ValueError):
    pass


_ARRAYS = ("successDevices", "successStacks", "failDevices", "failStacks",
          "deliveringDevices", "deliveringStacks")
_STATE_NAMES = {0: "free_already_delivered", 1: "delivering", 2: "delivery_done"}


def project_site_network_delivery(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteNetworkDeliveryError("result_invalid")
    allowed = set(_ARRAYS) | {"doneDevicesNum", "totalDevicesNum", "state"}
    partial = bool(set(result) - allowed)
    counts: dict[str, int] = {}
    for field in _ARRAYS:
        rows = result.get(field, [])
        if not isinstance(rows, list) or len(rows) > 20_000:
            raise SiteNetworkDeliveryError("list_invalid")
        if any(not isinstance(value, str) or len(value) > 512 for value in rows):
            raise SiteNetworkDeliveryError("identity_invalid")
        counts[field] = len(rows)
        if field not in result:
            partial = True
    done = result.get("doneDevicesNum")
    total = result.get("totalDevicesNum")
    state = result.get("state")
    for value in (done, total):
        if value is not None and (type(value) is not int or not 0 <= value < (1 << 31)):
            raise SiteNetworkDeliveryError("count_invalid")
    if state is not None and (type(state) is not int or state not in _STATE_NAMES):
        raise SiteNetworkDeliveryError("state_invalid")
    if done is None or total is None or state is None:
        partial = True
    if done is not None and total is not None and done > total:
        raise SiteNetworkDeliveryError("count_invalid")
    if done is not None and done != counts["successDevices"]:
        partial = True
    if total is not None and total < counts["successDevices"] + counts["failDevices"] + counts["deliveringDevices"]:
        partial = True
    return {
        "state_code": state,
        "state": _STATE_NAMES.get(state, "unknown"),
        "done_device_count": done,
        "total_device_count": total,
        "device_counts": {
            "succeeded": counts["successDevices"],
            "failed": counts["failDevices"],
            "delivering": counts["deliveringDevices"],
        },
        "stack_counts": {
            "succeeded": counts["successStacks"],
            "failed": counts["failStacks"],
            "delivering": counts["deliveringStacks"],
        },
        "partial": partial,
        "reachability_inferred": False,
    }
