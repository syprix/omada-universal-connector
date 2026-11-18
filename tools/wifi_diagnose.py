#!/usr/bin/env python3
"""Read-only, privacy-limited WLAN diagnostics from a local connector."""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import math
import os
import re
import stat
import sys
from urllib.parse import urlsplit
from typing import Callable


DEFAULT_BASE_URL = "http://127.0.0.1:18080"
REQUEST_TIMEOUT_SECONDS = 2.0
MAX_RESPONSE_BYTES = 256 * 1024
MAX_TOKEN_FILE_BYTES = 4096
SITE_REF_PATTERN = re.compile(r"[0-9a-f]{24}\Z")
TOKEN_PATTERN = re.compile(rb"[\x21-\x7e]{32,4096}\Z")
_WINDOW_KEYS = frozenset({"start_ms", "end_ms"})
_HEALTH_COUNT_KEYS = frozenset({
    "received_points", "examined_points", "unexamined_points", "outside_window_points",
    "duplicate_timestamp_points", "truncated_points", "returned_points", "unknown_fields",
})
_WIFI_DETAILS = frozenset({
    "accessTimeScoreDetail", "channelUtilScoreDetail", "accessCapacityScoreDetail",
    "rssiScoreDetail", "channelInterUtilDetail", "wirelessClientQualityDetail",
})
_DETAIL_LISTS = frozenset({"scores", "assocTime", "authTime", "dhcpTime", "dnsTime"})
_SIGNAL_CATEGORIES = (
    "poorSignal", "weakSignal", "averageSignal", "stableSignal", "strongSignal",
)
_SIGNAL_FIELDS = frozenset({
    "totalClients", "clientsPercent", "clients2g", "clients5g", "clients6g",
})
_BANDS = ("2g", "5g", "6g")
_MAX_INVENTORY_ITEMS = 10000
_MAX_SITE_INVENTORY = 4000
_AP_HEALTH_DIMENSIONS = frozenset({
    "cpu", "memory", "incident", "channel_utilization", "supported_channel_utilization",
    "channel_interference", "supported_channel_interference", "transmission",
})
_AP_HEALTH_INT_FIELDS = frozenset({
    "score", "summary_score", "incident_count", "average", "average_2g", "average_5g",
    "average_6g", "average_noise_floor", "average_tx_retry", "average_tx_drop",
    "incidents_count", "discarded_out_of_window_points", "missing_value_points",
})
_AP_HEALTH_SERIES_FIELDS = frozenset({
    "values", "values_2g", "values_5g", "values_6g", "noise_floor_values",
    "tx_retry_values", "tx_drop_values",
})
_MAX_AP_HEALTH_POINTS_PER_SERIES = 256
# At most 18 documented AP health series (including the split band/noise/retry
# series) can each contribute one unclassified marker per point.
_MAX_AP_HEALTH_UNCLASSIFIED_FIELDS = 18 * _MAX_AP_HEALTH_POINTS_PER_SERIES
_AP_HEALTH_NONNEGATIVE_COUNTS = frozenset({
    "incident_count", "incidents_count", "discarded_out_of_window_points",
    "missing_value_points",
})
_AP_RADIO_SETTING_BANDS = {
    "radioSetting2g": "2g", "radioSetting5g": "5g", "radioSetting5g1": "5g1",
    "radioSetting5g2": "5g2", "radioSetting6g": "6g",
}
_AP_RADIO_FIELDS = frozenset({
    "channel", "channelWidth", "freq", "txPower", "txPowerLevel", "radioEnable",
})
_RF_BANDS = ("2g", "5g", "5g2", "6g")
_RF_ROW_FIELDS = frozenset({"channel", "channel_width", "utilization_percent", "interference"})
_CANONICAL_NUMERIC_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_MAX_CLIENT_INVENTORY = 4000
_MAX_CLIENT_TIMELINE_SESSIONS = 128
_MAX_CLIENT_TIMELINE_EVENTS = 1024
_MAX_CLIENT_HEALTH_POINTS = 256
_CLIENT_TIMELINE_KINDS = ("connect", "association", "roaming", "disconnect")
_CLIENT_TIMELINE_EVENT_TYPES = frozenset({0, 1, 2, 3, 100, 101, 102, 200, 201, 202})
_CLIENT_HISTORY_INT64_FIELDS = frozenset({"download", "upload", "duration", "lastSeen", "associated"})
_CLIENT_HISTORY_INT32_FIELDS = frozenset({"port", "vid", "reasonType", "associationTime"})
_CLIENT_HISTORY_BOOL_FIELDS = frozenset({"guest"})
_CLIENT_HISTORY_FIELDS = (_CLIENT_HISTORY_INT64_FIELDS | _CLIENT_HISTORY_INT32_FIELDS |
                          _CLIENT_HISTORY_BOOL_FIELDS)
_AP_LAN_TRAFFIC_FIELDS = frozenset({
    "rxPkts", "txPkts", "rx", "tx", "rxDropPkts", "txDropPkts",
    "rxErrPkts", "txErrPkts",
})
_CLIENT_REF_FIELDS = frozenset({
    "client_ref", "wireless", "radio_id", "channel", "rx_rate", "tx_rate",
    "health_score", "rssi", "snr", "active", "last_seen",
})
_CLIENT_DISPLAY_FIELDS = ("wireless", "radio_id", "channel", "rssi", "snr", "active")
_TEXT_SITE_SOURCES = (
    ("wifi_health_timeline", "WLAN-Gesundheit (Zeitreihe)"),
    ("wifi_health_details", "WLAN-Gesundheit (Details)"),
    ("wifi_channels", "WLAN-Kanäle"),
    ("site_6ghz_ap_presence", "6-GHz-AP am Standort"),
    ("site_rogue_ap_results", "Gespeicherte Rogue-AP-Scanergebnisse"),
    ("site_wids_summary", "WLAN-IDS-Ereignisse"),
    ("site_wids_blacklist_summary", "WLAN-IDS-Sperrliste"),
    ("client_signal_distribution", "Client-Signalverteilung"),
    ("site_topology_network_summary", "SSID- und Netzwerkübersicht"),
)
_TEXT_SITE_POLICY_SOURCES = (
    ("band_steering", "Band-Steering-Einstellung"),
    ("rrm_settings", "WLAN-Optimierungseinstellung"),
    ("roaming_settings", "Roaming-Einstellungen"),
)
_TEXT_ERROR_MESSAGES = {
    "ap_names_require_selection": "Namenanzeige erfordert eine interaktive AP-Auswahl",
    "ap_names_unavailable": "AP-Namen sind im Standortinventar nicht verfügbar",
    "ap_inventory_invalid": "AP-Inventar ungültig",
    "ap_inventory_empty": "keine Access Points im Standortinventar",
    "ap_inventory_unavailable": "AP-Inventar nicht verfügbar",
    "ap_ref_invalid": "AP-Auswahl ungültig",
    "ap_ref_not_access_point": "Ausgewähltes Gerät ist kein bestätigter Access Point",
    "ap_ref_unknown": "Access Point im Standortinventar nicht gefunden",
    "ap_selection_ambiguous": "AP-Auswahl wegen gleicher sichtbarer Merkmale mehrdeutig",
    "ap_selection_cancelled": "AP-Auswahl abgebrochen",
    "ap_selection_invalid": "AP-Auswahl ungültig",
    "ap_selection_unavailable": "interaktive Terminalauswahl nicht verfügbar",
    "base_url_invalid": "lokale Connector-Adresse ungültig",
    "client_inventory_empty": "keine Clients im Inventar",
    "client_inventory_invalid": "Client-Inventar ungültig",
    "client_inventory_unavailable": "Client-Inventar nicht verfügbar",
    "client_selection_ambiguous": "Client-Auswahl wegen gleicher sichtbarer Merkmale mehrdeutig",
    "client_selection_cancelled": "Client-Auswahl abgebrochen",
    "client_selection_invalid": "Client-Auswahl ungültig",
    "client_selection_unavailable": "interaktive Terminalauswahl nicht verfügbar",
    "client_timeline_invalid": "Client-Zeitreihenoption ungültig",
    "client_timeline_requires_selection": "Client-Zeitreihe erfordert eine Client-Auswahl",
    "connector_http_error": "Connector meldet einen HTTP-Fehler",
    "connector_unavailable": "Connector nicht erreichbar",
    "response_invalid": "Connector-Antwort ungültig oder unvollständig",
    "response_too_large": "Connector-Antwort überschreitet die Größenbegrenzung",
    "site_auto_multiple_sites": "mehr als ein Standort gefunden; bitte Standort fest auswählen",
    "site_auto_no_sites": "kein Standort im Inventar gefunden",
    "site_inventory_invalid": "Standortinventar ungültig",
    "site_inventory_unavailable": "Standortinventar nicht verfügbar",
    "site_ref_invalid": "Standortauswahl ungültig",
    "site_ref_unknown": "Standort im Inventar nicht gefunden",
    "site_selection_invalid": "Standortauswahl ungültig",
    "token_unavailable": "lokale Token-Datei nicht sicher verfügbar",
}
_TEXT_FIELD_LABELS = {
    "wifiHealthScore": "WLAN-Gesundheitswert",
    "summaryScore": "Zusammenfassungswert",
    "support": "Unterstützungsfeld",
    "averageInterf2g": "Rohwert Interferenz 2g",
    "averageInterf5g": "Rohwert Interferenz 5g",
    "averageInterf6g": "Rohwert Interferenz 6g",
    "averageNoiseFloor": "Rohwert Rauschboden",
    "averageAssocTime": "Rohwert mittlere Zuordnungszeit",
    "averageAuthTime": "Rohwert mittlere Authentifizierungszeit",
    "averageDhcpTime": "Rohwert mittlere DHCP-Zeit",
    "averageDnsTime": "Rohwert mittlere DNS-Zeit",
    "scores": "Rohwertpunkte",
    "assocTime": "Zuordnungszeit-Rohwerte",
    "authTime": "Authentifizierungszeit-Rohwerte",
    "dhcpTime": "DHCP-Zeit-Rohwerte",
    "dnsTime": "DNS-Zeit-Rohwerte",
    "score": "Rohwert",
    "pastNum": "Rohwert",
    "time_ms": "Zeitwert (ms)",
}
_TEXT_SIGNAL_FIELD_LABELS = {
    "totalClients": "gesamt",
    "clientsPercent": "clientsPercent (Rohwert)",
    "clients2g": "2g",
    "clients5g": "5g",
    "clients6g": "6g",
}
_TEXT_JSON_HINT = "Weitere Details: erneut mit --format json ausführen."


class CliError(Exception):
    """Fixed, non-sensitive CLI error code."""

    def __init__(self, code: str, *, upstream_http_status: int | None = None,
                 upstream_error_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.upstream_http_status = upstream_http_status
        self.upstream_error_code = upstream_error_code


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "error: invalid arguments\n")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _Parser(description=__doc__)
    site_choice = parser.add_mutually_exclusive_group(required=True)
    site_choice.add_argument("--site-ref")
    site_choice.add_argument("--site-auto", action="store_true")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--ap-ref")
    target.add_argument("--ap-select", action="store_true")
    target.add_argument("--client-select", action="store_true")
    parser.add_argument("--show-ap-names", action="store_true")
    parser.add_argument("--client-timeline", action="store_true")
    return parser.parse_args(argv)


def _origin(base_url: object) -> tuple[str, int]:
    if not isinstance(base_url, str) or len(base_url) > 256:
        raise CliError("base_url_invalid")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        raise CliError("base_url_invalid") from None
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or
            parsed.username is not None or parsed.password is not None or
            parsed.path != "" or parsed.query or parsed.fragment or
            "?" in base_url or "#" in base_url or
            re.fullmatch(r"(?:localhost|127\.0\.0\.1)(?::[1-9][0-9]{0,4})?",
                         parsed.netloc, flags=re.IGNORECASE) is None or
            (port is not None and not 1 <= port <= 65535)):
        raise CliError("base_url_invalid")
    host = parsed.hostname
    if host is None:
        raise CliError("base_url_invalid")
    return host, port or 80


