"""Bounded, redacted references for gateway models offered for pre-configuration."""
from __future__ import annotations

from collections import Counter
from typing import Any

MAX_MODEL_ROWS = 100
MAX_MODEL_NAME_LENGTH = 128
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
_ROW_FIELDS = {"id", "name"}


class SiteGatewaySupportedModelReferencesError(ValueError):
    """Raised when the documented model reference list exceeds safe bounds."""


def project_site_gateway_supported_model_references(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteGatewaySupportedModelReferencesError("response_invalid")
    unknown_root_count = len(set(result) - {"supportModels"})
    if "supportModels" not in result:
        return {"data": {"model_references": [], "model_reference_count": 0,
                         "source_list_present": False, "missing_field_count": 1,
                         "invalid_row_count": 0, "duplicate_model_id_count": 0,
                         "unknown_field_count": unknown_root_count},
                "partial": True}
    rows = result["supportModels"]
    if not isinstance(rows, list) or len(rows) > MAX_MODEL_ROWS:
        raise SiteGatewaySupportedModelReferencesError("model_rows_invalid")
    candidates: list[tuple[int, str]] = []
    invalid_row_count = 0
    unknown_field_count = unknown_root_count
    for row in rows:
        if not isinstance(row, dict) or len(row) > 8:
            invalid_row_count += 1
            continue
        unknown_field_count += len(set(row) - _ROW_FIELDS)
        model_id = row.get("id")
        name = row.get("name")
        if (type(model_id) is not int or not INT32_MIN <= model_id <= INT32_MAX or
                not isinstance(name, str) or len(name) > MAX_MODEL_NAME_LENGTH or
                any(not character.isprintable() for character in name)):
            invalid_row_count += 1
            continue
        candidates.append((model_id, name))
    frequencies = Counter(model_id for model_id, _ in candidates)
    duplicate_model_id_count = sum(count > 1 for count in frequencies.values())
    model_references = [
        {"model_id": model_id, "model_name": name}
        for model_id, name in dict.fromkeys(candidates)
        if frequencies[model_id] == 1
    ]
    data = {
        "model_references": model_references,
        "model_reference_count": len(model_references),
        "source_list_present": True,
        "model_row_count": len(rows),
        "missing_field_count": 0,
        "invalid_row_count": invalid_row_count,
        "duplicate_model_id_count": duplicate_model_id_count,
        "unknown_field_count": unknown_field_count,
    }
    return {"data": data,
            "partial": bool(invalid_row_count or duplicate_model_id_count or
                            unknown_field_count)}
