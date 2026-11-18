"""Bounded projection of site mesh settings without returning gateway IPs."""
from __future__ import annotations

import ipaddress
from typing import Any


class SiteMeshSummaryError(ValueError):
    """Raised when a mesh settings response exceeds its documented bounds."""


_FIELDS = {"meshEnable", "autoFailoverEnable", "defGatewayEnable", "gateway", "fullSector"}
_BOOLEAN_FIELDS = {
    "meshEnable": "mesh_enabled",
    "autoFailoverEnable": "auto_failover_enabled",
    "defGatewayEnable": "automatic_gateway_detection",
    "fullSector": "full_sector_dfs_enabled",
}


def project_site_mesh_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteMeshSummaryError("response_invalid")
    missing = int("mesh" not in result)
    invalid = 0
    unknown = len(set(result) - {"mesh"})
    data: dict[str, object] = {}
    mesh = result.get("mesh")
    if "mesh" in result:
        if not isinstance(mesh, dict) or len(mesh) > 16:
            invalid += 1
        else:
            missing += int("meshEnable" not in mesh)
            unknown += len(set(mesh) - _FIELDS)
            for field, output in _BOOLEAN_FIELDS.items():
                if field not in mesh:
                    continue
                value = mesh[field]
                if type(value) is bool:
                    data[output] = value
                else:
                    invalid += 1
            if "gateway" in mesh:
                gateway = mesh["gateway"]
                if isinstance(gateway, str):
                    try:
                        ipaddress.IPv4Address(gateway)
                    except ipaddress.AddressValueError:
                        invalid += 1
                    else:
                        data["custom_gateway_configured"] = True
                else:
                    invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