def _load_token(path: object) -> str:
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 4096:
        raise CliError("token_unavailable")
    parts = path.split("/")
    if len(parts) < 3 or any(part in {"", ".", ".."} for part in parts[1:]):
        raise CliError("token_unavailable")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise CliError("token_unavailable")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_fd = -1
    token_fd = -1
    try:
        directory_fd = os.open("/", directory_flags)
        for component in parts[1:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        token_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        info = os.fstat(token_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or stat.S_IMODE(info.st_mode) not in (0o400, 0o600) or
                info.st_size > MAX_TOKEN_FILE_BYTES):
            raise CliError("token_unavailable")
        data = bytearray()
        while len(data) <= MAX_TOKEN_FILE_BYTES:
            chunk = os.read(token_fd, min(1024, MAX_TOKEN_FILE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        token_bytes = bytes(data).strip()
        if not TOKEN_PATTERN.fullmatch(token_bytes):
            raise CliError("token_unavailable")
        return token_bytes.decode("ascii")
    except CliError:
        raise
    except OSError:
        raise CliError("token_unavailable") from None
    finally:
        if token_fd >= 0:
            os.close(token_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid_constant")


def _request(host: str, port: int, path: str, token: str) -> object:
    connection = http.client.HTTPConnection(host, port, timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        connection.request("GET", path, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Connection": "close",
        })
        response = connection.getresponse()
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise CliError("response_too_large")
        if response.status != 200:
            raise CliError("connector_http_error")
        content_type = response.getheader("Content-Type", "")
        if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise CliError("response_invalid")
        try:
            return json.loads(body, object_pairs_hook=_pairs_no_duplicates,
                              parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise CliError("response_invalid") from None
    except CliError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException):
        raise CliError("connector_unavailable") from None
    finally:
        try:
            connection.close()
        except OSError:
            pass


def _int(value: object, *, minimum: int = -(2**63), maximum: int = 2**63 - 1) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _window(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != _WINDOW_KEYS:
        return None
    start, end = value.get("start_ms"), value.get("end_ms")
    if not _int(start, minimum=0) or not _int(end, minimum=0) or start > end:
        return None
    return {"start_ms": start, "end_ms": end}


def _counts(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != _HEALTH_COUNT_KEYS:
        return None
    if any(not _int(item, minimum=0, maximum=MAX_RESPONSE_BYTES) for item in value.values()):
        return None
    return {key: item for key, item in value.items()}


def _timeline_data(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CliError("response_invalid")
    window = _window(value.get("window"))
    points = value.get("scores")
    counts = _counts(value.get("counts"))
    if (window is None or not isinstance(points, list) or len(points) > 512 or
            type(value.get("partial")) is not bool or counts is None):
        raise CliError("response_invalid")
    if (counts["examined_points"] > min(counts["received_points"], 10000) or
            counts["unexamined_points"] != counts["received_points"] - counts["examined_points"] or
            counts["returned_points"] != len(points) or
            counts["returned_points"] > counts["examined_points"] or
            any(counts[key] > counts["examined_points"] for key in (
                "outside_window_points", "duplicate_timestamp_points", "truncated_points"))):
        raise CliError("response_invalid")
    scores: list[dict[str, int]] = []
    for point in points:
        if not isinstance(point, dict) or set(point) != {"time_ms", "score"}:
            raise CliError("response_invalid")
        if (not _int(point.get("time_ms"), minimum=window["start_ms"], maximum=window["end_ms"]) or
                not _int(point.get("score"), minimum=-(2**31), maximum=2**31 - 1)):
            raise CliError("response_invalid")
        scores.append({"time_ms": point["time_ms"], "score": point["score"]})
    partial_from_counts = any(counts[key] > 0 for key in (
        "unexamined_points", "outside_window_points", "duplicate_timestamp_points",
        "truncated_points", "unknown_fields"))
    return {"window": window, "scores": scores, "counts": counts,
            "partial": bool(value["partial"] or partial_from_counts)}


def _subhealth_data(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CliError("response_invalid")
    window = _window(value.get("window"))
    data = value.get("data")
    missing_fields = value.get("missing_fields", [])
    invalid_fields = value.get("invalid_fields", [])
    if (window is None or not isinstance(data, dict) or type(value.get("partial")) is not bool or
            not isinstance(missing_fields, list) or len(missing_fields) > 4096 or
            not isinstance(invalid_fields, list) or len(invalid_fields) > 4096 or
            not _int(value.get("unknown_field_count", 0), minimum=0, maximum=10000) or
            not _int(value.get("omitted_count", 0), minimum=0, maximum=10000)):
        raise CliError("response_invalid")
    clean: dict[str, object] = {}
    score = data.get("wifiHealthScore")
    if score is not None:
        if not _int(score, minimum=-(2**31), maximum=2**31 - 1):
            raise CliError("response_invalid")
        clean["wifiHealthScore"] = score
    for detail_name, detail in data.items():
        if detail_name == "wifiHealthScore":
            continue
        if detail_name not in _WIFI_DETAILS or not isinstance(detail, dict):
            raise CliError("response_invalid")
        if len(detail) > 32:
            raise CliError("response_invalid")
        clean_detail: dict[str, object] = {}
        for key, item in detail.items():
            if key == "incidents":
                continue
            if key in {"summaryScore", "averageInterf2g", "averageInterf5g", "averageInterf6g",
                       "averageNoiseFloor", "averageAssocTime", "averageAuthTime",
                       "averageDhcpTime", "averageDnsTime"}:
                if not _int(item, minimum=-(2**31), maximum=2**31 - 1):
                    raise CliError("response_invalid")
                clean_detail[key] = item
            elif key == "support":
                if type(item) is not bool:
                    raise CliError("response_invalid")
                clean_detail[key] = item
            elif key in _DETAIL_LISTS:
                if not isinstance(item, list) or len(item) > 512:
                    raise CliError("response_invalid")
                value_field = "pastNum" if key in {"assocTime", "authTime", "dhcpTime", "dnsTime"} else "score"
                points = []
                for point in item:
                    if (not isinstance(point, dict) or "time_ms" not in point or
                            set(point) - {"time_ms", value_field}):
                        raise CliError("response_invalid")
                    if (not _int(point["time_ms"], minimum=window["start_ms"], maximum=window["end_ms"]) or
                            (value_field in point and
                             not _int(point[value_field], minimum=-(2**31), maximum=2**31 - 1))):
                        raise CliError("response_invalid")
                    projected_point = {"time_ms": point["time_ms"]}
                    if value_field in point:
                        projected_point[value_field] = point[value_field]
                    points.append(projected_point)
                clean_detail[key] = points
            else:
                # Unknown or identity-bearing values are never echoed.
                continue
        clean[detail_name] = clean_detail
    local_unknown = any(
        key not in {"incidents", "summaryScore", "support", "scores", "assocTime", "authTime",
                    "dhcpTime", "dnsTime", "averageInterf2g", "averageInterf5g",
                    "averageInterf6g", "averageNoiseFloor", "averageAssocTime",
                    "averageAuthTime", "averageDhcpTime", "averageDnsTime"}
        for detail in data.values() if isinstance(detail, dict)
        for key in detail
    )
    return {"window": window, "data": clean,
            "partial": bool(value["partial"] or missing_fields or invalid_fields or
                            value["unknown_field_count"] or value["omitted_count"] or local_unknown),
            "missing_field_count": len(missing_fields),
            "invalid_field_count": len(invalid_fields),
            "unknown_field_count": value["unknown_field_count"],
            "omitted_count": value["omitted_count"]}


def _channels_data(value: object) -> dict[str, object]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            type(value.get("partial")) is not bool or not isinstance(value.get("data"), dict)):
        raise CliError("response_invalid")
    bands = value["data"].get("bands")
    if not isinstance(bands, dict) or not set(bands).issubset(_BANDS):
        raise CliError("response_invalid")
    clean_bands: dict[str, list[dict[str, object]]] = {}
    for band, rows in bands.items():
        if not isinstance(rows, list) or len(rows) > 256:
            raise CliError("response_invalid")
        clean_rows = []
        for row in rows:
            if not isinstance(row, dict) or not set(row).issubset(
                    {"channel", "ap_count", "client_count", "utilization_percent"}):
                raise CliError("response_invalid")
            clean = {}
            for key in ("channel", "ap_count", "client_count"):
                if key in row:
                    if not _int(row[key], minimum=0, maximum=2**31 - 1):
                        raise CliError("response_invalid")
                    clean[key] = row[key]
            if "utilization_percent" in row:
                utilization = row["utilization_percent"]
                if (utilization is not None and
                        (type(utilization) not in (int, float) or not 0 <= utilization <= 100 or
                         (type(utilization) is float and not math.isfinite(utilization)))):
                    raise CliError("response_invalid")
                clean["utilization_percent"] = utilization
            clean_rows.append(clean)
        clean_bands[band] = clean_rows
    missing_bands = not set(_BANDS).issubset(bands)
    return {"data": {"bands": clean_bands},
            "partial": bool(value["partial"] or missing_bands or
                            any(set(row) != {"channel", "ap_count", "client_count", "utilization_percent"}
                                for rows in bands.values() for row in rows))}


def _signal_data(value: object) -> dict[str, object]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            type(value.get("partial")) is not bool or not isinstance(value.get("data"), dict)):
        raise CliError("response_invalid")
    data = value["data"]
    if not set(data).issubset(_SIGNAL_CATEGORIES):
        raise CliError("response_invalid")
    clean: dict[str, dict[str, int]] = {}
    missing_metrics = False
    for category, metrics in data.items():
        if not isinstance(metrics, dict) or not set(metrics).issubset(_SIGNAL_FIELDS):
            raise CliError("response_invalid")
        if any(not _int(metric, minimum=-(2**31), maximum=2**31 - 1)
               for metric in metrics.values()):
            raise CliError("response_invalid")
        if not _SIGNAL_FIELDS.issubset(metrics):
            missing_metrics = True
        clean[category] = dict(metrics)
    missing_categories = not set(_SIGNAL_CATEGORIES).issubset(data)
    return {"data": clean,
            "partial": bool(value["partial"] or missing_categories or missing_metrics)}


def _ap_inventory_contains(payload: object, ap_ref: str) -> bool:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "devices"):
        raise CliError("ap_inventory_invalid")
    items = payload.get("items")
    count = payload.get("count")
    if (not isinstance(items, list) or len(items) > _MAX_SITE_INVENTORY or
            type(count) is not int or count != len(items)):
        raise CliError("ap_inventory_invalid")
    seen: set[str] = set()
    matches: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            raise CliError("ap_inventory_invalid")
        ref = item.get("device_ref")
        if not isinstance(ref, str) or not SITE_REF_PATTERN.fullmatch(ref) or ref in seen:
            raise CliError("ap_inventory_invalid")
        seen.add(ref)
        if ref == ap_ref:
            matches.append(item)
    if len(matches) != 1:
        return False
    device_type = matches[0].get("device_type")
    if (not isinstance(device_type, str) or len(device_type) > 64 or
            device_type.strip().casefold() not in {"ap", "access point", "accesspoint"}):
        raise CliError("ap_ref_not_access_point")
    return True


def _ap_tty_name(name: str) -> str:
    """Escape a name for the TTY and redact embedded address-like values."""
    safe = re.sub(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])",
                  "[MAC verborgen]", name)
    safe = re.sub(r"(?<![0-9A-Za-z])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9A-Za-z])",
                  "[IP verborgen]", safe)
    safe = re.sub(r"(?i)(?<![0-9a-f])[0-9a-f]{24}(?![0-9a-f])", "[Referenz verborgen]", safe)
    return ascii(safe)


def _ap_name_has_address(name: str) -> bool:
    if (re.search(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])", name) or
            re.search(r"(?<![0-9A-Za-z])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9A-Za-z])", name) or
            re.search(r"(?i)(?<![0-9a-f])[0-9a-f]{24}(?![0-9a-f])", name)):
        return True
    for token in re.findall(r"(?<![0-9A-Za-z])\[?[0-9A-Fa-f:.]+\]?(?![0-9A-Za-z])", name):
        candidate = token[1:-1] if token.startswith("[") and token.endswith("]") else token
        if ":" not in candidate:
            continue
        try:
            ipaddress.IPv6Address(candidate)
            return True
        except ValueError:
            continue
    return False


def _ap_candidates(payload: object, *, show_names: bool) -> list[dict[str, object]]:
    """Build a private, bounded AP selection list from one site inventory."""
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "devices"):
        raise CliError("ap_inventory_invalid")
    items, count = payload.get("items"), payload.get("count")
    if (not isinstance(items, list) or len(items) > _MAX_SITE_INVENTORY or
            type(count) is not int or count != len(items)):
        raise CliError("ap_inventory_invalid")
    allowed = {"device_ref", "device_type", "model", "state", "firmware", "device_name"}
    ap_types = {"ap", "access point", "accesspoint"}
    other_types = {"gateway", "router", "gw", "switch", "sw"}
    seen_refs: set[str] = set()
    seen_names: set[str] = set()
    candidates: list[dict[str, object]] = []
    display_signatures: set[tuple[object, ...]] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) - allowed:
            raise CliError("ap_inventory_invalid")
        ref, raw_type = item.get("device_ref"), item.get("device_type")
        if (not isinstance(ref, str) or not SITE_REF_PATTERN.fullmatch(ref) or
                ref in seen_refs or not isinstance(raw_type, str) or len(raw_type) > 64):
            raise CliError("ap_inventory_invalid")
        seen_refs.add(ref)
        device_type = raw_type.strip().casefold()
        if device_type in other_types:
            continue
        if device_type not in ap_types:
            raise CliError("ap_inventory_invalid")
        display: dict[str, object] = {"type": "AP"}
        model = item.get("model")
        if model is not None:
            if (not isinstance(model, str) or len(model) > 96 or
                    re.fullmatch(r"[A-Za-z0-9._() /+:-]{1,96}", model) is None):
                raise CliError("ap_inventory_invalid")
            display["model"] = model
        state = item.get("state")
        if state is not None:
            if type(state) is int and -(2**31) <= state <= 2**31 - 1:
                display["state"] = state
            elif (isinstance(state, str) and len(state) <= 96 and
                  re.fullmatch(r"[A-Za-z0-9._() /+:-]{1,96}", state) is not None):
                display["state"] = state
            else:
                raise CliError("ap_inventory_invalid")
        if show_names:
            name = item.get("device_name")
            if (not isinstance(name, str) or not name or len(name) > 128 or
                    any(ord(char) < 32 or ord(char) == 127 for char in name) or
                    _ap_name_has_address(name)):
                raise CliError("ap_names_unavailable")
            if name in seen_names:
                raise CliError("ap_selection_ambiguous")
            seen_names.add(name)
            # ascii() escapes terminal controls and non-ASCII characters; it is
            # emitted only to the verified controlling TTY, never to a report.
            display["name"] = _ap_tty_name(name)
        signature = tuple((key, display.get(key)) for key in ("type", "model", "state", "name"))
        if signature in display_signatures:
            raise CliError("ap_selection_ambiguous")
        display_signatures.add(signature)
        candidates.append({"_ref": ref, "display": display})
    if not candidates:
        raise CliError("ap_inventory_empty")
    if show_names and any("name" not in item["display"] for item in candidates):
        raise CliError("ap_names_unavailable")
    return candidates


