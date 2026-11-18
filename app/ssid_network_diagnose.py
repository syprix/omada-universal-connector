"""Bounded, read-only reconciliation of SSID network bindings."""
from __future__ import annotations

import re
from typing import Callable


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_SSID_DETAILS = 64
_MAX_SITE_ITEMS = 10000


class SsidNetworkDiagnoseError(ValueError):
    """Invalid caller input or unsafe inventory response."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _inventory(value: object, *, resource: str, ref_key: str,
               site_ref: str) -> list[str]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            value.get("resource") != resource or value.get("site_ref", site_ref) != site_ref):
        raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
    items, count = value.get("items"), value.get("count")
    if (not isinstance(items, list) or len(items) > _MAX_SITE_ITEMS or
            type(count) is not int or count != len(items)):
        raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
    refs: list[str] = []
    for item in items:
        ref = item.get(ref_key) if isinstance(item, dict) else None
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
        refs.append(ref)
    if len(set(refs)) != len(refs):
        raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
    return refs


def run_site(site_ref: str, requester: Callable[[str], object]) -> dict[str, object]:
    """Compare a bounded set of site SSID config refs with current networks."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise SsidNetworkDiagnoseError("site_ref_invalid")
    if not callable(requester):
        raise SsidNetworkDiagnoseError("connector_unavailable")

    try:
        sites = requester("/v1/sites")
    except Exception:
        raise SsidNetworkDiagnoseError("site_inventory_unavailable") from None
    if (not isinstance(sites, dict) or sites.get("status") != "ok" or
            sites.get("resource") != "sites"):
        raise SsidNetworkDiagnoseError("site_inventory_invalid")
    site_items, site_count = sites.get("items"), sites.get("count")
    if (not isinstance(site_items, list) or len(site_items) > _MAX_SITE_ITEMS or
            type(site_count) is not int or site_count != len(site_items) or
            any(not isinstance(row, dict) or not isinstance(row.get("site_ref"), str) or
                not _REF.fullmatch(row["site_ref"]) for row in site_items)):
        raise SsidNetworkDiagnoseError("site_inventory_invalid")
    if site_ref not in {row["site_ref"] for row in site_items}:
        raise SsidNetworkDiagnoseError("site_ref_unknown")

    root = f"/v1/sites/{site_ref}"
    try:
        ssid_result = requester(root + "/ssids")
    except Exception:
        raise SsidNetworkDiagnoseError("ssid_inventory_unavailable") from None
    ssid_refs = _inventory(ssid_result, resource="ssids", ref_key="ssid_ref", site_ref=site_ref)
    try:
        network_result = requester(root + "/networks")
    except Exception:
        raise SsidNetworkDiagnoseError("network_inventory_unavailable") from None
    network_refs = set(_inventory(
        network_result, resource="networks", ref_key="network_ref", site_ref=site_ref))

    inspected = min(len(ssid_refs), _MAX_SSID_DETAILS)
    matched = unbound = stale = unreadable = 0
    for ssid_ref in ssid_refs[:inspected]:
        try:
            detail = requester(f"{root}/ssids/{ssid_ref}")
        except Exception:
            unreadable += 1
            continue
        data = detail.get("data") if isinstance(detail, dict) else None
        binding = data.get("network_binding_ref") if isinstance(data, dict) else None
        if (not isinstance(detail, dict) or detail.get("status") != "ok" or
                detail.get("resource") != "ssid_configuration" or
                detail.get("site_ref", site_ref) != site_ref or
                not isinstance(data, dict) or data.get("ssid_ref") != ssid_ref):
            unreadable += 1
            continue
        if binding is None:
            unbound += 1
        elif not isinstance(binding, str) or not _REF.fullmatch(binding):
            unreadable += 1
        elif binding in network_refs:
            matched += 1
        else:
            stale += 1

    omitted = len(ssid_refs) - inspected
    return {
        "status": "ok",
        "resource": "ssid_network_summary",
        "site_ref": site_ref,
        "ssid_count": len(ssid_refs),
        "network_count": len(network_refs),
        "inspected_count": inspected,
        "matched_count": matched,
        "unbound_count": unbound,
        "stale_binding_count": stale,
        "unreadable_count": unreadable,
        "omitted_count": omitted,
        "partial": bool(omitted or unreadable),
    }
