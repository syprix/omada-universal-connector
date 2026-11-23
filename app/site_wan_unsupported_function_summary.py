"""Redacted count of documented DS-Lite/MAP-E limitation entries."""
from __future__ import annotations

from collections.abc import Mapping


MAX_FUNCTION_ENTRIES = 1_000


def summarize_wan_unsupported_functions(response: object) -> dict[str, object]:
    """Count source-reported entries without returning or interpreting their text."""
    if not isinstance(response, Mapping):
        return {"result_state": "invalid", "invalid_reason": "response_not_object",
                "reported_limitation_entry_count": None, "truncated": False}
    if "result" not in response:
        return {"result_state": "missing", "missing_field": "result",
                "reported_limitation_entry_count": None, "truncated": False}
    result = response["result"]
    if not isinstance(result, Mapping):
        return {"result_state": "invalid", "invalid_reason": "result_not_object",
                "reported_limitation_entry_count": None, "truncated": False}
    if "functions" not in result:
        return {"result_state": "missing", "missing_field": "functions",
                "reported_limitation_entry_count": None, "truncated": False}
    functions = result["functions"]
    if not isinstance(functions, list):
        return {"result_state": "invalid", "invalid_reason": "functions_not_array",
                "reported_limitation_entry_count": None, "truncated": False}
    truncated = len(functions) > MAX_FUNCTION_ENTRIES
    bounded = functions[:MAX_FUNCTION_ENTRIES]
    if any(not isinstance(value, str) for value in bounded):
        return {"result_state": "invalid", "invalid_reason": "function_entry_not_string",
                "reported_limitation_entry_count": None, "truncated": truncated}
    return {
        "result_state": "truncated" if truncated else "empty" if not bounded else "ok",
        "reported_limitation_entry_count": len(bounded),
        "truncated": truncated,
    }