def _select_ap(candidates: list[dict[str, object]], *, show_names: bool,
               tty_opener: Callable[[], object] | None = None) -> str:
    opener = tty_opener or _open_tty
    try:
        tty = opener()
    except CliError:
        raise CliError("ap_selection_unavailable") from None
    except Exception:
        raise CliError("ap_selection_unavailable") from None
    try:
        isatty = getattr(tty, "isatty", None)
        writer, flusher = getattr(tty, "write", None), getattr(tty, "flush", None)
        if not callable(isatty) or isatty() is not True or not callable(writer) or not callable(flusher):
            raise CliError("ap_selection_unavailable")
        writer("Access Points (Auswahl gilt nur für dieses Inventar):\n")
        for index, candidate in enumerate(candidates, 1):
            display = candidate["display"]
            assert isinstance(display, dict)
            pieces = ["Typ=AP"]
            if "model" in display:
                pieces.append("Modell=" + str(display["model"]))
            if "state" in display:
                pieces.append("Status=" + str(display["state"]))
            if show_names:
                pieces.append("Name=" + str(display["name"]))
            writer(f"{index}: " + " ".join(pieces) + "\n")
        writer("Index: ")
        flusher()
        try:
            selected_line = _tty_line(tty)
        except CliError:
            raise CliError("ap_selection_invalid") from None
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,3})", selected_line):
            raise CliError("ap_selection_invalid")
        selected_index = int(selected_line)
        if selected_index < 1 or selected_index > len(candidates):
            raise CliError("ap_selection_invalid")
        selected = candidates[selected_index - 1]
        writer("Auswahl mit ja bestätigen: ")
        flusher()
        try:
            confirmation = _tty_line(tty)
        except CliError:
            raise CliError("ap_selection_invalid") from None
        if confirmation.casefold() != "ja":
            raise CliError("ap_selection_cancelled")
        ref = selected.get("_ref")
        if not isinstance(ref, str) or not SITE_REF_PATTERN.fullmatch(ref):
            raise CliError("ap_inventory_invalid")
        return ref
    except CliError:
        raise
    except Exception:
        raise CliError("ap_selection_invalid") from None
    finally:
        closer = getattr(tty, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass


def _ap_health_data(value: object, start_ms: int, end_ms: int) -> dict[str, object]:
    if not isinstance(value, dict) or len(value) > 32:
        raise CliError("response_invalid")
    clean: dict[str, object] = {}
    partial = False
    for key, item in value.items():
        if key == "unclassified_minus_one_fields":
            if (not isinstance(item, list) or
                    len(item) > _MAX_AP_HEALTH_UNCLASSIFIED_FIELDS):
                raise CliError("response_invalid")
            partial = partial or bool(item)
            continue
        if key in _AP_HEALTH_INT_FIELDS:
            minimum = 0 if key in _AP_HEALTH_NONNEGATIVE_COUNTS else -(2**31)
            if not _int(item, minimum=minimum, maximum=2**31 - 1):
                partial = True
                continue
            clean[key] = item
            if key in {"discarded_out_of_window_points", "missing_value_points"} and item > 0:
                partial = True
        elif key == "supported":
            if type(item) is not bool:
                partial = True
                continue
            clean[key] = item
        elif key in _AP_HEALTH_DIMENSIONS:
            if not isinstance(item, dict) or len(item) > 32:
                partial = True
                continue
            clean_dimension: dict[str, object] = {}
            for field, field_value in item.items():
                if field in _AP_HEALTH_INT_FIELDS:
                    minimum = 0 if field in _AP_HEALTH_NONNEGATIVE_COUNTS else -(2**31)
                    if not _int(field_value, minimum=minimum, maximum=2**31 - 1):
                        partial = True
                        continue
                    clean_dimension[field] = field_value
                    if field in {"discarded_out_of_window_points", "missing_value_points"} and field_value > 0:
                        partial = True
                elif field == "supported":
                    if type(field_value) is not bool:
                        partial = True
                        continue
                    clean_dimension[field] = field_value
                elif field in _AP_HEALTH_SERIES_FIELDS:
                    if (not isinstance(field_value, list) or
                            len(field_value) > _MAX_AP_HEALTH_POINTS_PER_SERIES):
                        raise CliError("response_invalid")
                    points = []
                    for point in field_value:
                        if (not isinstance(point, dict) or set(point) != {"time_ms", "value"} or
                                not _int(point.get("time_ms"), minimum=start_ms, maximum=end_ms) or
                                not _int(point.get("value"), minimum=-(2**31), maximum=2**31 - 1)):
                            partial = True
                            continue
                        points.append({"time_ms": point["time_ms"], "value": point["value"]})
                    clean_dimension[field] = points
                else:
                    partial = True
            clean[key] = clean_dimension
        else:
            partial = True
    return {"data": clean, "partial": partial}


def _ap_health_response(payload: object, site_ref: str, ap_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "ap_health" or payload.get("site_ref") != site_ref or
            payload.get("device_ref") != ap_ref):
        raise CliError("response_invalid")
    start, end = payload.get("window_start_ms"), payload.get("window_end_ms")
    if (not _int(start, minimum=0) or not _int(end, minimum=0) or
            end < start or end - start != 86_400_000):
        raise CliError("response_invalid")
    declared_partial = payload.get("partial", False)
    if type(declared_partial) is not bool:
        raise CliError("response_invalid")
    data = _ap_health_data(payload.get("data"), start, end)
    known = {"status", "resource", "site_ref", "device_ref", "window_start_ms", "window_end_ms", "partial", "data"}
    return {"status": "ok", "partial": bool(declared_partial or data["partial"] or set(payload) - known),
            "capability_status": "unknown", "window": {"start_ms": start, "end_ms": end},
            "data": data["data"]}


def _ap_timeline_response(payload: object, site_ref: str, ap_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "ap_health_timeline" or
            payload.get("site_ref") != site_ref or payload.get("device_ref") != ap_ref):
        raise CliError("response_invalid")
    start, end = payload.get("window_start_ms"), payload.get("window_end_ms")
    data = payload.get("data")
    if (not _int(start, minimum=0) or not _int(end, minimum=0) or end < start or
            end - start != 86_400_000 or not isinstance(data, dict) or len(data) > 8 or
            type(payload.get("partial")) is not bool):
        raise CliError("response_invalid")
    partial = payload["partial"] or set(data) != {"scores"}
    known = {"status", "resource", "site_ref", "device_ref", "window_start_ms", "window_end_ms",
             "partial", "data", "missing_fields", "omitted_fields", "omitted_field_count"}
    partial = partial or bool(set(payload) - known)
    raw_scores = data.get("scores")
    scores: list[dict[str, int]] = []
    if not isinstance(raw_scores, list) or len(raw_scores) > 256:
        partial = True
        raw_scores = []
    for point in raw_scores:
        if (not isinstance(point, dict) or set(point) != {"time_ms", "score"} or
                not _int(point.get("time_ms"), minimum=start, maximum=end) or
                not _int(point.get("score"), minimum=-(2**31), maximum=2**31 - 1)):
            partial = True
            continue
        scores.append({"time_ms": point["time_ms"], "score": point["score"]})
    for metadata in ("missing_fields", "omitted_fields"):
        value = payload.get(metadata, [])
        if not isinstance(value, list) or len(value) > 512:
            raise CliError("response_invalid")
        partial = partial or bool(value)
    omitted_count = payload.get("omitted_field_count", 0)
    if not _int(omitted_count, minimum=0, maximum=10000):
        raise CliError("response_invalid")
    partial = partial or omitted_count > 0
    return {"status": "ok", "partial": bool(partial),
            "capability_status": "unknown", "window": {"start_ms": start, "end_ms": end},
            "data": {"scores": scores}}


def _ap_response_bound(payload: object, resource: str, site_ref: str,
                       ap_ref: str) -> dict[str, object]:
    """Validate an AP response's fixed resource and opaque device binding.

    The existing radio-config and rf-scan wrappers do not echo site_ref. Their
    site binding therefore comes from the fixed site-scoped route plus the
    connector's site/ref-to-MAC lookup. If an echoed site_ref is ever present,
    it must match exactly.
    """
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != resource or payload.get("device_ref") != ap_ref or
            ("site_ref" in payload and payload.get("site_ref") != site_ref)):
        raise CliError("response_invalid")
    return payload


def _ap_numeric(value: object, *, integer_only: bool = False) -> bool:
    if type(value) is int:
        return -(2**63) <= value <= 2**63 - 1
    if integer_only or type(value) is not float:
        return False
    return math.isfinite(value)


def _radio_number(value: object, *, integer_only: bool = False) -> int | float | None:
    if _ap_numeric(value, integer_only=integer_only):
        return value
    if (not isinstance(value, str) or len(value) > 64 or
            not _CANONICAL_NUMERIC_TEXT.fullmatch(value) or
            (integer_only and "." in value)):
        return None
    try:
        parsed: int | float = int(value) if "." not in value else float(value)
    except ValueError:
        return None
    return parsed if _ap_numeric(parsed, integer_only=integer_only) else None


def _ap_radio_config_response(payload: object, site_ref: str,
                              ap_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "radio_config", site_ref, ap_ref)
    raw = response.get("data")
    if not isinstance(raw, dict) or len(raw) > 16:
        raise CliError("response_invalid")
    clean_bands: dict[str, dict[str, object]] = {}
    partial = bool(set(response) - {"status", "resource", "site_ref", "device_ref", "data"})
    for source, band in _AP_RADIO_SETTING_BANDS.items():
        if source not in raw:
            partial = True
            continue
        setting = raw[source]
        if not isinstance(setting, dict) or len(setting) > 16:
            partial = True
            continue
        clean: dict[str, object] = {}
        if set(setting) - _AP_RADIO_FIELDS or not _AP_RADIO_FIELDS.issubset(setting):
            partial = True
        for field, value in setting.items():
            if field not in _AP_RADIO_FIELDS or value is None:
                partial = True
                continue
            if field == "radioEnable":
                if type(value) is not bool:
                    partial = True
                    continue
            else:
                normalized = _radio_number(
                    value, integer_only=field in {"channel", "channelWidth", "freq", "txPowerLevel"})
                if normalized is None:
                    partial = True
                    continue
                value = normalized
            clean[field] = value
        clean_bands[band] = clean
    return {"status": "ok", "partial": partial,
            "capability_status": "unknown", "data": {"bands": clean_bands}}


def _ap_rf_scan_data(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or len(value) > 16:
        raise CliError("response_invalid")
    partial = False
    clean: dict[str, object] = {"bands": {}}
    raw_bands: dict[str, list[object]] = {}
    total_histogram_points = 0
    for key, item in value.items():
        if key in _RF_BANDS:
            if not isinstance(item, list) or len(item) > 128:
                raise CliError("response_invalid")
            raw_bands[key] = item
        elif key.endswith("_scan_status") and key.removesuffix("_scan_status") in _RF_BANDS:
            if not _int(item, minimum=0, maximum=2):
                partial = True
                continue
            clean[key] = item
        else:
            partial = True
    for band in _RF_BANDS:
        if band not in raw_bands:
            partial = True
            continue
        rows: list[dict[str, object]] = []
        for row in raw_bands[band]:
            if not isinstance(row, dict) or not set(row).issubset(_RF_ROW_FIELDS):
                partial = True
                continue
            if not _RF_ROW_FIELDS.issubset(row):
                partial = True
            channel, width, utilization = row.get("channel"), row.get("channel_width"), row.get("utilization_percent")
            if (not _int(channel, minimum=1, maximum=233) or
                    not _int(width, minimum=2, maximum=5) or width not in {2, 3, 5} or
                    not _int(utilization, minimum=0, maximum=100)):
                partial = True
                continue
            interference_rows = row.get("interference")
            if not isinstance(interference_rows, list):
                partial = True
                interference_rows = []
            if len(interference_rows) > 2:
                raise CliError("response_invalid")
            clean_interference = []
            for interference in interference_rows:
                if (not isinstance(interference, dict) or
                        not set(interference).issubset({"level_dbm", "type", "histogram"})):
                    partial = True
                    continue
                level = interference.get("level_dbm")
                histogram = interference.get("histogram")
                if (not _int(level, minimum=-96, maximum=-48) or
                        not isinstance(histogram, list) or len(histogram) > 32):
                    partial = True
                    continue
                # `type` is an interpretation label; omit it instead of
                # presenting the controller's category as a confirmed cause.
                partial = True
                clean_histogram = []
                for point in histogram:
                    if (not isinstance(point, dict) or set(point) != {"signal_dbm", "count"} or
                            not _int(point.get("signal_dbm"), minimum=-91, maximum=-29) or
                            not _int(point.get("count"), minimum=0, maximum=200)):
                        partial = True
                        continue
                    total_histogram_points += 1
                    if total_histogram_points > 4096:
                        raise CliError("response_invalid")
                    clean_histogram.append({"signal_dbm": point["signal_dbm"],
                                            "count": point["count"]})
                clean_interference.append({"level_dbm": level, "histogram": clean_histogram})
            rows.append({"channel": channel, "channel_width": width,
                         "utilization_percent": utilization,
                         "interference": clean_interference})
        clean["bands"][band] = rows
    if any(band + "_scan_status" not in value for band in _RF_BANDS):
        partial = True
    return {"data": clean, "partial": partial}


def _ap_rf_scan_response(payload: object, site_ref: str,
                         ap_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_rf_scan", site_ref, ap_ref)
    projected = _ap_rf_scan_data(response.get("data"))
    missing_bands = response.get("missing_bands", [])
    if not isinstance(missing_bands, list) or len(missing_bands) > len(_RF_BANDS):
        raise CliError("response_invalid")
    if any(not isinstance(band, str) or band not in _RF_BANDS for band in missing_bands):
        raise CliError("response_invalid")
    partial = bool(projected["partial"] or missing_bands or response.get("partial") is True)
    if "partial" in response and type(response["partial"]) is not bool:
        raise CliError("response_invalid")
    known = {"status", "resource", "site_ref", "device_ref", "data", "partial", "missing_bands"}
    partial = partial or bool(set(response) - known)
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "data": projected["data"]}


def _route_projection(route_name: str, payload: object,
                      expected_site_ref: str) -> dict[str, object]:
    expected_resource = {
        "wifi_health_timeline": "wifi_health",
        "wifi_health_details": "wifi_subhealth",
        "wifi_channels": "site_dashboard_channels",
        "site_6ghz_ap_presence": "site_6ghz_ap_presence",
        "site_rogue_ap_results": "site_rogue_ap_results",
        "site_wids_summary": "site_wids_summary",
        "site_wids_blacklist_summary": "site_wids_blacklist_summary",
        "client_signal_distribution": "client_signal_distribution",
        "band_steering": "band_steering",
        "rrm_settings": "rrm_settings",
        "roaming_settings": "roaming_settings",
        "site_topology_network_summary": "site_topology_network_summary",
    }[route_name]
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != expected_resource or
            payload.get("site_ref") != expected_site_ref):
        raise CliError("response_invalid")
    if route_name == "wifi_health_timeline":
        data = _timeline_data(payload.get("data"))
    elif route_name == "wifi_health_details":
        data = _subhealth_data(payload)
    elif route_name == "wifi_channels":
        data = _channels_data(payload)
    elif route_name == "site_6ghz_ap_presence":
        source = payload.get("data")
        if (not isinstance(source, dict) or set(source) != {"has_6ghz_ap"} or
                type(source.get("has_6ghz_ap")) is not bool):
            raise CliError("response_invalid")
        data = {"partial": False, "has_6ghz_ap": source["has_6ghz_ap"]}
    elif route_name == "site_rogue_ap_results":
        summary = payload.get("summary")
        count = payload.get("count")
        expected_maps = ("by_radio_id", "by_channel", "by_security_code", "by_mode_code")
        expected_counts = ("unknown_radio_count", "unknown_security_count", "unknown_mode_count",
                           "unknown_row_count", "invalid_field_count", "unknown_field_count")
        if (not _int(count, minimum=0, maximum=10000) or not isinstance(summary, dict) or
                set(summary) != set(expected_maps) | set(expected_counts) | {"signal_dbm"}):
            raise CliError("response_invalid")
        clean: dict[str, object] = {}
        for key in expected_maps:
            value = summary[key]
            if (not isinstance(value, dict) or len(value) > 512 or
                    any(not isinstance(code, (str, int)) or
                        not _int(amount, minimum=0, maximum=10000)
                        for code, amount in value.items())):
                raise CliError("response_invalid")
            clean[key] = value
        for key in expected_counts:
            if not _int(summary[key], minimum=0, maximum=10000):
                raise CliError("response_invalid")
            clean[key] = summary[key]
        signal = summary["signal_dbm"]
        if (not isinstance(signal, dict) or set(signal) not in
                ({"sample_count"}, {"minimum", "maximum", "average", "sample_count"}) or
                not _int(signal["sample_count"], minimum=0, maximum=10000) or
                (signal["sample_count"] == 0 and set(signal) != {"sample_count"}) or
                (signal["sample_count"] > 0 and
                 (any(not _int(signal.get(k), minimum=-(2**31), maximum=2**31-1)
                      for k in ("minimum", "maximum")) or
                  type(signal.get("average")) not in {int, float} or
                  not math.isfinite(signal["average"])) )):
            raise CliError("response_invalid")
        clean["signal_dbm"] = signal
        if type(payload.get("partial")) is not bool or payload.get("data_age") != "unknown_stored_scan":
            raise CliError("response_invalid")
        partial = payload["partial"] or bool(set(payload) - {
            "status", "resource", "site_ref", "count", "summary", "partial", "data_age"})
        data = {"count": count, "summary": clean, "data_age": "unknown_stored_scan",
                "partial": partial}
    elif route_name == "site_wids_summary":
        summary = payload.get("summary")
        count = payload.get("count")
        total = payload.get("total_rows")
        expected_maps = ("by_level_code", "by_type_code", "by_band_code", "by_channel")
        expected_counts = ("unknown_level_count", "unknown_band_count", "invalid_field_count",
                           "unknown_field_count", "unknown_row_count")
        partial = payload.get("partial")
        if (not _int(count, minimum=0, maximum=1000) or
                not _int(total, minimum=count, maximum=2**63-1) or
                not isinstance(summary, dict) or
                set(summary) != set(expected_maps) | set(expected_counts) or
                type(partial) is not bool):
            raise CliError("response_invalid")
        clean: dict[str, object] = {"count": count, "total_rows": total}
        for key in expected_maps:
            value = summary[key]
            if (not isinstance(value, dict) or len(value) > 1000 or
                    any(not isinstance(code, (str, int)) or
                        not _int(amount, minimum=0, maximum=1000)
                        for code, amount in value.items())):
                raise CliError("response_invalid")
            clean[key] = value
        for key in expected_counts:
            if not _int(summary[key], minimum=0, maximum=1000):
                raise CliError("response_invalid")
            clean[key] = summary[key]
        clean["partial"] = partial or total > count
        data = clean
    elif route_name == "site_wids_blacklist_summary":
        summary = payload.get("summary")
        count = payload.get("count")
        total = payload.get("total_rows")
        expected_counts = ("invalid_field_count", "unknown_field_count", "unknown_row_count")
        if (not _int(count, minimum=0, maximum=1000) or
                not _int(total, minimum=count, maximum=2**63-1) or
                not isinstance(summary, dict) or set(summary) != set(expected_counts) or
                type(payload.get("partial")) is not bool or
                any(not _int(summary[key], minimum=0, maximum=1000)
                    for key in expected_counts)):
            raise CliError("response_invalid")
        data = {"count": count, "total_rows": total,
                "summary": {key: summary[key] for key in expected_counts},
                "partial": payload["partial"] or total > count}
    elif route_name == "site_topology_network_summary":
        source = payload.get("data")
        fields = {
            "unknown_field_count", "split_network_count", "default_network_count",
            "configuring_network_count", "unknown_network_field_count", "ssid_count",
            "ssid_vlan_enabled_count", "ssid_configuring_count", "ssid_client_count_sum",
            "ssid_vlan_id_count", "unknown_ssid_field_count", "partial",
        }
        if not isinstance(source, dict) or len(source) > len(fields):
            raise CliError("response_invalid")
        partial = (type(payload.get("partial")) is not bool or
                   type(source.get("partial")) is not bool or
                   payload.get("partial") != source.get("partial") or
                   set(source) != fields or bool(set(payload) - {
                       "status", "resource", "site_ref", "data", "partial"}))
        clean: dict[str, object] = {}
        for field in fields - {"partial"}:
            value = source.get(field)
            if value is None:
                partial = True
                clean[field] = None
            elif not _int(value, minimum=0, maximum=2**31 - 1):
                partial = True
            else:
                clean[field] = value
        clean["partial"] = partial or source.get("partial") is True
        data = clean
    elif route_name == "band_steering":
        source = payload.get("data")
        if (not isinstance(source, dict) or set(source) != {"mode"} or
                type(source.get("mode")) is not int or source["mode"] not in {0, 1, 2}):
            raise CliError("response_invalid")
        data = {"mode": source["mode"], "partial": False}
    elif route_name == "rrm_settings":
        source = payload.get("data")
        allowed = {"mode", "timeRangeEnable", "resource", "timeRangeAction"}
        if not isinstance(source, dict) or len(source) > len(allowed):
            raise CliError("response_invalid")
        enums = {"mode": {0, 1}, "resource": {0, 1, 2}, "timeRangeAction": {0, 1}}
        clean: dict[str, object] = {}
        partial = payload.get("partial") is True or set(source) != allowed
        if type(payload.get("partial", False)) is not bool:
            raise CliError("response_invalid")
        for key, value in source.items():
            valid = (type(value) is bool if key == "timeRangeEnable" else
                     type(value) is int and value in enums.get(key, set()))
            if key not in allowed:
                partial = True
            elif valid:
                clean[key] = value
            else:
                partial = True
        omitted_count = payload.get("omitted_field_count", 0)
        if type(omitted_count) is not int or not 0 <= omitted_count <= 64:
            raise CliError("response_invalid")
        data = {**clean, "partial": partial, "omitted_field_count": omitted_count}
    elif route_name == "roaming_settings":
        source = payload.get("data")
        allowed = {"fastRoamingEnable", "aiRoamingEnable", "dualBand11kReportEnable",
                   "forceDisassociationEnable", "nonStickRoamingEnable"}
        if not isinstance(source, dict) or len(source) > len(allowed):
            raise CliError("response_invalid")
        clean = {key: value for key, value in source.items()
                 if key in allowed and type(value) is bool}
        partial = (payload.get("partial") is True or set(clean) != allowed or
                   len(clean) != len(source))
        if type(payload.get("partial", False)) is not bool:
            raise CliError("response_invalid")
        omitted_count = payload.get("omitted_field_count", 0)
        if type(omitted_count) is not int or not 0 <= omitted_count <= 64:
            raise CliError("response_invalid")
        data = {**clean, "partial": partial, "omitted_field_count": omitted_count}
    else:
        data = _signal_data(payload)
    return {"status": "ok", "partial": data["partial"],
            "capability_status": "unknown", "data": data}


