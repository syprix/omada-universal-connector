"""Redacted projection of documented AP wired-uplink status."""
from __future__ import annotations

import math
import re


class ApWiredUplinkError(ValueError):
    """The AP wired-uplink result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_wired_uplink_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_ROOT_FIELDS = frozenset({"wiredUplink"})
_REDACTED_FIELDS = frozenset({
    "uplinkMac", "stackId", "type", "name", "port", "ip", "model",
    "modelVersion", "uplinkPort",
})
_COUNTERS = (
    "upBytes", "downBytes", "upPackets", "downPackets", "upDropPackets",
    "downDropPackets", "upErrorsPackets", "downErrorsPackets", "activity",
)
_CORE_FIELDS = ("duplex", "portType", *_COUNTERS, "linkStatus", "linkSpeed")
_OPTIONAL_INT32 = frozenset({"poeState", "voipState"})
_NUMERIC_FIELDS = frozenset({"txPower", "rxPower", "temp", "voltage", "current"})
_OPTIONAL_FIELDS = _OPTIONAL_INT32 | _NUMERIC_FIELDS | frozenset({"rate"})
_ALLOWED_FIELDS = frozenset(_CORE_FIELDS) | _OPTIONAL_FIELDS | _REDACTED_FIELDS
_RATE_VALUES = {"0": 0, "10": 10, "100": 100, "1000": 1000,
                "2500": 2500, "10000": 10000}
_MAX_ROOT_FIELDS = 8
_MAX_INFO_FIELDS = 48
_MAX_KEY_LENGTH = 128
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_MAC_RE = re.compile(r"(?i)(?:(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2})\Z")
_REF_RE = re.compile(r"[0-9a-f]{24}\Z")


def _integer(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def project_ap_wired_uplink(raw: object, *,
                            device_ref_by_mac: dict[str, str] | None = None
                            ) -> dict[str, object]:
    """Project ``result.wiredUplink`` without exposing topology or identity.

    Core integers are validated against their documented int32/int64 storage
    widths. Sensor values have no unit or range interpretation. Optional
    counters/measurements omitted by a controller do not by themselves make a
    response partial; absent core values and empty safe projections do.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_ROOT_FIELDS:
        raise ApWiredUplinkError()
    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApWiredUplinkError()

    data: dict[str, dict[str, object]] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown = sum(1 for key in raw if key not in _ROOT_FIELDS)
    redacted = 0

    if "wiredUplink" not in raw:
        missing.append("wiredUplink")
    else:
        source = raw["wiredUplink"]
        if not isinstance(source, dict):
            if isinstance(source, (list, tuple)) and len(source) > _MAX_INFO_FIELDS:
                raise ApWiredUplinkError()
            invalid.append("wiredUplink")
            source = {}
        if len(source) > _MAX_INFO_FIELDS:
            raise ApWiredUplinkError()
        projected: dict[str, object] = {}
        for key, value in source.items():
            if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                raise ApWiredUplinkError()
            if key not in _ALLOWED_FIELDS:
                unknown += 1
                continue
            if key in _REDACTED_FIELDS:
                redacted += 1
                if key == "uplinkMac" and device_ref_by_mac is not None:
                    mapped_ref = None
                    if isinstance(value, str) and _MAC_RE.fullmatch(value):
                        mapped_ref = device_ref_by_mac.get(
                            value.replace(":", "").replace("-", "").lower())
                    if not isinstance(mapped_ref, str) or not _REF_RE.fullmatch(mapped_ref):
                        mapped_ref = None
                    projected["uplink_device_ref_status"] = (
                        "mapped" if mapped_ref is not None else "not_in_inventory")
                    if mapped_ref is not None:
                        projected["uplink_device_ref"] = mapped_ref
                continue
            if key == "rate":
                if type(value) is str and value in _RATE_VALUES:
                    projected["rate_mbps"] = _RATE_VALUES[value]
                else:
                    invalid.append("wiredUplink.rate")
            elif key == "duplex":
                if _integer(value, 0, 2):
                    projected[key] = value
                else:
                    invalid.append("wiredUplink." + key)
            elif key == "portType":
                if _integer(value, 0, 2):
                    projected[key] = value
                else:
                    invalid.append("wiredUplink." + key)
            elif key in _OPTIONAL_INT32:
                if _integer(value, 0, 1):
                    projected[key] = value
                else:
                    invalid.append("wiredUplink." + key)
            elif key in _NUMERIC_FIELDS:
                if _finite_number(value):
                    projected[key] = value
                else:
                    invalid.append("wiredUplink." + key)
            elif key in _COUNTERS or key in {"linkStatus", "linkSpeed"}:
                low, high = ((_INT64_MIN, _INT64_MAX) if key in _COUNTERS
                             else (_INT32_MIN, _INT32_MAX))
                if _integer(value, low, high):
                    projected[key] = value
                else:
                    invalid.append("wiredUplink." + key)

        for key in _CORE_FIELDS:
            if key not in source:
                missing.append("wiredUplink." + key)
        data["wiredUplink"] = projected

    if not any(data.values()):
        missing.append("safe_fields")
    return {
        "status": "ok",
        "resource": "ap_wired_uplink",
        "data": data,
        "partial": bool(missing or invalid or unknown),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown,
        "redacted_field_count": redacted,
    }
