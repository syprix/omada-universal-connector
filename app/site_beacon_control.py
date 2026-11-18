"""Bounded projection of site WLAN beacon and airtime settings."""
from __future__ import annotations

from typing import Any


class SiteBeaconControlError(ValueError):
    """Raised when a beacon-control response exceeds its schema bounds."""


_BEACON_FIELDS = {
    "beaconInterval2g": ("beacon_interval_2g", 40, 500),
    "beaconIntvMode2g": ("beacon_interval_mode_2g", None, None),
    "dtimPeriod2g": ("dtim_period_2g", 1, 255),
    "rtsThreshold2g": ("rts_threshold_2g", 1, 2347),
    "fragmentationThreshold2g": ("fragmentation_threshold_2g", 256, 2346),
    "beaconInterval5g": ("beacon_interval_5g", 40, 500),
    "beaconIntvMode5g": ("beacon_interval_mode_5g", None, None),
    "dtimPeriod5g": ("dtim_period_5g", 1, 255),
    "rtsThreshold5g": ("rts_threshold_5g", 1, 2347),
    "fragmentationThreshold5g": ("fragmentation_threshold_5g", 256, 2346),
    "beaconInterval6g": ("beacon_interval_6g", 40, 500),
    "beaconIntvMode6g": ("beacon_interval_mode_6g", None, None),
    "dtimPeriod6g": ("dtim_period_6g", 1, 255),
    "rtsThreshold6g": ("rts_threshold_6g", 1, 2347),
    "fragmentationThreshold6g": ("fragmentation_threshold_6g", 256, 2346),
    "probeResponseMaxRetransNum2g": ("probe_response_max_retransmissions_2g", 0, 3),
    "probeResponseMaxRetransNum5g": ("probe_response_max_retransmissions_5g", 0, 3),
    "probeResponseReplyThresholdMode2g": ("probe_response_threshold_mode_2g", None, None),
    "probeResponseReplyThresholdMode5g": ("probe_response_threshold_mode_5g", None, None),
    "probeResponseReplyThreshold2g": ("probe_response_threshold_dbm_2g", -95, 0),
    "probeResponseReplyThreshold5g": ("probe_response_threshold_dbm_5g", -95, 0),
}
_BOOLEAN_FIELDS = {
    "probeResponseReplyThresholdEnable2g": "probe_response_threshold_enabled_2g",
    "probeResponseReplyThresholdEnable5g": "probe_response_threshold_enabled_5g",
}
_AIRTIME_FIELDS = {"enable2g": "airtime_fairness_enabled_2g",
                   "enable5g": "airtime_fairness_enabled_5g",
                   "enable6g": "airtime_fairness_enabled_6g"}


def _bounded_object(value: Any, limit: int) -> bool:
    return isinstance(value, dict) and len(value) <= limit


def project_site_beacon_control(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteBeaconControlError("response_invalid")
    missing = int("beaconControl" not in result) + int("airtimeFairness" not in result)
    invalid = 0
    known = {"beaconControl", "airtimeFairness"}
    unknown = len(set(result) - known)
    data: dict[str, object] = {}
    beacon = result.get("beaconControl")
    if "beaconControl" in result:
        if not _bounded_object(beacon, 32):
            invalid += 1
        else:
            unknown += len(set(beacon) - set(_BEACON_FIELDS) - set(_BOOLEAN_FIELDS))
            for field in ("dtimPeriod2g", "dtimPeriod5g", "dtimPeriod6g",
                          "rtsThreshold2g", "rtsThreshold5g", "rtsThreshold6g"):
                missing += int(field not in beacon)
            for field, (output, lower, upper) in _BEACON_FIELDS.items():
                if field not in beacon:
                    continue
                value = beacon[field]
                if type(value) is int and -(2 ** 31) <= value < 2 ** 31 and (lower is None or lower <= value <= upper):
                    data[output] = value
                else:
                    invalid += 1
            for field, output in _BOOLEAN_FIELDS.items():
                if field not in beacon:
                    continue
                if type(beacon[field]) is bool:
                    data[output] = beacon[field]
                else:
                    invalid += 1
    airtime = result.get("airtimeFairness")
    if "airtimeFairness" in result:
        if not _bounded_object(airtime, 4):
            invalid += 1
        else:
            unknown += len(set(airtime) - set(_AIRTIME_FIELDS))
            for field, output in _AIRTIME_FIELDS.items():
                if field not in airtime:
                    missing += 1
                elif type(airtime[field]) is bool:
                    data[output] = airtime[field]
                else:
                    invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