def _inventory_contains(payload: object, site_ref: str) -> bool:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise CliError("site_inventory_invalid")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > 10000:
        raise CliError("site_inventory_invalid")
    references = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("site_ref"), str):
            raise CliError("site_inventory_invalid")
        reference = item["site_ref"]
        if not SITE_REF_PATTERN.fullmatch(reference):
            raise CliError("site_inventory_invalid")
        references.append(reference)
    return site_ref in references


def _single_site_ref(payload: object) -> str:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "sites"):
        raise CliError("site_inventory_invalid")
    items, count = payload.get("items"), payload.get("count")
    if (not isinstance(items, list) or len(items) > _MAX_SITE_INVENTORY or
            type(count) is not int or count != len(items)):
        raise CliError("site_inventory_invalid")
    refs: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise CliError("site_inventory_invalid")
        reference = item.get("site_ref")
        if not isinstance(reference, str) or not SITE_REF_PATTERN.fullmatch(reference):
            raise CliError("site_inventory_invalid")
        if reference in seen:
            raise CliError("site_inventory_invalid")
        seen.add(reference)
        refs.append(reference)
    if not refs:
        raise CliError("site_auto_no_sites")
    if len(refs) != 1:
        raise CliError("site_auto_multiple_sites")
    return refs[0]


def _text_scalar(value: object) -> str | None:
    if type(value) is bool:
        return "ja" if value else "nein"
    if type(value) is int and -(2**63) <= value <= 2**63 - 1:
        return str(value)
    if type(value) is float and math.isfinite(value):
        return repr(value)
    return None


def _text_error(code: object) -> str:
    if isinstance(code, str):
        return _TEXT_ERROR_MESSAGES.get(code, "Fehler; Antwortdetails ausgeblendet")
    return "Fehler; Antwortdetails ausgeblendet"


def _text_status(section: object) -> tuple[str, bool]:
    if not isinstance(section, dict):
        return "unvollständig; Kapabilität unbekannt", True
    status = section.get("status")
    capability = section.get("capability_status")
    if isinstance(status, str) and status == "error":
        return f"Fehler: {_text_error(section.get('error'))}; Kapabilität unbekannt", True
    if not isinstance(status, str) or status not in {"ok", "partial"}:
        return "unvollständig; Kapabilität unbekannt", True
    partial_value = section.get("partial")
    partial = status == "partial" or partial_value is True or type(partial_value) is not bool
    if capability != "unknown":
        partial = True
    label = "teilweise" if partial else "ok"
    return f"{label}; Kapabilität unbekannt", partial


def _render_site_raw_values(report: dict[str, object]) -> tuple[list[str], bool]:
    lines: list[str] = []
    incomplete = False
    results = report.get("results")
    if not isinstance(results, dict):
        return ["  - Standortwerte: unvollständig"], True

    timeline = results.get("wifi_health_timeline")
    if (isinstance(timeline, dict) and isinstance(timeline.get("status"), str) and
            timeline.get("status") in {"ok", "partial"}):
        data = timeline.get("data")
        if isinstance(data, dict):
            if set(data) - {"window", "scores", "counts", "partial"}:
                incomplete = True
            points = data.get("scores")
            if isinstance(points, list):
                lines.append(f"  - Gesundheits-Zeitreihe: {len(points)} geprüfte Punkte")
                for point in points[:16]:
                    if not isinstance(point, dict) or set(point) != {"time_ms", "score"}:
                        incomplete = True
                        continue
                    time_value = _text_scalar(point.get("time_ms"))
                    score_value = _text_scalar(point.get("score"))
                    if time_value is None or score_value is None:
                        incomplete = True
                        continue
                    lines.append(f"    Zeitwert (ms)={time_value}; score-Rohwert={score_value}")
                if len(points) > 16:
                    lines.append(f"    weitere Punkte nicht gezeigt: {len(points) - 16}")
            else:
                incomplete = True
        else:
            incomplete = True

    details_result = results.get("wifi_health_details")
    details = details_result.get("data") if isinstance(details_result, dict) else None
    data = details.get("data") if isinstance(details, dict) else None
    if (isinstance(details_result, dict) and isinstance(details_result.get("status"), str) and
            details_result.get("status") in {"ok", "partial"} and
            not isinstance(data, dict)):
        incomplete = True
    if isinstance(data, dict):
        if set(data) - (_WIFI_DETAILS | {"wifiHealthScore"}):
            incomplete = True
        if "wifiHealthScore" in data:
            rendered_score = _text_scalar(data["wifiHealthScore"])
            if rendered_score is None:
                incomplete = True
            else:
                lines.append(f"  - WLAN-Gesundheitswert (Rohwert): {rendered_score}")
        point_count = 0
        for detail_name in sorted(_WIFI_DETAILS):
            detail = data.get(detail_name)
            if detail is None:
                continue
            if not isinstance(detail, dict):
                incomplete = True
                continue
            for field in sorted(detail):
                label = _TEXT_FIELD_LABELS.get(field)
                if label is None:
                    # Incidents are deliberately redacted by the projector.
                    if field != "incidents":
                        incomplete = True
                    continue
                value = detail[field]
                if field in _DETAIL_LISTS:
                    if not isinstance(value, list):
                        incomplete = True
                        continue
                    point_count += len(value)
                    for point in value[:12]:
                        if (not isinstance(point, dict) or
                                set(point) - {"time_ms", "score", "pastNum"}):
                            incomplete = True
                            continue
                        parts = []
                        for key in ("time_ms", "score", "pastNum"):
                            if key in point:
                                rendered = _text_scalar(point[key])
                                if rendered is None:
                                    incomplete = True
                                else:
                                    parts.append(f"{_TEXT_FIELD_LABELS[key]}={rendered}")
                        if parts:
                            lines.append(f"  - {label}: " + "; ".join(parts))
                    if len(value) > 12:
                        lines.append(f"    weitere Punkte nicht gezeigt: {len(value) - 12}")
                else:
                    rendered = _text_scalar(value)
                    if rendered is None:
                        incomplete = True
                    else:
                        lines.append(f"  - {label}: {rendered}")

    channels_result = results.get("wifi_channels")
    channel_data = channels_result.get("data") if isinstance(channels_result, dict) else None
    channel_projection = channel_data.get("data") if isinstance(channel_data, dict) else None
    bands = channel_projection.get("bands") if isinstance(channel_projection, dict) else None
    if (isinstance(channels_result, dict) and isinstance(channels_result.get("status"), str) and
            channels_result.get("status") in {"ok", "partial"} and
            not isinstance(bands, dict)):
        incomplete = True
    if isinstance(bands, dict):
        if set(bands) - set(_BANDS):
            incomplete = True
        for band in _BANDS:
            rows = bands.get(band)
            if not isinstance(rows, list):
                incomplete = True
                continue
            lines.append(f"  - Kanalband {band}: {len(rows)} Rohwert-Zeilen")
            for row in rows[:20]:
                if (not isinstance(row, dict) or set(row) - {
                        "channel", "ap_count", "client_count", "utilization_percent"}):
                    incomplete = True
                    continue
                pairs = []
                for field in ("channel", "ap_count", "client_count", "utilization_percent"):
                    if field not in row:
                        continue
                    value = row[field]
                    if value is None and field == "utilization_percent":
                        pairs.append("utilization_percent=keine Daten")
                    else:
                        rendered = _text_scalar(value)
                        if rendered is None:
                            incomplete = True
                        else:
                            pairs.append(f"{field}={rendered}")
                if pairs:
                    lines.append("    " + "; ".join(pairs))
            if len(rows) > 20:
                lines.append(f"    weitere Zeilen nicht gezeigt: {len(rows) - 20}")

    signal_result = results.get("client_signal_distribution")
    signal = signal_result.get("data") if isinstance(signal_result, dict) else None
    signal_data = signal.get("data") if isinstance(signal, dict) else None
    if (isinstance(signal_result, dict) and isinstance(signal_result.get("status"), str) and
            signal_result.get("status") in {"ok", "partial"} and
            not isinstance(signal_data, dict)):
        incomplete = True
    if isinstance(signal_data, dict):
        if set(signal_data) - set(_SIGNAL_CATEGORIES):
            incomplete = True
        category_labels = {
            "poorSignal": "Signalgruppe 1", "weakSignal": "Signalgruppe 2",
            "averageSignal": "Signalgruppe 3", "stableSignal": "Signalgruppe 4",
            "strongSignal": "Signalgruppe 5",
        }
        for category in _SIGNAL_CATEGORIES:
            metrics = signal_data.get(category)
            if not isinstance(metrics, dict):
                incomplete = True
                continue
            for field in sorted(_SIGNAL_FIELDS):
                if field not in metrics:
                    incomplete = True
                    continue
                rendered = _text_scalar(metrics[field])
                if rendered is None:
                    incomplete = True
                else:
                    field_label = _TEXT_SIGNAL_FIELD_LABELS[field]
                    lines.append(f"  - Signal {category_labels[category]} / {field_label}: {rendered}")
            if set(metrics) - set(_SIGNAL_FIELDS):
                incomplete = True
    return lines, incomplete


