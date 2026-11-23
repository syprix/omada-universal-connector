"""Count uploaded firmware metadata coverage without exposing file details."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerFirmwareInventoryError(ValueError):
    pass


_ROW_FIELDS = frozenset(("id", "name", "modelTypeInfo", "uploadTime", "description"))


def summarize_firmware_inventory(rows: object, total: object,
                                 pages_fetched: int, page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or type(total) is not int or
            total < len(rows) or not 0 <= total < (1 << 63) or
            type(pages_fetched) is not int or not 0 <= pages_fetched <= 10 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise ControllerFirmwareInventoryError("input_invalid")

    coverage = {
        "identifier_reported_count": 0,
        "file_name_reported_count": 0,
        "model_information_reported_count": 0,
        "display_model_reported_count": 0,
        "backend_model_reported_count": 0,
        "upload_time_reported_count": 0,
        "description_reported_count": 0,
    }
    invalid_rows = invalid_fields = unknown_fields = 0
    partial = len(rows) < total

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            invalid_rows += 1
            partial = True
            continue
        unknown_fields += sum(key not in _ROW_FIELDS for key in row)
        partial |= any(key not in _ROW_FIELDS for key in row)

        for source, output in (("id", "identifier_reported_count"),
                               ("name", "file_name_reported_count"),
                               ("description", "description_reported_count")):
            value = row.get(source)
            if value is None:
                continue
            if isinstance(value, str):
                coverage[output] += 1
            else:
                invalid_fields += 1
                partial = True

        model = row.get("modelTypeInfo")
        if model is not None:
            if not isinstance(model, Mapping) or len(model) > 8:
                invalid_fields += 1
                partial = True
            else:
                coverage["model_information_reported_count"] += 1
                unknown_fields += sum(key not in {"showModel", "compoundModel"}
                                      for key in model)
                partial |= any(key not in {"showModel", "compoundModel"} for key in model)
                for source, output in (("showModel", "display_model_reported_count"),
                                       ("compoundModel", "backend_model_reported_count")):
                    value = model.get(source)
                    if value is None:
                        continue
                    if isinstance(value, str):
                        coverage[output] += 1
                    else:
                        invalid_fields += 1
                        partial = True

        uploaded = row.get("uploadTime")
        if uploaded is not None:
            if type(uploaded) is int and 0 <= uploaded < (1 << 63):
                coverage["upload_time_reported_count"] += 1
            else:
                invalid_fields += 1
                partial = True

    return {
        "firmware_entry_count": len(rows),
        "reported_total_count": total,
        "coverage_complete": len(rows) >= total,
        "metadata_field_coverage": coverage,
        "pages_fetched": pages_fetched,
        "page_limit": page_limit,
        "truncated": len(rows) < total,
        "invalid_record_count": invalid_rows,
        "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown_fields,
        "partial": bool(partial or invalid_rows or invalid_fields or unknown_fields or
                         any(count < len(rows) for count in coverage.values())),
        "firmware_suitability_or_device_compatibility_inferred": False,
        "identifiers_names_descriptions_and_timestamps_returned": False,
    }
