"""Redacted counts for site Wi-Fi calling profile configuration."""
from __future__ import annotations


class WifiCallingProfilesError(ValueError):
    """Invalid or unsafe profile response."""


_MAX_PROFILES = 1_000
_MAX_CARRIERS_PER_PROFILE = 1_000
_MAX_EPDGS_PER_CARRIER = 1_000


def project_site_wifi_calling_profiles_summary(raw: object) -> dict[str, object]:
    if not isinstance(raw, list) or len(raw) > _MAX_PROFILES:
        raise WifiCallingProfilesError("profile_list_invalid")
    carriers = epdgs = domain_endpoints = ip_endpoints = 0
    priorities: dict[str, int] = {}
    epdg_types = {"domain": 0, "ip": 0, "unknown": 0}
    resources: dict[str, int] = {}
    redacted = unknown = invalid = 0
    for profile in raw:
        if not isinstance(profile, dict):
            raise WifiCallingProfilesError("profile_invalid")
        redacted += sum(key in profile and profile[key] is not None
                        for key in ("id", "name", "description"))
        unknown += sum(key not in {"id", "name", "description", "carrierList", "resource"}
                       for key in profile)
        resource = profile.get("resource")
        if resource is not None:
            if type(resource) is not int or resource not in (0, 1, 2):
                invalid += 1
            else:
                key = str(resource)
                resources[key] = resources.get(key, 0) + 1
        if "carrierList" not in profile:
            unknown += 1
            continue
        carrier_rows = profile["carrierList"]
        if carrier_rows is None:
            unknown += 1
            continue
        if not isinstance(carrier_rows, list) or len(carrier_rows) > _MAX_CARRIERS_PER_PROFILE:
            invalid += 1
            continue
        carriers += len(carrier_rows)
        for carrier in carrier_rows:
            if not isinstance(carrier, dict):
                invalid += 1
                continue
            redacted += int("carrierName" in carrier and carrier["carrierName"] is not None)
            unknown += sum(key not in {"carrierName", "epdgs"} for key in carrier)
            if "epdgs" not in carrier or carrier["epdgs"] is None:
                unknown += 1
                continue
            endpoints = carrier["epdgs"]
            if not isinstance(endpoints, list) or len(endpoints) > _MAX_EPDGS_PER_CARRIER:
                invalid += 1
                continue
            epdgs += len(endpoints)
            for endpoint in endpoints:
                if not isinstance(endpoint, dict):
                    invalid += 1
                    continue
                redacted += sum(key in endpoint and endpoint[key] is not None
                                for key in ("domain", "ip"))
                unknown += sum(key not in {"qosPriority", "type", "domain", "ip"}
                               for key in endpoint)
                kind = endpoint.get("type")
                if kind is None:
                    epdg_types["unknown"] += 1
                    unknown += 1
                elif type(kind) is not int or kind not in (0, 1):
                    invalid += 1
                    epdg_types["unknown"] += 1
                else:
                    epdg_types["domain" if kind == 0 else "ip"] += 1
                    value_key = "domain" if kind == 0 else "ip"
                    value = endpoint.get(value_key)
                    if value is not None:
                        if not isinstance(value, str) or len(value) > 253 or any(ord(c) < 32 for c in value):
                            invalid += 1
                        elif value:
                            if kind == 0:
                                domain_endpoints += 1
                            else:
                                ip_endpoints += 1
                priority = endpoint.get("qosPriority")
                if priority is not None:
                    if type(priority) is not int or not 0 <= priority <= 2_147_483_647:
                        invalid += 1
                    else:
                        key = str(priority)
                        priorities[key] = priorities.get(key, 0) + 1
    return {
        "profile_count": len(raw),
        "carrier_count": carriers,
        "epdg_count": epdgs,
        "epdg_type_counts": epdg_types,
        "domain_endpoint_count": domain_endpoints,
        "ip_endpoint_count": ip_endpoints,
        "qos_priority_counts": priorities,
        "profile_resource_counts": resources,
        "partial": bool(unknown or invalid),
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
    }
