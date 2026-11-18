"""Create and compare small local snapshots of selected safe configuration fields."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


SCHEMA_VERSION = 1
MAX_SECTIONS = 4
_REF = re.compile(r"[0-9a-f]{24}")
_LABEL = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
_ALIASES = {
    "radio_config": {"radio_2g", "radio_5g", "radio_5g1", "radio_5g2", "radio_6g"},
    "radio_fields": {"channel", "channelWidth", "freq", "txPower", "txPowerLevel", "radioEnable"},
    "ssid_fields": {"enabled", "guest_enabled", "broadcast_enabled", "band",
                     "vlan_enabled", "owe_enabled", "mlo_enabled", "fast_roaming_11r",
                     "security_mode", "pmf_mode", "auto_wan_access",
                     "security_configuration_present", "security_credentials_present",
                     "ap_group_binding_count", "network_binding_present"},
    "lan_fields": {"purpose", "purpose_label", "vlan_type", "vlan_type_label", "vlan",
                    "application", "application_label", "primary", "isolated_network",
                    "igmp_snooping", "mld_snooping", "portal_enabled",
                    "access_control_rule_enabled", "rate_limit_enabled",
                    "multi_vlan_summary", "dhcp"},
    "dns_fields": {"cache_enabled", "cache_ttl_seconds", "proxy_enabled", "proxy_mode",
                    "supports_dns_override", "dns_override_configured"},
}
_RADIO_BANDS = {"radioSetting2g": "radio_2g", "radioSetting5g": "radio_5g",
                "radioSetting5g1": "radio_5g1", "radioSetting5g2": "radio_5g2",
                "radioSetting6g": "radio_6g"}
_RADIO_FIELD_NAMES = {"channel": "channel", "channelWidth": "channel_width",
                      "freq": "frequency", "txPower": "tx_power",
                      "txPowerLevel": "tx_power_level", "radioEnable": "radio_enabled"}
_RADIO_OUTPUT_FIELDS = set(_RADIO_FIELD_NAMES.values())


class ConfigSnapshotError(ValueError):
    """Invalid selection, snapshot, or comparison input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _label(value: object, kind: str) -> str:
    if (not isinstance(value, str) or not _LABEL.fullmatch(value) or
            _REF.fullmatch(value)):
        raise ConfigSnapshotError(f"{kind}_label_invalid")
    return value


def _clean(value: object, *, depth: int = 0) -> object:
    if depth > 4:
        raise ConfigSnapshotError("snapshot_value_invalid")
    if value is None or type(value) in (bool, int, str):
        if isinstance(value, str) and (len(value) > 96 or any(ord(char) < 32 for char in value)):
            raise ConfigSnapshotError("snapshot_value_invalid")
        if type(value) is int and not -(2**31) <= value <= 2**31 - 1:
            raise ConfigSnapshotError("snapshot_value_invalid")
        return value
    if type(value) is float:
        import math
        if math.isfinite(value):
            return value
        raise ConfigSnapshotError("snapshot_value_invalid")
    if isinstance(value, list) and len(value) <= 32:
        return [_clean(item, depth=depth + 1) for item in value]
    if isinstance(value, dict) and len(value) <= 32:
        if not all(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key)
                   for key in value):
            raise ConfigSnapshotError("snapshot_value_invalid")
        return {key: _clean(item, depth=depth + 1) for key, item in sorted(value.items())}
    raise ConfigSnapshotError("snapshot_value_invalid")


def _data(value: object, resource: str) -> tuple[dict[str, object], bool]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            value.get("resource") != resource or not isinstance(value.get("data"), dict)):
        raise ConfigSnapshotError("snapshot_source_invalid")
    return value["data"], value.get("partial") is True


def _section(kind: str, label: str, response: object) -> dict[str, object]:
    resource = {"radio": "radio_config", "ssid": "ssid_configuration",
                "lan": "site_lan_network_detail_summary"}[kind]
    data, partial = _data(response, resource)
    if kind == "radio":
        clean: dict[str, object] = {}
        for source_band, output_band in _RADIO_BANDS.items():
            settings = data.get(source_band)
            if settings is None:
                continue
            if not isinstance(settings, dict):
                raise ConfigSnapshotError("snapshot_source_invalid")
            selected = {_RADIO_FIELD_NAMES[key]: _clean(settings[key])
                        for key in sorted(_RADIO_FIELD_NAMES) if key in settings}
            if selected:
                clean[output_band] = dict(sorted(selected.items()))
        clean = dict(sorted(clean.items()))
    elif kind == "ssid":
        clean = {key: _clean(data[key]) for key in sorted(_ALIASES["ssid_fields"])
                 if key in data}
        clean["network_binding_present"] = "network_binding_ref" in data
    else:
        clean = {key: _clean(data[key]) for key in sorted(_ALIASES["lan_fields"])
                 if key in data}
    return {"kind": kind, "label": label, "status": "observed",
            "partial": partial, "values": clean}