def _render_text(report: object) -> str:
    if not isinstance(report, dict):
        return "Gesamtzustand: unvollständig\nAntwortstruktur ungültig; Details ausgeblendet."
    lines: list[str] = []
    status = report.get("status")
    partial = status != "ok"
    lines.append("Gesamtzustand: " + ("ok" if status == "ok" else
                                      "Fehler" if status == "error" else "teilweise"))
    if status == "error" and "error" in report:
        lines.append("Fehler: " + _text_error(report.get("error")))
    lines.append("Standortquellen:")
    results = report.get("results")
    source_results = results if isinstance(results, dict) else {}
    policy_included = any(key in source_results for key, _ in _TEXT_SITE_POLICY_SOURCES)
    sources = _TEXT_SITE_SOURCES + (_TEXT_SITE_POLICY_SOURCES if policy_included else ())
    for key, label in sources:
        rendered, source_partial = _text_status(source_results.get(key))
        lines.append(f"- {label}: {rendered}")
        partial = partial or source_partial
    presence = source_results.get("site_6ghz_ap_presence")
    presence_data = presence.get("data") if isinstance(presence, dict) else None
    if isinstance(presence_data, dict) and type(presence_data.get("has_6ghz_ap")) is bool:
        lines.append("- 6-GHz-AP vorhanden: " +
                     ("ja" if presence_data["has_6ghz_ap"] else "nein"))
    else:
        partial = True
    if policy_included:
        band = source_results.get("band_steering")
        band_data = band.get("data") if isinstance(band, dict) else None
        if isinstance(band_data, dict) and type(band_data.get("mode")) is int:
            lines.append(f"- Band-Steering-Moduscode: {band_data['mode']}")
        else:
            partial = True
        rrm = source_results.get("rrm_settings")
        rrm_data = rrm.get("data") if isinstance(rrm, dict) else None
        if isinstance(rrm_data, dict):
            for key in ("mode", "timeRangeEnable", "resource", "timeRangeAction"):
                value = _text_scalar(rrm_data.get(key)) if key in rrm_data else None
                if value is not None:
                    lines.append(f"- RRM {key}: {value}")
                else:
                    partial = True
        else:
            partial = True
        roaming = source_results.get("roaming_settings")
        roaming_data = roaming.get("data") if isinstance(roaming, dict) else None
        if isinstance(roaming_data, dict):
            for key in ("fastRoamingEnable", "aiRoamingEnable", "dualBand11kReportEnable",
                        "forceDisassociationEnable", "nonStickRoamingEnable"):
                if type(roaming_data.get(key)) is bool:
                    lines.append(f"- Roaming {key}: {_text_scalar(roaming_data[key])}")
                else:
                    partial = True
        else:
            partial = True
    lines.append("Verfügbare Rohwerte:")
    raw_lines, raw_partial = _render_site_raw_values(report)
    lines.extend(raw_lines)
    partial = partial or raw_partial

    ap = report.get("ap")
    if ap is not None:
        lines.append("AP-Abfragen:")
        if not isinstance(ap, dict):
            lines.append(f"- AP-Quellen: unvollständig; {_TEXT_JSON_HINT}")
            partial = True
        else:
            for key, label in (("health", "AP-Gesundheit"), ("timeline", "AP-Zeitreihe"),
                               ("radio_config", "AP-Funkkonfiguration"), ("rf_scan", "AP-RF-Ergebnis")):
                rendered, issue = _text_status(ap.get(key))
                lines.append(f"- {label}: {rendered}; {_TEXT_JSON_HINT}")
                partial = partial or issue
            lan_traffic = ap.get("lan_traffic")
            if lan_traffic is not None:
                rendered, issue = _text_status(lan_traffic)
                lines.append(f"- AP-LAN-Verkehrszähler: {rendered}; {_TEXT_JSON_HINT}")
                partial = partial or issue

    client = report.get("client")
    if client is not None:
        lines.append("Client-Abfragen:")
        if not isinstance(client, dict):
            lines.append(f"- Client-Quelle: unvollständig; {_TEXT_JSON_HINT}")
            partial = True
        else:
            rendered, issue = _text_status(client.get("connections"))
            lines.append(f"- Verbindungsverlauf: {rendered}; {_TEXT_JSON_HINT}")
            partial = partial or issue
            timelines = client.get("timelines")
            if timelines is not None:
                lines.append("Client-Zeitreihen:")
                if not isinstance(timelines, dict):
                    lines.append(f"- Zeitreihen: unvollständig; {_TEXT_JSON_HINT}")
                    partial = True
                else:
                    for kind in _CLIENT_TIMELINE_KINDS:
                        rendered, issue = _text_status(timelines.get(kind))
                        lines.append(f"- Ereignistyp {kind}: {rendered}; {_TEXT_JSON_HINT}")
                        partial = partial or issue
            health_timeline = client.get("health_timeline")
            if health_timeline is not None:
                rendered, issue = _text_status(health_timeline)
                lines.append(f"- Client-Gesundheits-Zeitreihe: {rendered}; {_TEXT_JSON_HINT}")
                partial = partial or issue
            history = client.get("history")
            if history is not None:
                rendered, issue = _text_status(history)
                lines.append(f"- Client-Verlauf: {rendered}; {_TEXT_JSON_HINT}")
                partial = partial or issue
            lines.append(f"- Detaillierte Client-Werte: {_TEXT_JSON_HINT}")
    if partial and lines[0] == "Gesamtzustand: ok":
        lines[0] = "Gesamtzustand: teilweise"
    return "\n".join(lines)


def _open_tty():
    """Open only the real controlling terminal; never fall back to stdin/stdout."""
    flags = os.O_RDWR | getattr(os, "O_NOCTTY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open("/dev/tty", flags)
    except OSError:
        raise CliError("client_selection_unavailable") from None
    try:
        if not os.isatty(fd):
            raise CliError("client_selection_unavailable")
        return os.fdopen(fd, "r+", encoding="utf-8", errors="strict", buffering=1)
    except Exception:
        os.close(fd)
        raise


def _client_candidates(payload: object, *, allow_duplicate_displays: bool = False) -> list[dict[str, object]]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "clients"):
        raise CliError("client_inventory_invalid")
    items, count = payload.get("items"), payload.get("count")
    if (not isinstance(items, list) or len(items) > _MAX_CLIENT_INVENTORY or
            type(count) is not int or count != len(items)):
        raise CliError("client_inventory_invalid")
    candidates: list[dict[str, object]] = []
    seen_refs: set[str] = set()
    seen_displays: set[tuple[object, ...]] = set()
    int_fields = {"radio_id", "channel", "rx_rate", "tx_rate", "health_score", "rssi", "snr"}
    for item in items:
        if (not isinstance(item, dict) or set(item) - _CLIENT_REF_FIELDS or
                not isinstance(item.get("client_ref"), str) or
                not SITE_REF_PATTERN.fullmatch(item["client_ref"]) or
                item["client_ref"] in seen_refs):
            raise CliError("client_inventory_invalid")
        seen_refs.add(item["client_ref"])
        clean: dict[str, object] = {}
        for key, value in item.items():
            if key == "client_ref":
                continue
            if key in {"wireless", "active"}:
                if type(value) is not bool:
                    raise CliError("client_inventory_invalid")
            elif key in int_fields:
                if not _int(value, minimum=-(2**31), maximum=2**31 - 1):
                    raise CliError("client_inventory_invalid")
            elif key == "last_seen":
                if not _int(value, minimum=0, maximum=2**63 - 1):
                    raise CliError("client_inventory_invalid")
            clean[key] = value
        if not any(field in clean for field in _CLIENT_DISPLAY_FIELDS):
            raise CliError("client_inventory_invalid")
        signature = tuple(clean.get(field) for field in _CLIENT_DISPLAY_FIELDS)
        if signature in seen_displays and not allow_duplicate_displays:
            raise CliError("client_selection_ambiguous")
        seen_displays.add(signature)
        candidates.append({"_ref": item["client_ref"], "display": clean})
    if not candidates:
        raise CliError("client_inventory_empty")
    return candidates


def _tty_line(tty: object) -> str:
    try:
        reader = getattr(tty, "readline")
        line = reader(33)
    except Exception:
        raise CliError("client_selection_invalid") from None
    if not isinstance(line, str) or not line or len(line) > 32:
        raise CliError("client_selection_invalid")
    if "\n" in line[:-1] or "\r" in line[:-1]:
        raise CliError("client_selection_invalid")
    return line.rstrip("\r\n")


def _select_client(candidates: list[dict[str, object]],
                   tty_opener: Callable[[], object] | None = None) -> tuple[str, dict[str, object]]:
    opener = tty_opener or _open_tty
    try:
        tty = opener()
    except CliError:
        raise
    except Exception:
        raise CliError("client_selection_unavailable") from None
    try:
        isatty = getattr(tty, "isatty", None)
        if not callable(isatty) or isatty() is not True:
            raise CliError("client_selection_unavailable")
        writer = getattr(tty, "write", None)
        flusher = getattr(tty, "flush", None)
        if not callable(writer) or not callable(flusher):
            raise CliError("client_selection_unavailable")
        writer("Clients (nur sichere Merkmale; Indexe gelten nur für diese Auswahl):\n")
        for index, candidate in enumerate(candidates, 1):
            display = candidate["display"]
            assert isinstance(display, dict)
            pieces = []
            for field in _CLIENT_DISPLAY_FIELDS:
                value = display.get(field)
                rendered = "—" if field not in display else (
                    "ja" if value is True else "nein" if value is False else str(value))
                pieces.append(f"{field}={rendered}")
            writer(f"{index}: " + " ".join(pieces) + "\n")
        writer("Index: ")
        flusher()
        selected_line = _tty_line(tty)
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,3})", selected_line):
            raise CliError("client_selection_invalid")
        selected_index = int(selected_line)
        if selected_index < 1 or selected_index > len(candidates):
            raise CliError("client_selection_invalid")
        selected = candidates[selected_index - 1]
        writer("Auswahl mit ja bestätigen: ")
        flusher()
        confirmation = _tty_line(tty)
        if confirmation.casefold() != "ja":
            raise CliError("client_selection_cancelled")
        selected_ref = selected.get("_ref")
        display = selected.get("display")
        if (not isinstance(selected_ref, str) or not SITE_REF_PATTERN.fullmatch(selected_ref) or
                not isinstance(display, dict)):
            raise CliError("client_inventory_invalid")
        return selected_ref, {field: display[field] for field in _CLIENT_DISPLAY_FIELDS if field in display}
    except CliError:
        raise
    except Exception:
        raise CliError("client_selection_invalid") from None
    finally:
        closer = getattr(tty, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass


def _client_connections_response(payload: object, site_ref: str, client_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "client_connection_history" or
            payload.get("client_ref") != client_ref or
            ("site_ref" in payload and payload.get("site_ref") != site_ref)):
        raise CliError("response_invalid")
    start, end = payload.get("window_start_ms"), payload.get("window_end_ms")
    raw_items, raw_count = payload.get("items"), payload.get("count")
    if (not _int(start, minimum=0) or not _int(end, minimum=0) or
            end < start or end - start != 86_400_000 or
            not isinstance(raw_items, list) or len(raw_items) > 128 or
            type(raw_count) is not int or not 0 <= raw_count <= 128):
        raise CliError("response_invalid")
    partial = raw_count != len(raw_items)
    known_top = {"status", "resource", "client_ref", "site_ref", "window_start_ms",
                 "window_end_ms", "count", "items"}
    partial = partial or bool(set(payload) - known_top)
    items: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, dict) or not set(item).issubset({"kind", "start_ms", "duration_ms", "end_ms"}):
            partial = True
            continue
        kind = item.get("kind")
        item_start = item.get("start_ms")
        duration = item.get("duration_ms")
        finish = item.get("end_ms")
        if (not isinstance(kind, str) or kind not in {"connection", "roaming"} or
                not _int(item_start, minimum=start, maximum=end) or
                not _int(duration, minimum=0, maximum=2**63 - 1) or
                ("end_ms" in item and (kind != "connection" or
                 not _int(finish, minimum=item_start, maximum=end)))):
            partial = True
            continue
        if item_start + duration > end:
            # start_ms and duration_ms are separately documented raw values;
            # keep both and flag uncertainty without inferring an end/state.
            partial = True
        projected = {"kind": kind, "start_ms": item_start, "duration_ms": duration}
        if "end_ms" in item:
            projected["end_ms"] = finish
        items.append(projected)
    items.sort(key=lambda item: item["start_ms"])
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "window": {"start_ms": start, "end_ms": end},
            "duration_note": "duration_ms ist ein Rohwert; Endzeit und Verbindungsstatus werden daraus nicht abgeleitet",
            "data": {"count": len(items), "items": items}}


def _client_timeline_response(payload: object, site_ref: str, client_ref: str,
                              kind: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "client_timeline" or
            payload.get("site_ref") != site_ref or payload.get("client_ref") != client_ref or
            payload.get("kind") != kind):
        raise CliError("response_invalid")
    start, end = payload.get("window_start_ms"), payload.get("window_end_ms")
    data = payload.get("data")
    missing = payload.get("missing_fields", [])
    omitted = payload.get("omitted_fields", [])
    omitted_count = payload.get("omitted_field_count", 0)
    if (not _int(start, minimum=0) or not _int(end, minimum=0) or
            end < start or end - start != 86_400_000 or
            type(payload.get("partial")) is not bool or
            not isinstance(data, dict) or
            not isinstance(missing, list) or len(missing) > 4096 or
            not isinstance(omitted, list) or len(omitted) > 4096 or
            any(not isinstance(path, str) or len(path) > 256 for path in missing + omitted) or
            not _int(omitted_count, minimum=0, maximum=4096)):
        raise CliError("response_invalid")
    partial = bool(payload["partial"] or missing or omitted or omitted_count or
                   any(key not in payload for key in (
                       "missing_fields", "omitted_fields", "omitted_field_count")))
    known_top = {"status", "resource", "site_ref", "client_ref", "kind",
                 "window_start_ms", "window_end_ms", "data", "partial",
                 "missing_fields", "omitted_fields", "omitted_field_count"}
    if set(payload) - known_top:
        partial = True
    if set(data) - {"sessions"}:
        partial = True
    clean_data: dict[str, object] = {}
    if "sessions" in data:
        raw_sessions = data["sessions"]
        if (not isinstance(raw_sessions, list) or
                len(raw_sessions) > _MAX_CLIENT_TIMELINE_SESSIONS):
            raise CliError("response_invalid")
        total_events = 0
        sessions: list[dict[str, object]] = []
        for session in raw_sessions:
            if not isinstance(session, dict):
                partial = True
                continue
            if set(session) - {"start_ms", "end_ms", "events"}:
                partial = True
            projected_session: dict[str, object] = {}
            for field in ("start_ms", "end_ms"):
                if field not in session:
                    partial = True
                    continue
                value = session[field]
                if value is None:
                    projected_session[field] = None
                    partial = True
                elif _int(value, minimum=start, maximum=end):
                    projected_session[field] = value
                else:
                    partial = True
            if (type(projected_session.get("start_ms")) is int and
                    type(projected_session.get("end_ms")) is int and
                    projected_session["start_ms"] > projected_session["end_ms"]):
                projected_session.pop("end_ms", None)
                partial = True
            if "events" not in session:
                partial = True
            else:
                raw_events = session["events"]
                if not isinstance(raw_events, list):
                    partial = True
                else:
                    total_events += len(raw_events)
                    if total_events > _MAX_CLIENT_TIMELINE_EVENTS:
                        raise CliError("response_invalid")
                    events: list[dict[str, object]] = []
                    for event in raw_events:
                        if not isinstance(event, dict):
                            partial = True
                            continue
                        if set(event) - {"time_ms", "event_type"}:
                            partial = True
                        projected_event: dict[str, object] = {}
                        if "time_ms" not in event:
                            partial = True
                        elif event["time_ms"] is None:
                            projected_event["time_ms"] = None
                            partial = True
                        elif _int(event["time_ms"], minimum=start, maximum=end):
                            projected_event["time_ms"] = event["time_ms"]
                        else:
                            partial = True
                        event_type = event.get("event_type")
                        if type(event_type) is int and event_type in _CLIENT_TIMELINE_EVENT_TYPES:
                            projected_event["event_type"] = event_type
                        else:
                            partial = True
                        events.append(projected_event)
                    projected_session["events"] = events
            sessions.append(projected_session)
        clean_data["sessions"] = sessions
    else:
        partial = True
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "window": {"start_ms": start, "end_ms": end}, "data": clean_data}


