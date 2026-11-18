"""Redacted projection of the documented AP antenna gain list."""
from __future__ import annotations


class ApAntennaGainError(ValueError):
    """The AP antenna gain result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_antenna_gain_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_RESULT_FIELDS = 8
_MAX_ITEM_FIELDS = 8
_MAX_KEY_LENGTH = 128
_MAX_ITEMS = 64
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_ap_antenna_gain(raw: object) -> dict[str, object]:
    """Project `anteGainList` without adding units or other interpretations.

    Valid list entries retain their documented numeric `radioId` and `anteGain`
    values. Duplicate radio IDs are preserved in the list and explicitly mark
    the projection partial; they are never collapsed into a map. Unknown names
    and values are discarded.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_RESULT_FIELDS:
        raise ApAntennaGainError()

    data: dict[str, list[dict[str, int]]] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown_field_count = 0
    invalid_item_count = 0
    duplicate_radio_id_count = 0

    if "anteGainList" not in raw:
        missing.append("anteGainList")
    else:
        rows = raw["anteGainList"]
        if not isinstance(rows, list):
            invalid.append("anteGainList")
        elif len(rows) > _MAX_ITEMS:
            raise ApAntennaGainError()
        else:
            projected: list[dict[str, int]] = []
            seen_radio_ids: set[int] = set()
            for item in rows:
                if not isinstance(item, dict):
                    invalid_item_count += 1
                    continue
                if len(item) > _MAX_ITEM_FIELDS:
                    raise ApAntennaGainError()

                row: dict[str, int] = {}
                for field, low, high in (("radioId", 0, 3), ("anteGain", 0, 30)):
                    if field not in item:
                        missing.append(f"anteGainList[].{field}")
                        continue
                    value = item[field]
                    if _int32(value) and low <= value <= high:
                        row[field] = value
                    else:
                        invalid.append(f"anteGainList[].{field}")

                extras = 0
                for key in item:
                    if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                        raise ApAntennaGainError()
                    if key not in {"radioId", "anteGain"}:
                        extras += 1
                unknown_field_count += extras
                radio_id = row.get("radioId")
                if radio_id is not None:
                    if radio_id in seen_radio_ids:
                        duplicate_radio_id_count += 1
                    else:
                        seen_radio_ids.add(radio_id)
                projected.append(row)
            data["anteGainList"] = projected

    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApAntennaGainError()
        if key != "anteGainList":
            unknown_field_count += 1

    if invalid_item_count:
        invalid.append("anteGainList[].item")

    return {
        "status": "ok",
        "resource": "ap_antenna_gain",
        "data": data,
        "partial": bool(missing or invalid or unknown_field_count or duplicate_radio_id_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_field_count,
        "invalid_item_count": invalid_item_count,
        "duplicate_radio_id_count": duplicate_radio_id_count,
    }