def build_snapshot(*, site_label: str, sections: list[dict[str, object]],
                   captured_at: str | None = None) -> dict[str, object]:
    site_label = _label(site_label, "site")
    if not isinstance(sections, list) or not 1 <= len(sections) <= MAX_SECTIONS:
        raise ConfigSnapshotError("snapshot_sections_invalid")
    keys: set[tuple[str, str]] = set()
    clean_sections = []
    for section in sections:
        if not isinstance(section, dict) or section.get("status") != "observed":
            raise ConfigSnapshotError("snapshot_section_invalid")
        kind, label = section.get("kind"), section.get("label")
        if not isinstance(kind, str) or kind not in {"radio", "ssid", "lan", "dns"}:
            raise ConfigSnapshotError("snapshot_section_invalid")
        label = _label(label, str(kind))
        key = (str(kind), label)
        if key in keys:
            raise ConfigSnapshotError("snapshot_section_duplicate")
        keys.add(key)
        values = section.get("values")
        if not isinstance(values, dict) or len(values) > 32:
            raise ConfigSnapshotError("snapshot_section_invalid")
        allowed = {"dns": _ALIASES["dns_fields"],
                   "ssid": _ALIASES["ssid_fields"],
                   "lan": _ALIASES["lan_fields"]}.get(kind)
        if kind == "radio":
            if set(values) - _ALIASES["radio_config"]:
                raise ConfigSnapshotError("snapshot_section_invalid")
            for radio in values.values():
                if not isinstance(radio, dict) or set(radio) - _RADIO_OUTPUT_FIELDS:
                    raise ConfigSnapshotError("snapshot_section_invalid")
        elif allowed is not None and set(values) - allowed:
            raise ConfigSnapshotError("snapshot_section_invalid")
        clean_sections.append({"kind": kind, "label": label,
                               "status": "observed", "partial": section.get("partial") is True,
                               "values": _clean(values)})
    clean_sections.sort(key=lambda item: (item["kind"], item["label"]))
    timestamp = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(timestamp, str) or len(timestamp) > 40:
        raise ConfigSnapshotError("snapshot_time_invalid")
    return {"schema_version": SCHEMA_VERSION, "resource": "omada_config_snapshot",
            "site_label": site_label, "captured_at": timestamp,
            "sections": clean_sections}


