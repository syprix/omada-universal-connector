"""Redacted inventory coverage for documented Gateway QoS service references."""
from __future__ import annotations

from collections import Counter
from typing import Any

MAX_SERVICE_REFERENCES = 1_000
MAX_ROW_FIELDS = 16
MAX_REFERENCE_TEXT_LENGTH = 256


class GatewayQosServiceReferenceInventoryError(ValueError):
    """Raised when the service-reference response exceeds safe bounds."""


def _valid_text(value: Any, *, allow_empty: bool) -> bool:
    if not isinstance(value, str) or len(value) > MAX_REFERENCE_TEXT_LENGTH:
        return False
    if not allow_empty and not value.strip():
        return False
    return not any(ord(char) < 32 or ord(char) == 127 for char in value)


def project_gateway_qos_service_reference_inventory(result: Any) -> dict[str, object]:
    """Count documented id/name coverage in one unpaginated result.data list.

    The source contract describes string IDs and names but gives no list total,
    required-field declaration, or pagination metadata. This projection does
    not claim server-side completeness or use references to inspect profiles.
    """
    if (not isinstance(result, dict) or set(result) != {"data"} or
            not isinstance(result.get("data"), list) or
            len(result["data"]) > MAX_SERVICE_REFERENCES):
        raise GatewayQosServiceReferenceInventoryError("response_invalid")

    rows = result["data"]
    id_present = id_missing = id_invalid = id_valid = 0
    name_present = name_missing = name_invalid = name_valid = 0
    invalid_row_count = unknown_field_count = 0
    valid_ids: list[str] = []

    for row in rows:
        if not isinstance(row, dict) or len(row) > MAX_ROW_FIELDS:
            invalid_row_count += 1
            continue

        unknown_field_count += len(set(row) - {"id", "name"})

        if "id" not in row:
            id_missing += 1
        else:
            id_present += 1
            if _valid_text(row["id"], allow_empty=False):
                id_valid += 1
                valid_ids.append(row["id"])
            else:
                id_invalid += 1

        if "name" not in row:
            name_missing += 1
        else:
            name_present += 1
            if _valid_text(row["name"], allow_empty=True):
                name_valid += 1
            else:
                name_invalid += 1

    frequencies = Counter(valid_ids)
    duplicate_reference_count = sum(count - 1 for count in frequencies.values()
                                    if count > 1)
    unique_reference_count = len(frequencies)
    empty = not rows
    partial = bool(
        invalid_row_count or id_missing or id_invalid or duplicate_reference_count or
        name_missing or name_invalid or unknown_field_count)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_gateway_qos_service_reference_inventory",
        "partial": partial,
        "source_scope": "single_unpaginated_response",
        "server_completeness_established": False,
        "row_count": len(rows),
        "empty": empty,
        "invalid_row_count": invalid_row_count,
        "id_present_count": id_present,
        "id_missing_count": id_missing,
        "id_invalid_count": id_invalid,
        "id_valid_count": id_valid,
        "id_unique_count": unique_reference_count,
        "duplicate_reference_count": duplicate_reference_count,
        "name_present_count": name_present,
        "name_missing_count": name_missing,
        "name_invalid_count": name_invalid,
        "name_valid_count": name_valid,
        "unknown_field_count": unknown_field_count,
    }