def summarize_client_timeline(timeline: object) -> dict[str, object]:
    """Summarize a validated timeline without interpreting event-code meaning."""
    if (not isinstance(timeline, dict) or timeline.get("status") not in {"ok", "partial"} or
            type(timeline.get("partial")) is not bool or
            not isinstance(timeline.get("window"), dict)):
        raise CliError("response_invalid")
    data = timeline.get("data")
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, list) or len(sessions) > _MAX_CLIENT_TIMELINE_SESSIONS:
        raise CliError("response_invalid")
    event_count = 0
    unknown_event_count = 0
    by_code: dict[str, int] = {}
    times: list[int] = []
    for session in sessions:
        if not isinstance(session, dict) or not isinstance(session.get("events"), list):
            raise CliError("response_invalid")
        for event in session["events"]:
            if not isinstance(event, dict):
                raise CliError("response_invalid")
            event_count += 1
            code = event.get("event_type")
            if type(code) is int and code in _CLIENT_TIMELINE_EVENT_TYPES:
                key = str(code)
                by_code[key] = by_code.get(key, 0) + 1
            else:
                unknown_event_count += 1
            event_time = event.get("time_ms")
            if type(event_time) is int:
                times.append(event_time)
    partial = timeline["partial"] or unknown_event_count > 0
    summary: dict[str, object] = {
        "session_count": len(sessions), "event_count": event_count,
        "unknown_event_count": unknown_event_count,
        "by_event_type_code": dict(sorted(by_code.items(), key=lambda item: int(item[0]))),
        "first_event_ms": min(times) if times else None,
        "last_event_ms": max(times) if times else None,
    }
    return {"status": "partial" if partial else "ok", "partial": partial,
            "capability_status": "unknown", "window": timeline["window"],
            "summary": summary}


def _client_health_timeline_response(payload: object, site_ref: str,
                                     client_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "client_health_timeline" or
            payload.get("site_ref") != site_ref or payload.get("client_ref") != client_ref):
        raise CliError("response_invalid")
    start, end = payload.get("window_start_ms"), payload.get("window_end_ms")
    data = payload.get("data")
    missing, omitted = payload.get("missing_fields", []), payload.get("omitted_fields", [])
    omitted_count = payload.get("omitted_field_count", 0)
    if (not _int(start, minimum=0) or not _int(end, minimum=0) or
            end < start or end - start != 86_400_000 or
            type(payload.get("partial")) is not bool or not isinstance(data, dict) or
            not isinstance(missing, list) or len(missing) > 4096 or
            not isinstance(omitted, list) or len(omitted) > 4096 or
            any(not isinstance(path, str) or len(path) > 256 for path in missing + omitted) or
            not _int(omitted_count, minimum=0, maximum=4096)):
        raise CliError("response_invalid")
    partial = bool(payload["partial"] or missing or omitted or omitted_count or
                   any(key not in payload for key in (
                       "missing_fields", "omitted_fields", "omitted_field_count")))
    if set(payload) - {"status", "resource", "site_ref", "client_ref",
                       "window_start_ms", "window_end_ms", "data", "partial",
                       "missing_fields", "omitted_fields", "omitted_field_count"}:
        partial = True
    if set(data) - {"scores"}:
        partial = True
    clean_data: dict[str, object] = {}
    if "scores" in data:
        raw_scores = data["scores"]
        if not isinstance(raw_scores, list) or len(raw_scores) > _MAX_CLIENT_HEALTH_POINTS:
            raise CliError("response_invalid")
        scores: list[dict[str, int]] = []
        for point in raw_scores:
            if not isinstance(point, dict):
                partial = True
                continue
            if set(point) - {"time_ms", "score"}:
                partial = True
            time_ms, score = point.get("time_ms"), point.get("score")
            if not _int(time_ms, minimum=start, maximum=end):
                partial = True
                continue
            projected = {"time_ms": time_ms}
            if _int(score, minimum=-(2**31), maximum=2**31 - 1):
                projected["score"] = score
            else:
                partial = True
            scores.append(projected)
        clean_data["scores"] = scores
    else:
        partial = True
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "window": {"start_ms": start, "end_ms": end}, "data": clean_data}


def _client_history_response(payload: object, site_ref: str,
                             client_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "client_history" or
            payload.get("site_ref") != site_ref or payload.get("client_ref") != client_ref):
        raise CliError("response_invalid")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CliError("response_invalid")
    partial = payload.get("partial") is True or type(payload.get("partial")) is not bool
    if set(payload) - {"status", "resource", "site_ref", "client_ref", "data", "partial",
                       "missing_field_count", "invalid_field_count", "unknown_field_count",
                       "omitted_count"}:
        partial = True
    for key in ("missing_field_count", "invalid_field_count", "unknown_field_count", "omitted_count"):
        if key not in payload:
            partial = True
        elif not _int(payload[key], minimum=0, maximum=4000):
            partial = True
        elif payload[key] > 0:
            partial = True
    raw_rows, source_count = data.get("rows"), data.get("count")
    if not isinstance(raw_rows, list) or len(raw_rows) > 4000:
        raise CliError("response_invalid")
    if set(data) - {"count", "rows"}:
        partial = True
    if type(source_count) is not int or not 0 <= source_count <= 4000 or source_count != len(raw_rows):
        partial = True

    rows: list[dict[str, object]] = []
    for source in raw_rows:
        if not isinstance(source, dict):
            partial = True
            continue
        if set(source) - _CLIENT_HISTORY_FIELDS or not _CLIENT_HISTORY_FIELDS.issubset(source):
            partial = True
        projected: dict[str, object] = {}
        for field, value in source.items():
            if field in _CLIENT_HISTORY_BOOL_FIELDS:
                if type(value) is bool:
                    projected[field] = value
                else:
                    partial = True
            elif field in _CLIENT_HISTORY_INT32_FIELDS:
                if _int(value, minimum=-(2**31), maximum=2**31 - 1):
                    projected[field] = value
                else:
                    partial = True
            elif field in _CLIENT_HISTORY_INT64_FIELDS:
                if _int(value):
                    projected[field] = value
                else:
                    partial = True
        if projected:
            rows.append(projected)
        else:
            partial = True
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "data": {"count": len(rows), "rows": rows}}


def _ap_lan_traffic_response(payload: object, site_ref: str,
                             device_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "ap_lan_traffic" or
            payload.get("site_ref") != site_ref or payload.get("device_ref") != device_ref):
        raise CliError("response_invalid")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CliError("response_invalid")
    partial = payload.get("partial") is True or type(payload.get("partial")) is not bool
    if set(payload) - {"status", "resource", "site_ref", "device_ref", "data", "partial",
                       "missing_fields", "invalid_fields", "unknown_field_count"}:
        partial = True
    for key in ("missing_fields", "invalid_fields"):
        if key not in payload:
            partial = True
        elif not isinstance(payload[key], list) or len(payload[key]) > 8 or any(
                not isinstance(field, str) for field in payload[key]):
            partial = True
        elif payload[key]:
            partial = True
    unknown_count = payload.get("unknown_field_count")
    if not _int(unknown_count, minimum=0, maximum=32):
        partial = True
    elif unknown_count:
        partial = True
    if set(data) - _AP_LAN_TRAFFIC_FIELDS:
        partial = True
    clean: dict[str, int] = {}
    for field, value in data.items():
        if field not in _AP_LAN_TRAFFIC_FIELDS:
            continue
        if _int(value, minimum=0, maximum=2**63 - 1):
            clean[field] = value
        else:
            partial = True
    if set(clean) != _AP_LAN_TRAFFIC_FIELDS:
        partial = True
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "data": clean}


