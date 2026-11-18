"""Validated DHCP snooping status projection."""

from __future__ import annotations

from collections.abc import Mapping


class SiteDhcpSnoopingStatusError(ValueError):
    """The controller returned an invalid DHCP snooping status response."""


def project_site_dhcp_snooping_status(result: object) -> dict[str, object]:
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteDhcpSnoopingStatusError("result must be a bounded object")
    missing = invalid = unknown = 0
    enabled: bool | None = None
    if "dhcpSnoopEnable" not in result:
        missing += 1
    elif isinstance(result["dhcpSnoopEnable"], bool):
        enabled = result["dhcpSnoopEnable"]
    else:
        invalid += 1
    unknown += sum(key != "dhcpSnoopEnable" for key in result)
    return {
        "data": {"dhcp_snooping_enabled": enabled},
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
