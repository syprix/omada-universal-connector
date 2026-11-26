"""Project only the documented firmware-pool channel quantities."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerFirmwarePoolCountsError(ValueError):
    pass


_CHANNELS = {"0": "stable", "1": "release_candidate", "2": "beta"}
_INT32_MAX = (1 << 31) - 1


def project_firmware_pool_channel_counts(value: object) -> dict[str, object]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping) or len(value) > 16:
        raise ControllerFirmwarePoolCountsError("map_invalid")

    counts: dict[str, int | None] = {label: None for label in _CHANNELS.values()}
    reported = invalid = unknown = 0
    for key, count in value.items():
        label = _CHANNELS.get(key) if isinstance(key, str) else None
        if label is None:
            unknown += 1
            continue
        reported += 1
        if type(count) is not int or not 0 <= count <= _INT32_MAX:
            invalid += 1
            continue
        counts[label] = count

    # Reported means a documented channel key was present, whether its value
    # was valid or not. Missing is reserved for documented keys not in the map.
    missing = len(_CHANNELS) - reported
    return {
        "channel_counts": counts,
        "reported_count": reported,
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_key_count": unknown,
        "partial": bool(missing or invalid or unknown),
        "firmware_details_returned": False,
        "installed_firmware_or_upgrade_state_inferred": False,
    }