def _ap_wifi_neighbors_response(payload: object, site_ref: str,
                                device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_wifi_neighbors", site_ref, device_ref)
    items, count = response.get("items"), response.get("count")
    if (not isinstance(items, list) or len(items) > 512 or
            not _int(count, minimum=0, maximum=512) or count != len(items)):
        raise CliError("response_invalid")
    partial = bool(set(response) - {"status", "resource", "site_ref", "device_ref", "count", "items"})
    rows = []
    for item in items[:64]:
        if not isinstance(item, dict):
            raise CliError("response_invalid")
        band, channel = item.get("band"), item.get("channel")
        signal, bandwidth = item.get("signal_dbm"), item.get("bandwidth")
        if (not isinstance(band, str) or band not in {"2g", "5g", "5g2", "6g"} or
                not _int(channel, minimum=1, maximum=233) or
                not _int(signal, minimum=-120, maximum=0) or
                not _int(bandwidth, minimum=0, maximum=320)):
            partial = True
            continue
        if set(item) - {"neighbor_ref", "band", "channel", "signal_dbm", "bandwidth", "last_seen_ms"}:
            partial = True
        rows.append({"band": band, "channel": channel,
                     "signal_dbm": signal, "bandwidth": bandwidth})
    return {"status": "ok", "partial": partial or len(items) > 64,
            "capability_status": "unknown",
            "data": {"count": count, "rows": rows,
                     "omitted_count": max(0, count - len(rows))}}


def _ap_speed_test_response(payload: object, site_ref: str,
                            device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_speed_test_results", site_ref, device_ref)
    data = response.get("data")
    if not isinstance(data, dict):
        raise CliError("response_invalid")
    partial = bool(response.get("partial")) or bool(
        set(response) - {"status", "resource", "site_ref", "device_ref", "data", "partial"})
    if set(data) - {"main_testing", "results", "source_ap_ref", "target_ap_ref"}:
        partial = True
    main_testing = data.get("main_testing")
    if type(main_testing) is not bool:
        partial = True
        main_testing = None
    results = data.get("results")
    if not isinstance(results, list) or len(results) > 4:
        raise CliError("response_invalid")
    clean_results = []
    seen_roles = set()
    for row in results:
        if not isinstance(row, dict):
            raise CliError("response_invalid")
        if set(row) - {"role", "down_rate", "up_rate", "time_ms", "status", "error_code"}:
            partial = True
        role = row.get("role")
        if not _int(role, minimum=0, maximum=1) or role in seen_roles:
            partial = True
            continue
        seen_roles.add(role)
        projected = {"role": role}
        for field in ("down_rate", "up_rate"):
            value = row.get(field)
            if (type(value) in {int, float} and math.isfinite(value) and
                    0 <= value <= 1_000_000_000):
                projected[field] = value
            else:
                partial = True
        if "time_ms" in row:
            if _int(row["time_ms"], minimum=0):
                projected["time_ms"] = row["time_ms"]
            else:
                partial = True
        if "status" in row:
            if _int(row["status"], minimum=-2, maximum=1):
                projected["status"] = row["status"]
            else:
                partial = True
        if "error_code" in row:
            if _int(row["error_code"], minimum=-(2**31), maximum=2**31 - 1):
                projected["error_code"] = row["error_code"]
            else:
                partial = True
        clean_results.append(projected)
    # The report is scoped to one selected AP; keep peer references out of it.
    result_data: dict[str, object] = {"main_testing": main_testing,
                                      "results": clean_results}
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "data": result_data}


def _ap_wired_downlink_response(payload: object, site_ref: str,
                                device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_wired_downlink", site_ref, device_ref)
    items, count = response.get("items"), response.get("count")
    if (not isinstance(items, list) or len(items) > 256 or
            not _int(count, minimum=0, maximum=256) or count != len(items)):
        raise CliError("response_invalid")
    partial = bool(response.get("partial")) or bool(
        set(response) - {"status", "resource", "site_ref", "device_ref", "count", "source_count",
                         "items", "partial", "omitted_count", "unknown_field_count",
                         "redacted_field_count"})
    source_count = response.get("source_count")
    if not _int(source_count, minimum=count, maximum=256):
        partial = True
    safe_fields = {"port", "portType", "duplex", "link", "speed",
                   "poeState", "voipState", "txPower", "rxPower", "temp", "voltage",
                   "current", "rxPkts", "txPkts", "rx", "tx", "rxDropPkts",
                   "txDropPkts", "rxErrPkts", "txErrPkts", "downLinkPort", "display"}
    accepted_fields = safe_fields | {"device_ref"}
    rows = []
    for row in items:
        if not isinstance(row, dict) or len(row) > 32:
            raise CliError("response_invalid")
        if set(row) - accepted_fields:
            partial = True
        clean = {key: value for key, value in row.items() if key in safe_fields}
        if not clean:
            partial = True
            continue
        rows.append(clean)
    omitted = response.get("omitted_count", 0)
    if not _int(omitted, minimum=0, maximum=256):
        partial = True
        omitted = 0
    partial = partial or bool(omitted)
    for field in ("unknown_field_count", "redacted_field_count"):
        value = response.get(field, 0)
        if not _int(value, minimum=0, maximum=256):
            partial = True
        elif field == "unknown_field_count" and value:
            partial = True
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "data": {"count": count, "rows": rows, "omitted_count": omitted}}


def _ap_ports_response(payload: object, site_ref: str,
                       device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_ports", site_ref, device_ref)
    summary = response.get("summary")
    count = response.get("count")
    if not _int(count, minimum=0, maximum=128) or not isinstance(summary, dict):
        raise CliError("response_invalid")
    maps = ("by_link_status_code", "by_link_speed_code", "by_port_type_code",
            "duplex_code_counts", "poe_state_code_counts", "poe_input_mode_code_counts")
    counts = ("poe_supported_ports", "poe_output_enabled_ports", "uplink_ports",
              "logical_uplink_ports", "vlan_supported_ports", "local_vlan_enabled_ports",
              "unknown_row_count", "invalid_field_count", "unknown_field_count")
    if set(summary) != set(maps) | set(counts):
        raise CliError("response_invalid")
    clean: dict[str, object] = {}
    for key in maps:
        value = summary[key]
        if (not isinstance(value, dict) or len(value) > 16 or
                any(not isinstance(code, (str, int)) or
                    not _int(amount, minimum=0, maximum=128) for code, amount in value.items())):
            raise CliError("response_invalid")
        clean[key] = value
    for key in counts:
        if not _int(summary[key], minimum=0, maximum=128):
            raise CliError("response_invalid")
        clean[key] = summary[key]
    partial = response.get("partial") is True or any(
        clean[key] for key in ("unknown_row_count", "invalid_field_count", "unknown_field_count"))
    if set(response) - {"status", "resource", "site_ref", "device_ref", "count", "summary", "partial"}:
        partial = True
    return {"status": "ok", "capability_status": "unknown", "partial": partial,
            "count": count, "summary": clean}


def _ap_port_vlans_response(payload: object, site_ref: str,
                            device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_port_vlans", site_ref, device_ref)
    vlan_ids = response.get("vlan_id_counts")
    port_counts = response.get("port_counts")
    if (not _int(response.get("count"), minimum=0, maximum=10_000) or
            not _int(response.get("total_rows"), minimum=0, maximum=10_000) or
            not isinstance(vlan_ids, dict) or len(vlan_ids) > 10_000 or
            not isinstance(port_counts, dict) or
            set(port_counts) != {"nativePort", "tagPort", "untagPort"}):
        raise CliError("response_invalid")
    clean_vlan_ids: dict[str, int] = {}
    for vlan_id, count in vlan_ids.items():
        if (not isinstance(vlan_id, str) or not re.fullmatch(r"-?[0-9]{1,10}", vlan_id) or
                not _int(count, minimum=1, maximum=10_000)):
            raise CliError("response_invalid")
        parsed = int(vlan_id)
        if not -(2**31) <= parsed <= 2**31 - 1:
            raise CliError("response_invalid")
        clean_vlan_ids[vlan_id] = count
    clean_ports = {}
    for key, value in port_counts.items():
        if not _int(value, minimum=0, maximum=2_000_000):
            raise CliError("response_invalid")
        clean_ports[key] = value
    counts = ("redacted_field_count", "unknown_field_count", "invalid_row_or_field_count")
    for key in counts:
        if not _int(response.get(key), minimum=0, maximum=100_000):
            raise CliError("response_invalid")
    partial = response.get("partial") is True or bool(
        response["unknown_field_count"] or response["invalid_row_or_field_count"] or
        response["count"] != response["total_rows"])
    if set(response) - {"status", "resource", "site_ref", "device_ref", "count",
                        "total_rows", "vlan_id_counts", "port_counts", *counts, "partial"}:
        partial = True
    return {"status": "ok", "capability_status": "unknown", "partial": partial,
            "count": response["count"], "total_rows": response["total_rows"],
            "vlan_id_counts": clean_vlan_ids, "port_counts": clean_ports,
            "redacted_field_count": response["redacted_field_count"],
            "unknown_field_count": response["unknown_field_count"],
            "invalid_row_or_field_count": response["invalid_row_or_field_count"]}


def _ap_lldp_config_response(payload: object, site_ref: str,
                             device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_lldp_config", site_ref, device_ref)
    expected = {"status", "resource", "site_ref", "device_ref", "data", "partial",
                "missing_field_count", "invalid_field_count", "unknown_field_count"}
    data = response.get("data")
    if not isinstance(data, dict) or set(data) - {"setting_code", "setting", "supported"}:
        raise CliError("response_invalid")
    setting_code = data.get("setting_code")
    setting = data.get("setting")
    supported = data.get("supported")
    labels = {0: "off", 1: "on", 2: "site_default"}
    if ((setting_code is None) != (setting is None) or
            (setting_code is not None and
             (type(setting_code) is not int or labels.get(setting_code) != setting)) or
            (supported is not None and type(supported) is not bool)):
        raise CliError("response_invalid")
    partial = type(response.get("partial")) is not bool or response.get("partial") is True
    for name in ("missing_field_count", "invalid_field_count", "unknown_field_count"):
        value = response.get(name)
        if not _int(value, minimum=0, maximum=8):
            raise CliError("response_invalid")
        partial = partial or value > 0
    partial = partial or bool(set(response) - expected)
    return {"status": "ok", "capability_status": "unknown", "partial": partial,
            "data": {key: data[key] for key in ("setting_code", "setting", "supported")
                     if key in data}}


def _ap_wired_uplink_response(payload: object, site_ref: str,
                               device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_wired_uplink", site_ref, device_ref)
    expected = {"status", "resource", "site_ref", "device_ref", "data", "partial",
                "missing_fields", "invalid_fields", "unknown_field_count",
                "redacted_field_count"}
    partial = bool(set(response) - expected)
    if type(response.get("partial")) is not bool:
        partial = True
    else:
        partial = partial or response["partial"]
    for name in ("missing_fields", "invalid_fields"):
        values = response.get(name, [])
        if not isinstance(values, list) or len(values) > 48 or any(
                not isinstance(value, str) or len(value) > 128 for value in values):
            partial = True
        elif values:
            partial = True
    for name in ("unknown_field_count", "redacted_field_count"):
        value = response.get(name, 0)
        if not _int(value, minimum=0, maximum=48):
            partial = True
        elif name == "unknown_field_count" and value:
            partial = True
    data = response.get("data")
    if not isinstance(data, dict) or set(data) - {"wiredUplink"}:
        raise CliError("response_invalid")
    uplink = data.get("wiredUplink")
    if not isinstance(uplink, dict) or len(uplink) > 32:
        raise CliError("response_invalid")
    integer_fields = {
        "duplex": (0, 2), "portType": (0, 2), "poeState": (0, 1),
        "voipState": (0, 1), "linkStatus": (-(2**31), 2**31 - 1),
        "linkSpeed": (-(2**31), 2**31 - 1),
        "upBytes": (-(2**63), 2**63 - 1), "downBytes": (-(2**63), 2**63 - 1),
        "upPackets": (-(2**63), 2**63 - 1), "downPackets": (-(2**63), 2**63 - 1),
        "upDropPackets": (-(2**63), 2**63 - 1),
        "downDropPackets": (-(2**63), 2**63 - 1),
        "upErrorsPackets": (-(2**63), 2**63 - 1),
        "downErrorsPackets": (-(2**63), 2**63 - 1),
        "activity": (-(2**63), 2**63 - 1),
    }
    numeric_fields = {"txPower", "rxPower", "temp", "voltage", "current"}
    allowed = set(integer_fields) | numeric_fields | {"rate_mbps"}
    clean: dict[str, int | float] = {}
    for key, value in uplink.items():
        if key not in allowed:
            partial = True
        elif key in integer_fields:
            low, high = integer_fields[key]
            if not _int(value, minimum=low, maximum=high):
                partial = True
            else:
                clean[key] = value
        elif key == "rate_mbps":
            if not _int(value, minimum=0, maximum=10000) or value not in {
                    0, 10, 100, 1000, 2500, 10000}:
                partial = True
            else:
                clean[key] = value
        elif _ap_numeric(value):
            clean[key] = value
        else:
            partial = True
    if set(clean) != set(uplink):
        partial = True
    return {"status": "ok", "partial": partial, "capability_status": "unknown",
            "data": {"wiredUplink": clean}}


def _ap_wlan_overrides_response(payload: object, site_ref: str,
                                device_ref: str) -> dict[str, object]:
    response = _ap_response_bound(payload, "ap_wlan_overrides", site_ref, device_ref)
    fields = {
        "entry_count", "included_entry_count", "truncated_entry_count",
        "enabled_count", "disabled_count", "unknown_enabled_state_count",
        "vlan_enabled_count", "vlan_disabled_count", "unknown_vlan_state_count",
        "password_present_count", "vlan_id_present_count", "vlan_pool_present_count",
        "by_band_code", "by_security_code", "ap_group_assigned",
        "redacted_field_count", "invalid_row_count", "unknown_field_count",
        "invalid_field_count", "missing_field_count", "partial",
    }
    partial = bool(response.get("partial")) or bool(set(response) - {
        "status", "resource", "site_ref", "device_ref", *fields})
    if set(response) - {"status", "resource", "site_ref", "device_ref", *fields}:
        partial = True
    data: dict[str, object] = {}
    counts = fields - {"by_band_code", "by_security_code", "ap_group_assigned", "partial"}
    for field in counts:
        value = response.get(field)
        if not _int(value, minimum=0, maximum=4096):
            partial = True
            continue
        data[field] = value
    for field, allowed in (("by_band_code", {"0", "1", "2"}),
                           ("by_security_code", {"0", "2", "3", "4", "5"})):
        raw = response.get(field)
        if not isinstance(raw, dict) or len(raw) > 5:
            partial = True
            continue
        clean = {}
        for code, count in raw.items():
            normalized = str(code) if type(code) is int else code
            if normalized not in allowed or not _int(count, minimum=0, maximum=4096):
                partial = True
                continue
            clean[normalized] = count
        data[field] = clean
    if type(response.get("ap_group_assigned")) is bool:
        data["ap_group_assigned"] = response["ap_group_assigned"]
    else:
        partial = True
    return {"status": "ok", "partial": partial,
            "capability_status": "unknown", "data": data}


_DIAGNOSTIC_ROUTES = (
    ("wifi_health_timeline", "/v1/sites/{site_ref}/wifi/health/timeline"),
    ("wifi_health_details", "/v1/sites/{site_ref}/wifi/health/details"),
    ("wifi_channels", "/v1/sites/{site_ref}/wifi/channels"),
    ("client_signal_distribution", "/v1/sites/{site_ref}/wifi/client-signal-distribution"),
    ("site_6ghz_ap_presence", "/v1/sites/{site_ref}/wifi/6ghz-ap-presence"),
    ("site_rogue_ap_results", "/v1/sites/{site_ref}/wifi/rogue-ap-results"),
    ("site_wids_summary", "/v1/sites/{site_ref}/wifi/wids-summary"),
    ("site_wids_blacklist_summary", "/v1/sites/{site_ref}/wifi/wids-blacklist-summary"),
    ("band_steering", "/v1/sites/{site_ref}/wifi/band-steering"),
    ("rrm_settings", "/v1/sites/{site_ref}/wifi/optimization"),
    ("roaming_settings", "/v1/sites/{site_ref}/wifi/roaming"),
    ("site_topology_network_summary", "/v1/sites/{site_ref}/topology/network-summary"),
)


def run(site_ref: str | None, token_file: str, base_url: str = DEFAULT_BASE_URL,
        ap_ref: str | None = None, client_select: bool = False,
        tty_opener: Callable[[], object] | None = None,
        client_timeline: bool = False, site_auto: bool = False,
        ap_select: bool = False, show_ap_names: bool = False,
        requester: Callable[[str], object] | None = None,
        client_ref: str | None = None,
        compact_client_timeline: bool = False,
        include_wlan_policy_context: bool | None = None,
        current_inventory: dict[str, object] | None = None) -> dict[str, object]:
    if type(site_auto) is not bool or (site_auto and site_ref is not None):
        raise CliError("site_selection_invalid")
    if not site_auto and (not isinstance(site_ref, str) or not SITE_REF_PATTERN.fullmatch(site_ref)):
        raise CliError("site_ref_invalid")
    if (type(client_select) is not bool or (client_select and ap_ref is not None) or
            (client_select and client_ref is not None)):
        raise CliError("client_selection_invalid")
    if (client_ref is not None and
            (not isinstance(client_ref, str) or not SITE_REF_PATTERN.fullmatch(client_ref) or
             ap_ref is not None or ap_select)):
        raise CliError("client_selection_invalid")
    if type(compact_client_timeline) is not bool:
        raise CliError("client_timeline_invalid")
    if include_wlan_policy_context is not None and type(include_wlan_policy_context) is not bool:
        raise CliError("site_selection_invalid")
    include_policy = (not (client_ref is not None or ap_ref is not None or
                           client_select or ap_select)
                      if include_wlan_policy_context is None else include_wlan_policy_context)
    if (type(ap_select) is not bool or (ap_select and (ap_ref is not None or client_select))):
        raise CliError("ap_selection_invalid")
    if type(show_ap_names) is not bool or (show_ap_names and not ap_select):
        raise CliError("ap_names_require_selection")
    if type(client_timeline) is not bool:
        raise CliError("client_timeline_invalid")
    if client_timeline and not (client_select or client_ref is not None):
        raise CliError("client_timeline_requires_selection")
    if ap_ref is not None and (not isinstance(ap_ref, str) or not SITE_REF_PATTERN.fullmatch(ap_ref)):
        raise CliError("ap_ref_invalid")
    if requester is not None and not callable(requester):
        raise CliError("connector_unavailable")
    if current_inventory is not None and (
            client_ref is None or client_select or site_auto or
            not isinstance(current_inventory, dict) or
            set(current_inventory) != {"sites", "clients"}):
        raise CliError("client_inventory_invalid")
    if requester is None:
        host, port = _origin(base_url)
        token = _load_token(token_file)

    def fetch(path: str) -> object:
        if requester is not None:
            return requester(path)
        return _request(host, port, path, token)

    if current_inventory is None:
        try:
            inventory = fetch("/v1/sites")
        except CliError:
            raise CliError("site_inventory_unavailable") from None
    else:
        inventory = current_inventory["sites"]
    if site_auto:
        site_ref = _single_site_ref(inventory)
    elif not _inventory_contains(inventory, site_ref):
        raise CliError("site_ref_unknown")
    assert isinstance(site_ref, str)
    report_site = {} if site_auto else {"site_ref": site_ref}

    selected_client_ref: str | None = None
    client_selection: dict[str, object] | None = None
    if client_select or client_ref is not None:
        if current_inventory is not None:
            clients_payload = current_inventory["clients"]
        else:
            try:
                clients_payload = fetch(f"/v1/sites/{site_ref}/clients")
            except CliError:
                raise CliError("client_inventory_unavailable") from None
        candidates = _client_candidates(clients_payload, allow_duplicate_displays=client_ref is not None)
        if client_ref is None:
            selected_client_ref, client_selection = _select_client(candidates, tty_opener)
        else:
            selected = [candidate for candidate in candidates if candidate.get("_ref") == client_ref]
            if not selected:
                raise CliError("client_ref_unknown")
            selected_client_ref = client_ref
            client_selection = selected[0]["display"]

    ap_report: dict[str, object] | None = None
    ap_inventory_loaded = False
    if ap_select:
        try:
            devices = fetch(f"/v1/sites/{site_ref}/devices")
        except CliError:
            raise CliError("ap_inventory_unavailable") from None
        ap_candidates = _ap_candidates(devices, show_names=show_ap_names)
        ap_ref = _select_ap(ap_candidates, show_names=show_ap_names, tty_opener=tty_opener)
        ap_inventory_loaded = True
    if ap_ref is not None:
        if not ap_inventory_loaded:
            try:
                devices = fetch(f"/v1/sites/{site_ref}/devices")
            except CliError:
                raise CliError("ap_inventory_unavailable") from None
            if not _ap_inventory_contains(devices, ap_ref):
                raise CliError("ap_ref_unknown")

    results: dict[str, object] = {}
    for route_name, template in _DIAGNOSTIC_ROUTES:
        if (route_name in {"site_wids_summary", "site_wids_blacklist_summary"} and
                (client_ref is not None or selected_client_ref is not None or ap_ref is not None or
                 client_select or ap_select or client_timeline)):
            continue
        if not include_policy and route_name in {"band_steering", "rrm_settings", "roaming_settings"}:
            continue
        if (route_name == "site_topology_network_summary" and
                (client_ref is not None or ap_ref is not None or client_select or ap_select)):
            continue
        path = template.format(site_ref=site_ref)
        try:
            payload = fetch(path)
            results[route_name] = _route_projection(route_name, payload, site_ref)
        except CliError as exc:
            results[route_name] = {"status": "error", "error": exc.code,
                                   "capability_status": "unknown"}
    successful = [item for item in results.values()
                  if isinstance(item, dict) and item.get("status") == "ok"]
    client_report: dict[str, object] | None = None
    if selected_client_ref is not None:
        try:
            payload = fetch(
                f"/v1/sites/{site_ref}/clients/{selected_client_ref}/connections")
            connections = _client_connections_response(payload, site_ref, selected_client_ref)
            client_report = {
                "status": "partial" if connections["partial"] else "ok",
                "capability_status": "unknown",
                "selection": client_selection,
                "connections": connections,
            }
            if connections["partial"]:
                any_client_partial = True
            else:
                any_client_partial = False
        except CliError as exc:
            client_report = {
                "status": "error", "error": exc.code,
                "capability_status": "unknown", "selection": client_selection,
                "connections": {"status": "error", "error": exc.code,
                                "capability_status": "unknown"},
            }
            any_client_partial = False
        if client_timeline:
            timelines: dict[str, object] = {}
            for kind in _CLIENT_TIMELINE_KINDS:
                path = f"/v1/sites/{site_ref}/clients/{selected_client_ref}/timeline/{kind}"
                try:
                    timeline_payload = fetch(path)
                    timeline = _client_timeline_response(
                        timeline_payload, site_ref, selected_client_ref, kind)
                    if compact_client_timeline:
                        timeline = summarize_client_timeline(timeline)
                    timelines[kind] = timeline
                    any_client_partial = any_client_partial or timeline["partial"] is True
                except CliError as exc:
                    timelines[kind] = {"status": "error", "error": exc.code,
                                       "capability_status": "unknown"}
                    any_client_partial = True
            client_report["timelines"] = timelines
            if any(item.get("status") == "error" or item.get("partial") is True
                   for item in timelines.values() if isinstance(item, dict)):
                client_report["status"] = "partial"
            health_path = f"/v1/sites/{site_ref}/clients/{selected_client_ref}/health/timeline"
            try:
                health_payload = fetch(health_path)
                health_timeline = _client_health_timeline_response(
                    health_payload, site_ref, selected_client_ref)
                client_report["health_timeline"] = health_timeline
                if health_timeline["partial"]:
                    any_client_partial = True
                    client_report["status"] = "partial"
            except CliError as exc:
                client_report["health_timeline"] = {
                    "status": "error", "error": exc.code,
                    "capability_status": "unknown",
                }
                any_client_partial = True
                client_report["status"] = "partial"
            history_path = f"/v1/sites/{site_ref}/clients/{selected_client_ref}/history"
            try:
                history_payload = fetch(history_path)
                history = _client_history_response(
                    history_payload, site_ref, selected_client_ref)
                client_report["history"] = history
                if history["partial"]:
                    any_client_partial = True
                    client_report["status"] = "partial"
            except CliError as exc:
                client_report["history"] = {
                    "status": "error", "error": exc.code,
                    "capability_status": "unknown",
                }
                any_client_partial = True
                client_report["status"] = "partial"
    else:
        any_client_partial = False
    if not successful and ap_ref is None and client_report is None:
        return {"status": "error", "error": "all_diagnostics_failed",
                **report_site, "capability_status": "unknown", "results": results}
    any_errors = len(successful) != len(results)
    any_partial = any(item.get("partial") is True for item in successful)
    if ap_ref is not None:
        ap_results: dict[str, object] = {}
        ap_routes = (
            ("health", f"/v1/sites/{site_ref}/aps/{ap_ref}/health", _ap_health_response),
            ("timeline", f"/v1/sites/{site_ref}/aps/{ap_ref}/health/timeline", _ap_timeline_response),
            ("radio_config", f"/v1/sites/{site_ref}/aps/{ap_ref}/radio-config",
             _ap_radio_config_response),
            ("rf_scan", f"/v1/sites/{site_ref}/aps/{ap_ref}/rf-scan", _ap_rf_scan_response),
            ("lan_traffic", f"/v1/sites/{site_ref}/aps/{ap_ref}/lan-traffic",
             _ap_lan_traffic_response),
            ("wifi_neighbors", f"/v1/sites/{site_ref}/aps/{ap_ref}/wifi-neighbors",
             _ap_wifi_neighbors_response),
            ("speed_test_results", f"/v1/sites/{site_ref}/aps/{ap_ref}/speed-test-results",
             _ap_speed_test_response),
            ("wired_downlink", f"/v1/sites/{site_ref}/aps/{ap_ref}/wired-downlink",
             _ap_wired_downlink_response),
            ("wired_uplink", f"/v1/sites/{site_ref}/aps/{ap_ref}/wired-uplink",
             _ap_wired_uplink_response),
            ("ports", f"/v1/sites/{site_ref}/aps/{ap_ref}/ports", _ap_ports_response),
            ("lldp_config", f"/v1/sites/{site_ref}/aps/{ap_ref}/lldp-config",
             _ap_lldp_config_response),
            ("port_vlans", f"/v1/sites/{site_ref}/aps/{ap_ref}/port-vlans",
             _ap_port_vlans_response),
            ("wlan_overrides", f"/v1/sites/{site_ref}/aps/{ap_ref}/wlan-overrides",
             _ap_wlan_overrides_response),
        )
        for name, path, projector in ap_routes:
            try:
                payload = fetch(path)
                projected = projector(payload, site_ref, ap_ref)
                ap_results[name] = projected
                any_partial = any_partial or projected["partial"] is True
            except CliError as exc:
                ap_results[name] = {"status": "error", "error": exc.code,
                                    "capability_status": "unknown"}
                any_errors = True
        successful_ap = [item for item in ap_results.values()
                         if isinstance(item, dict) and item.get("status") == "ok"]
        ap_status = ("error" if not successful_ap else
                     "partial" if len(successful_ap) != len(ap_results) or
                     any(item.get("partial") is True for item in successful_ap) else "ok")
        any_partial = any_partial or ap_status == "partial"
        ap_report = {"status": ap_status, "capability_status": "unknown", **ap_results}
    ap_successful = (ap_report is not None and ap_report.get("status") in {"ok", "partial"})
    client_successful = (client_report is not None and client_report.get("status") in {"ok", "partial"})
    if not successful and not ap_successful and not client_successful:
        return {"status": "error", "error": "all_diagnostics_failed",
                **report_site, "capability_status": "unknown", "results": results,
                **({"ap": ap_report} if ap_report is not None else {}),
                **({"client": client_report} if client_report is not None else {})}
    overall_status = "partial" if any_errors or any_partial or any_client_partial or (
        client_report is not None and client_report.get("status") == "error") else "ok"
    report: dict[str, object] = {"status": overall_status, **report_site,
                                 "capability_status": "unknown", "results": results}
    if ap_report is not None:
        report["ap"] = ap_report
    if client_report is not None:
        report["client"] = client_report
    return report


def compare_aps(site_ref: str, ap_refs: list[str], *,
                requester: Callable[[str], object]) -> dict[str, object]:
    """Return a compact side-by-side comparison of two APs using fixed reads."""
    if not isinstance(site_ref, str) or not SITE_REF_PATTERN.fullmatch(site_ref):
        raise CliError("site_ref_invalid")
    if (not isinstance(ap_refs, list) or len(ap_refs) != 2 or ap_refs[0] == ap_refs[1] or
            any(not isinstance(ref, str) or not SITE_REF_PATTERN.fullmatch(ref)
                for ref in ap_refs)):
        raise CliError("ap_selection_invalid")
    if not callable(requester):
        raise CliError("connector_unavailable")

    try:
        sites = requester("/v1/sites")
    except CliError:
        raise CliError("site_inventory_unavailable") from None
    if not _inventory_contains(sites, site_ref):
        raise CliError("site_ref_unknown")
    try:
        devices = requester(f"/v1/sites/{site_ref}/devices")
    except CliError:
        raise CliError("ap_inventory_unavailable") from None
    if not all(_ap_inventory_contains(devices, ref) for ref in ap_refs):
        raise CliError("ap_ref_unknown")

    metric_paths = (
        ("health", "health", _ap_health_response),
        ("radio", "radio-config", _ap_radio_config_response),
        ("rf_scan", "rf-scan", _ap_rf_scan_response),
        ("wifi_neighbors", "wifi-neighbors", _ap_wifi_neighbors_response),
        ("lan_traffic", "lan-traffic", _ap_lan_traffic_response),
    )
    items: list[dict[str, object]] = []
    any_partial = False
    for ap_ref in ap_refs:
        entry: dict[str, object] = {"ap_ref": ap_ref, "status": "ok"}
        for output_name, route_name, project in metric_paths:
            path = f"/v1/sites/{site_ref}/aps/{ap_ref}/{route_name}"
            try:
                payload = requester(path)
                value = project(payload, site_ref, ap_ref)
                if output_name == "health":
                    value = _comparison_health(value)
                elif output_name == "radio":
                    value = _comparison_radio(value)
                elif output_name == "rf_scan":
                    value = _comparison_rf_scan(value)
                elif output_name == "wifi_neighbors":
                    value = _comparison_neighbors(value)
                else:
                    value = {"status": value["status"], "partial": value["partial"],
                             "data": value["data"]}
                entry[output_name] = value
                if value.get("partial") is True:
                    entry["status"] = "partial"
            except CliError as exc:
                error: dict[str, object] = {
                    "status": "error", "error": exc.code,
                    "capability_status": "unknown",
                }
                if type(exc.upstream_http_status) is int:
                    error["upstream_http_status"] = exc.upstream_http_status
                if type(exc.upstream_error_code) is int:
                    error["upstream_error_code"] = exc.upstream_error_code
                entry[output_name] = error
                entry["status"] = "partial"
        any_partial = any_partial or entry["status"] != "ok"
        items.append(entry)
    return {"status": "partial" if any_partial else "ok",
            "resource": "wifi_ap_comparison", "site_ref": site_ref,
            "count": len(items), "items": items, "partial": any_partial}


def _comparison_health(value: dict[str, object]) -> dict[str, object]:
    data = value["data"]
    if not isinstance(data, dict):
        raise CliError("response_invalid")
    compact: dict[str, object] = {}
    for key, item in data.items():
        if key in _AP_HEALTH_INT_FIELDS or key == "supported":
            compact[key] = item
        elif key in _AP_HEALTH_DIMENSIONS and isinstance(item, dict):
            compact[key] = {field: field_value for field, field_value in item.items()
                            if field in _AP_HEALTH_INT_FIELDS | {"supported"}}
    return {"status": value["status"], "partial": value["partial"],
            "window": value["window"], "data": compact}


def _comparison_radio(value: dict[str, object]) -> dict[str, object]:
    data = value["data"]
    bands = data.get("bands") if isinstance(data, dict) else None
    if not isinstance(bands, dict):
        raise CliError("response_invalid")
    fields = {"channel", "channelWidth", "txPower", "radioEnable"}
    compact = {band: {field: setting[field] for field in fields if field in setting}
               for band, setting in bands.items() if isinstance(setting, dict)}
    return {"status": value["status"], "partial": value["partial"],
            "data": {"bands": compact}}


def _comparison_rf_scan(value: dict[str, object]) -> dict[str, object]:
    data = value["data"]
    bands = data.get("bands") if isinstance(data, dict) else None
    if not isinstance(bands, dict):
        raise CliError("response_invalid")
    compact_bands: dict[str, object] = {}
    for band, rows in bands.items():
        if not isinstance(rows, list):
            raise CliError("response_invalid")
        utilization = [row["utilization_percent"] for row in rows
                       if isinstance(row, dict) and _int(row.get("utilization_percent"),
                                                         minimum=0, maximum=100)]
        compact_bands[band] = {"channel_count": len(rows),
                               "max_utilization_percent": max(utilization) if utilization else None}
    scan_status = {key: item for key, item in data.items()
                   if key.endswith("_scan_status") and key.removesuffix("_scan_status") in _RF_BANDS}
    return {"status": value["status"], "partial": value["partial"],
            "data": {"bands": compact_bands, **scan_status}}


def _comparison_neighbors(value: dict[str, object]) -> dict[str, object]:
    data = value.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) > 64:
        raise CliError("response_invalid")
    by_band: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise CliError("response_invalid")
        band, channel, signal = row.get("band"), row.get("channel"), row.get("signal_dbm")
        if (band not in {"2g", "5g", "5g2", "6g"} or
                not _int(channel, minimum=1, maximum=233) or
                not _int(signal, minimum=-120, maximum=0)):
            raise CliError("response_invalid")
        current = by_band.setdefault(band, {"count": 0, "channels": {},
                                             "strongest_signal_dbm": None})
        current["count"] += 1
        channels = current["channels"]
        channels[str(channel)] = channels.get(str(channel), 0) + 1
        strongest = current["strongest_signal_dbm"]
        current["strongest_signal_dbm"] = signal if strongest is None else max(strongest, signal)
    return {"status": value["status"], "partial": value["partial"],
            "data": {"by_band": by_band,
                     "omitted_count": data.get("omitted_count", 0)}}


def main(argv: list[str] | None = None) -> int:
    output_format = "json"
    try:
        args = _parse_args(argv)
        output_format = args.format
        result = run(args.site_ref, args.token_file, args.base_url, args.ap_ref,
                     args.client_select, client_timeline=args.client_timeline,
                     site_auto=args.site_auto, ap_select=args.ap_select,
                     show_ap_names=args.show_ap_names)
    except CliError as exc:
        if output_format == "text":
            print("Gesamtzustand: Fehler\nFehler: " + _text_error(exc.code))
        else:
            print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        # Keep any unforeseen exception details and paths out of terminal output.
        print('{"status":"error","error":"diagnostic_failed"}')
        return 1
    try:
        if output_format == "text":
            print(_render_text(result))
        else:
            print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError):
        print('{"status":"error","error":"diagnostic_failed"}')
        return 1
    return 1 if result.get("status") == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
