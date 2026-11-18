"""Offline, privacy-preserving interpretation of imported DNS observations."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

MAX_WINDOW_MS = 86_400_000
MAX_SAMPLES = 10_000
_DNS_FIELDS = {
    "cache_enabled", "cache_ttl_seconds", "proxy_enabled", "proxy_mode",
    "supports_dns_override", "dns_override_configured",
}
_PROXY_MODES = {"dnssec", "doh", "dot", "dns_override"}
_OBSERVATIONS = {
    "dns": ({"resolved", "failed"}, {"dns_resolution_check", "diagnostic_export"}),
    "local_reachability": ({"reachable", "unreachable"},
                            {"reachability_check", "diagnostic_export"}),
    "ipv4": ({"available", "unavailable"}, {"interface_status", "diagnostic_export"}),
    "ipv6": ({"available", "unavailable"}, {"interface_status", "diagnostic_export"}),
}
_WIFI_SOURCES = {"system_log", "diagnostic_export"}


class DnsIncidentDiagnosisError(ValueError):
    """Invalid diagnosis window or imported evidence."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _snapshot_context(snapshot: object, start_ms: int, end_ms: int) -> dict[str, object]:
    if (not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != 1 or
            type(snapshot.get("schema_version")) is not int or
            snapshot.get("resource") != "omada_config_snapshot" or
            not isinstance(snapshot.get("captured_at"), str) or
            not isinstance(snapshot.get("sections"), list) or
            len(snapshot["sections"]) > 4):
        raise DnsIncidentDiagnosisError("snapshot_invalid")
    try:
        captured = datetime.fromisoformat(snapshot["captured_at"].replace("Z", "+00:00"))
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise ValueError
        captured_ms = int(captured.timestamp() * 1000)
    except (ValueError, OverflowError, OSError):
        raise DnsIncidentDiagnosisError("snapshot_time_invalid") from None
    dns_sections = [item for item in snapshot["sections"]
                    if isinstance(item, Mapping) and item.get("kind") == "dns" and
                    item.get("label") == "site"]
    if len(dns_sections) > 1:
        raise DnsIncidentDiagnosisError("snapshot_invalid")
    values: dict[str, object] = {}
    partial = True
    if dns_sections:
        section = dns_sections[0]
        raw = section.get("values")
        if (section.get("status") != "observed" or type(section.get("partial")) is not bool or
                not isinstance(raw, Mapping) or set(raw) - _DNS_FIELDS):
            raise DnsIncidentDiagnosisError("snapshot_invalid")
        partial = section["partial"]
        for key, value in raw.items():
            if key in {"cache_enabled", "proxy_enabled", "supports_dns_override",
                       "dns_override_configured"} and type(value) is bool:
                values[key] = value
            elif key == "cache_ttl_seconds" and type(value) is int and 1 <= value <= 86400:
                values[key] = value
            elif key == "proxy_mode" and value in _PROXY_MODES:
                values[key] = value
            else:
                raise DnsIncidentDiagnosisError("snapshot_invalid")
    relation = ("before_window" if captured_ms < start_ms else
                "after_window" if captured_ms > end_ms else "within_window")
    return {
        "status": "observed" if dns_sections and values and not partial else
                  "partial" if dns_sections else "unknown",
        "captured_at": snapshot["captured_at"],
        "capture_relation_to_window": relation,
        "values": values,
        "missing_field_count": len(_DNS_FIELDS - set(values)),
        "network_scope": "site_wide",
        "partial": not dns_sections or partial or set(values) != _DNS_FIELDS,
    }