def project_capture(*, site_label: str, site_ref: str, client: Any,
                    ap_ref: str | None = None, ap_label: str | None = None,
                    ssid_ref: str | None = None, ssid_label: str | None = None,
                    network_ref: str | None = None, network_label: str | None = None) -> dict[str, object]:
    """Read selected settings through the existing client, then remove all raw references."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise ConfigSnapshotError("site_ref_invalid")
    selections = ((ap_ref, ap_label, "ap"), (ssid_ref, ssid_label, "ssid"),
                  (network_ref, network_label, "network"))
    for ref, label, kind in selections:
        if (ref is None) != (label is None):
            raise ConfigSnapshotError(f"{kind}_selection_invalid")
        if ref is not None and (not isinstance(ref, str) or not _REF.fullmatch(ref)):
            raise ConfigSnapshotError(f"{kind}_ref_invalid")
        if label is not None:
            _label(label, kind)

    sites = client.list_sites()
    if (not isinstance(sites, dict) or sites.get("status") != "ok" or
            not any(isinstance(row, dict) and row.get("site_ref") == site_ref
                    for row in sites.get("items", []))):
        raise ConfigSnapshotError("site_ref_unknown")
    sections: list[dict[str, object]] = []
    if ap_ref is not None:
        client.list_devices(site_ref)
        sections.append(_section("radio", str(ap_label),
                                 client.read_ap_radio_part(site_ref, ap_ref, "radio_config")))
    if ssid_ref is not None:
        client.list_ssids(site_ref)
        sections.append(_section("ssid", str(ssid_label),
                                 client.read_ssid_configuration(site_ref, ssid_ref)))
    if network_ref is not None:
        client.list_networks(site_ref)
        sections.append(_section("lan", str(network_label),
                                 client.read_site_lan_network_detail_summary(site_ref, network_ref)))
    # DNS settings are site-scoped. Their projections contain only documented
    # flags and mode codes; resolver addresses and names remain excluded.
    dns: dict[str, object] = {}
    partial = False
    cache, cache_partial = _data(client.read_dns_cache_settings(site_ref), "dns_cache_settings")
    proxy, proxy_partial = _data(client.read_dns_proxy_settings(site_ref), "dns_proxy_settings")
    partial = cache_partial or proxy_partial
    for source, target in (("enabled", "cache_enabled"), ("ttl_seconds", "cache_ttl_seconds")):
        if source in cache:
            dns[target] = _clean(cache[source])
    for source, target in (("enabled", "proxy_enabled"), ("mode", "proxy_mode"),
                           ("supports_dns_override", "supports_dns_override"),
                           ("dns_override_configured", "dns_override_configured")):
        if source in proxy:
            dns[target] = _clean(proxy[source])
    sections.append({"kind": "dns", "label": "site", "status": "observed",
                      "partial": partial, "values": dns})
    return build_snapshot(site_label=site_label, sections=sections)


def compare_snapshots(before: object, after: object) -> dict[str, object]:
    """Compare only fields observed in both compatible snapshots."""
    for value in (before, after):
        if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or
                value.get("schema_version") != SCHEMA_VERSION or
                value.get("resource") != "omada_config_snapshot" or
                not isinstance(value.get("site_label"), str) or
                not isinstance(value.get("captured_at"), str) or len(value["captured_at"]) > 40 or
                not isinstance(value.get("sections"), list) or
                not 1 <= len(value["sections"]) <= MAX_SECTIONS):
            raise ConfigSnapshotError("snapshot_invalid")
    _label(before["site_label"], "site")
    _label(after["site_label"], "site")
    if before["site_label"] != after["site_label"]:
        raise ConfigSnapshotError("snapshot_scope_mismatch")
    old = _snapshot_sections(before["sections"])
    new = _snapshot_sections(after["sections"])
    comparisons: list[dict[str, object]] = []
    for key in sorted(set(old) | set(new)):
        left, right = old.get(key), new.get(key)
        values_left = left.get("values", {}) if isinstance(left, dict) else {}
        values_right = right.get("values", {}) if isinstance(right, dict) else {}
        fields = []
        for field in sorted(set(values_left) | set(values_right)):
            known_left = isinstance(left, dict) and not left.get("partial") and field in values_left
            known_right = isinstance(right, dict) and not right.get("partial") and field in values_right
            if not (known_left and known_right):
                fields.append({"field": field, "status": "not_comparable"})
            else:
                status = "unchanged" if values_left[field] == values_right[field] else "changed"
                row: dict[str, object] = {"field": field, "status": status}
                if status == "changed":
                    row.update({"before": values_left[field], "after": values_right[field]})
                fields.append(row)
        comparisons.append({"kind": key[0], "label": key[1],
                            "status": "not_comparable" if left is None or right is None else "compared",
                            "fields": fields})
    return {"status": "ok", "resource": "omada_config_comparison",
            "schema_version": SCHEMA_VERSION,
            "site_label": before["site_label"],
            "before_captured_at": before["captured_at"],
            "after_captured_at": after["captured_at"],
            "sections": comparisons,
            "limitations": [
                "Only fields exposed by the connector's redacted read projections are compared.",
                "A partial source or missing field is not treated as an unchanged value.",
                "Section labels are supplied by the operator; the comparison cannot verify that the same controller object was selected twice.",
                "Names, addresses, secrets and raw controller references are omitted.",
            ]}


def _snapshot_sections(items: list[object]) -> dict[tuple[str, str], dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    for item in items:
        if (not isinstance(item, dict) or item.get("status") != "observed" or
                not isinstance(item.get("kind"), str) or
                item.get("kind") not in {"radio", "ssid", "lan", "dns"} or
                not isinstance(item.get("label"), str) or
                not isinstance(item.get("partial"), bool) or
                not isinstance(item.get("values"), dict)):
            raise ConfigSnapshotError("snapshot_invalid")
        kind, label = item["kind"], _label(item["label"], str(item["kind"]))
        key = (kind, label)
        if key in result:
            raise ConfigSnapshotError("snapshot_invalid")
        values = item["values"]
        allowed = {"radio": _ALIASES["radio_config"], "ssid": _ALIASES["ssid_fields"],
                   "lan": _ALIASES["lan_fields"], "dns": _ALIASES["dns_fields"]}[kind]
        if kind == "radio":
            if set(values) - allowed or any(not isinstance(row, dict) or
                    set(row) - _RADIO_OUTPUT_FIELDS for row in values.values()):
                raise ConfigSnapshotError("snapshot_invalid")
        elif set(values) - allowed:
            raise ConfigSnapshotError("snapshot_invalid")
        if not isinstance(_clean(values), dict):
            raise ConfigSnapshotError("snapshot_invalid")
        result[key] = item
    return result
