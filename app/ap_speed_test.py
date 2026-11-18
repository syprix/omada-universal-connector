"""Bounded projection for existing AP link speed-test results."""
from __future__ import annotations

import math
import re
from typing import Any


class ApSpeedTestError(ValueError):
    """The controller returned an invalid speed-test result shape."""


_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}\Z")
_ITEM_FIELDS = frozenset({"role", "downRate", "upRate", "time", "status", "errorCode", "errorMsg"})


def _int(value: object, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _rate(value: object) -> bool:
    if type(value) is int:
        return 0 <= value <= 1_000_000_000
    return type(value) is float and math.isfinite(value) and 0 <= value <= 1_000_000_000


def project_ap_speed_test(value: object, device_ref: str,
                          device_refs_by_mac: dict[str, str]) -> dict[str, Any]:
    if not isinstance(value, dict) or len(value) > 16:
        raise ApSpeedTestError("response_invalid")
    partial = bool(set(value) - {"mainTesting", "sourceAP", "targetAP", "speedTestResult"})
    data: dict[str, Any] = {}
    if "mainTesting" in value:
        if type(value["mainTesting"]) is bool:
            data["main_testing"] = value["mainTesting"]
        else:
            partial = True
    else:
        partial = True

    for source, target in (("sourceAP", "source_ap_ref"), ("targetAP", "target_ap_ref")):
        mac = value.get(source)
        if mac == "":
            continue
        if not isinstance(mac, str) or not _MAC.fullmatch(mac):
            partial = True
            continue
        ref = device_refs_by_mac.get(re.sub(r"[:-]", "", mac).lower())
        if ref is None:
            partial = True
        else:
            data[target] = ref

    raw_results = value.get("speedTestResult")
    if raw_results is None:
        results: list[object] = []
        partial = True
    elif not isinstance(raw_results, dict):
        raise ApSpeedTestError("response_invalid")
    elif "role" in raw_results:
        results = [raw_results]
    else:
        if len(raw_results) > 4:
            raise ApSpeedTestError("response_invalid")
        results = list(raw_results.values())
        if any(not isinstance(key, str) or len(key) > 96 for key in raw_results):
            partial = True

    projected: list[dict[str, object]] = []
    seen_roles: set[int] = set()
    for item in results:
        if not isinstance(item, dict) or len(item) > 16:
            raise ApSpeedTestError("response_invalid")
        clean: dict[str, object] = {}
        if set(item) - _ITEM_FIELDS:
            partial = True
        role = item.get("role")
        if not _int(role, minimum=0, maximum=1) or role in seen_roles:
            partial = True
            continue
        seen_roles.add(role)
        clean["role"] = role
        if "downRate" in item:
            if _rate(item["downRate"]):
                clean["down_rate"] = item["downRate"]
            else:
                partial = True
        else:
            partial = True
        if "upRate" in item:
            if _rate(item["upRate"]):
                clean["up_rate"] = item["upRate"]
            else:
                partial = True
        else:
            partial = True
        if "time" in item:
            if _int(item["time"], minimum=0, maximum=2**63 - 1):
                clean["time_ms"] = item["time"]
            else:
                partial = True
        if "status" in item:
            if _int(item["status"], minimum=-2, maximum=1):
                clean["status"] = item["status"]
            else:
                partial = True
        else:
            partial = True
        if "errorCode" in item:
            if _int(item["errorCode"], minimum=-(2**31), maximum=2**31 - 1):
                clean["error_code"] = item["errorCode"]
            else:
                partial = True
        # Error text is controller-generated and may contain identifiers.
        if "errorMsg" in item:
            partial = True
        projected.append(clean)
    projected.sort(key=lambda row: row["role"])
    data["results"] = projected
    return {"status": "ok", "resource": "ap_speed_test_results",
            "device_ref": device_ref, "data": data, "partial": partial}