def _network_context(summary: object) -> dict[str, object]:
    if summary is None:
        return {"status": "unknown", "network_specific_mapping": "unknown",
                "device_to_network_association": "not_available", "partial": True}
    if (not isinstance(summary, Mapping) or summary.get("resource") != "ssid_network_summary" or
            summary.get("status") not in {"ok", "partial"}):
        raise DnsIncidentDiagnosisError("network_summary_invalid")
    checks = summary.get("network_checks")
    dns = checks.get("dns") if isinstance(checks, Mapping) else None
    if not isinstance(checks, Mapping) or not isinstance(dns, Mapping):
        raise DnsIncidentDiagnosisError("network_summary_invalid")
    mapping = dns.get("network_specific_mapping")
    if mapping not in {"unknown", "observed", "partial", "unavailable"}:
        mapping = "unknown"
    return {
        "status": summary["status"],
        "network_count": summary.get("network_count")
        if type(summary.get("network_count")) is int else None,
        "ssid_count": summary.get("ssid_count")
        if type(summary.get("ssid_count")) is int else None,
        "ssid_network_binding_count": summary.get("matched_count")
        if type(summary.get("matched_count")) is int else None,
        "network_specific_mapping": mapping,
        "device_to_network_association": "unknown_without_imported_network_reference",
        "partial": summary.get("partial") is not False,
    }


