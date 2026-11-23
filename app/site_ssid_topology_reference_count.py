"""Count opaque string references returned for a selected SSID topology."""
from __future__ import annotations
from collections.abc import Mapping

class SsidTopologyReferenceError(ValueError):
    pass

def count_ssid_topology_references(payload: object) -> dict[str, object]:
    # OpenAPI OperationResponseListString documents errorCode/msg/result.
    if (not isinstance(payload, Mapping) or set(payload) - {"errorCode", "msg", "result"} or
        type(payload.get("errorCode")) is not int or payload.get("errorCode") != 0 or
        not isinstance(payload.get("result"), list)):
        raise SsidTopologyReferenceError("envelope_invalid")
    values = payload["result"]
    if len(values) > 4_096 or any(not isinstance(value, str) or len(value) > 512 for value in values):
        raise SsidTopologyReferenceError("references_invalid")
    return {"reference_count": len(values), "partial": False,
            "reference_values_returned": False, "reference_semantics": "opaque_string"}