def diagnose_dns_incident(measurements: object, *, start_ms: int, end_ms: int,
                          snapshot: object | None = None,
                          network_summary: object | None = None,
                          include_observations: bool = False) -> dict[str, object]:
    """Summarize only source-labeled imported observations and optional saved context."""
    if (type(start_ms) is not int or type(end_ms) is not int or start_ms < 0 or
            end_ms < start_ms or end_ms - start_ms > MAX_WINDOW_MS):
        raise DnsIncidentDiagnosisError("time_window_invalid")
    if type(include_observations) is not bool:
        raise DnsIncidentDiagnosisError("detail_option_invalid")
    if (not isinstance(measurements, Mapping) or
            measurements.get("resource") != "device_measurements" or
            measurements.get("schema_version") != 1 or
            type(measurements.get("schema_version")) is not int or
            not isinstance(measurements.get("observations"), list) or
            len(measurements["observations"]) > MAX_SAMPLES):
        raise DnsIncidentDiagnosisError("measurements_invalid")

    selected: list[dict[str, object]] = []
    wifi_disconnected = dns_failed = dns_resolved = dns_missing = 0
    failed_with_local_reachable = failed_with_local_unreachable = 0
    failed_with_wifi_disconnected = resolved_with_local_unreachable = 0
    ipv4_unavailable = ipv6_unavailable = 0
    for row in measurements["observations"]:
        if not isinstance(row, Mapping):
            raise DnsIncidentDiagnosisError("measurements_invalid")
        timestamp = row.get("timestamp_ms")
        timestamp_utc = row.get("timestamp_utc")
        wifi, dns, local = row.get("wifi"), row.get("dns"), row.get("local_reachability")
        if (type(timestamp) is not int or timestamp < 0 or not isinstance(wifi, Mapping) or
                type(wifi.get("connected")) is not bool or
                wifi.get("source_kind") not in _WIFI_SOURCES or
                not isinstance(timestamp_utc, str) or len(timestamp_utc) > 40):
            raise DnsIncidentDiagnosisError("measurements_invalid")
        try:
            parsed_time = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
            if (parsed_time.tzinfo is None or parsed_time.utcoffset() is None or
                    int(parsed_time.timestamp() * 1000) != timestamp):
                raise ValueError
        except (ValueError, OverflowError, OSError):
            raise DnsIncidentDiagnosisError("measurements_invalid") from None
        if not start_ms <= timestamp <= end_ms:
            continue
        if not wifi["connected"]:
            wifi_disconnected += 1
        dns_status = dns.get("status") if isinstance(dns, Mapping) else None
        local_status = local.get("status") if isinstance(local, Mapping) else None
        if dns_status is None:
            dns_missing += 1
        elif dns_status == "failed":
            dns_failed += 1
            if local_status == "reachable":
                failed_with_local_reachable += 1
            elif local_status == "unreachable":
                failed_with_local_unreachable += 1
            if not wifi["connected"]:
                failed_with_wifi_disconnected += 1
        elif dns_status == "resolved":
            dns_resolved += 1
            if local_status == "unreachable":
                resolved_with_local_unreachable += 1
        else:
            raise DnsIncidentDiagnosisError("measurements_invalid")
        ipv4 = row.get("ipv4")
        ipv6 = row.get("ipv6")
        if isinstance(ipv4, Mapping) and ipv4.get("status") == "unavailable":
            ipv4_unavailable += 1
        if isinstance(ipv6, Mapping) and ipv6.get("status") == "unavailable":
            ipv6_unavailable += 1
        projected: dict[str, object] = {
            "timestamp_utc": timestamp_utc,
            "wifi_connected": wifi["connected"],
        }
        for key, value in (("dns", dns), ("local_reachability", local),
                           ("ipv4", ipv4), ("ipv6", ipv6)):
            if isinstance(value, Mapping):
                statuses, sources = _OBSERVATIONS[key]
                if value.get("status") not in statuses or value.get("source_kind") not in sources:
                    raise DnsIncidentDiagnosisError("measurements_invalid")
                projected[key] = {"status": value["status"],
                                  "source_kind": value["source_kind"],
                                  "verification": "imported_unverified"}
        selected.append(projected)

    if snapshot is None:
        dns_config = {"status": "unknown", "capture_relation_to_window": "unknown",
                      "values": {}, "missing_field_count": len(_DNS_FIELDS),
                      "network_scope": "site_wide", "partial": True}
    else:
        dns_config = _snapshot_context(snapshot, start_ms, end_ms)
    network = _network_context(network_summary)
    dns_observed = dns_failed + dns_resolved
    findings = []
    if dns_failed:
        findings.append({"kind": "imported_dns_failures", "count": dns_failed,
                         "verification": "declared_source_not_independently_verified"})
    if failed_with_local_reachable:
        findings.append({"kind": "dns_failure_with_local_reachability",
                         "count": failed_with_local_reachable,
                         "meaning": "separate_checks_disagree_on_reachability_scope"})
    if failed_with_local_unreachable:
        findings.append({"kind": "dns_failure_with_local_unreachable",
                         "count": failed_with_local_unreachable,
                         "meaning": "network_and_dns_failures_cooccur; cause_unknown"})
    if resolved_with_local_unreachable:
        findings.append({"kind": "dns_resolved_with_local_unreachable",
                         "count": resolved_with_local_unreachable,
                         "meaning": "separate_checks_report_different_reachability"})
    missing_evidence = []
    if dns_missing or not selected:
        missing_evidence.append("device_dns_observations")
    if dns_config["status"] == "unknown":
        missing_evidence.append("site_dns_configuration_snapshot")
    if network["status"] == "unknown":
        missing_evidence.append("ssid_network_mapping_summary")
    report = {
        "status": "ok", "resource": "dns_incident_diagnosis",
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "summary": {
            "sample_count": len(selected), "wifi_disconnected_count": wifi_disconnected,
            "dns_sample_count": dns_observed, "dns_failed_count": dns_failed,
            "dns_resolved_count": dns_resolved, "dns_missing_count": dns_missing,
            "dns_failure_with_local_reachable_count": failed_with_local_reachable,
            "dns_failure_with_local_unreachable_count": failed_with_local_unreachable,
            "dns_failure_with_wifi_disconnected_count": failed_with_wifi_disconnected,
            "dns_resolved_with_local_unreachable_count": resolved_with_local_unreachable,
            "ipv4_unavailable_count": ipv4_unavailable,
            "ipv6_unavailable_count": ipv6_unavailable,
        },
        "dns_configuration": dns_config,
        "network_context": network,
        "findings": findings,
        "missing_evidence": missing_evidence,
        "cause": "undetermined",
        "observation_detail": "included" if include_observations else "aggregated_only",
        "limitations": [
            "Imported device observations carry declared source labels and are not independently verified.",
            "Site DNS settings do not identify the resolver used by an imported device sample.",
            "The available network summary cannot bind these observations to one network.",
            "No DNS lookup, address probe, controller write, or configuration change is performed.",
        ],
        "partial": (not selected or dns_missing > 0 or dns_config["partial"] is True or
                    network["partial"] is True),
    }
    if include_observations:
        report["observations"] = selected
    return report
