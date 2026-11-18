#!/usr/bin/env python3
"""Interactively sign one locally supplied approval request; performs no I/O to controllers."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from typing import Any, Callable, TextIO

try:
    from app.operator_approval import load_operator_key, sign_approval
except ImportError:  # direct execution from tools/
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    from app.operator_approval import load_operator_key, sign_approval


OPS = {"radio", "dns-cache", "ssid", "gateway-ipv6", "poe", "switch-port-status", "band-steering", "rrm-mode", "site-led", "ap-afc", "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "switch-port-name", "site-dpi", "gateway-voip", "gateway-tag-qos", "switch-cable-test", "switch-cable-test-cancel", "controller-radius-proxy"}
REF = re.compile(r"[0-9a-f]{24}\Z")
PID = re.compile(r"[0-9a-f]{48}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
OPERATOR = re.compile(r"op_[0-9a-f]{24}\Z")
FIELDS = {"operation", "plan_id", "target_refs", "before", "target", "before_hash", "digest"}
WARNINGS = {
    "radio": "Funkänderungen können WLAN-Verbindungen unterbrechen.",
    "dns-cache": "DNS-Änderungen können die Namensauflösung beeinflussen.",
    "ssid": "Das Ändern eines WLANs kann Geräte trennen.",
    "gateway-ipv6": "Die IPv6-Änderung kann Verbindungen unterbrechen.",
    "poe": "Eine PoE-Änderung kann angeschlossene Geräte ausschalten.",
    "switch-port-status": "Eine Portänderung kann Geräte, Uplinks oder den Verwaltungszugang trennen.",
    "switch-port-name": "Ein Portname kann in Inventaren, Überwachung und Benachrichtigungen erscheinen.",
    "site-dpi": "DPI kann die Klassifikation beeinflussen; Traffic-Logging kann Nutzungsdaten protokollieren.",
    "gateway-voip": "Die Änderung kann die VoIP-Priorisierung für SIP/RTP beeinflussen; Gateway-Unterstützung und Wirkung sind nicht garantiert.",
    "gateway-tag-qos": "Standortweite Gateway-QoS-Kennzeichnung: mögliche Seiteneffekte auf den Datenverkehr sind nicht vollständig dokumentiert.",
    "band-steering": "Eine Band-Steering-Änderung kann WLAN-Clients kurzzeitig unterbrechen.",
    "rrm-mode": "RF-Optimierung kann WLAN-Funkparameter ändern und Verbindungen unterbrechen.",
    "site-led": "Der tatsächliche Wirkungsumfang der LED-Änderung hängt vom Controller ab.",
    "ap-afc": "Eine AFC-Konfigurationsänderung kann das Verhalten des AP beeinflussen.",
    "site-lldp": "Die Wirkung auf konkrete Geräte hängt vom Controller ab.",
    "ap-channel-limit": "Die konkrete Wirkung der AP-Kanalbegrenzung hängt vom Controller ab.",
    "ap-ofdma": "Wirkung und partielle PATCH-Semantik sind nicht live geprüft; es kann zu Unterbrechungen oder anderen Änderungen kommen.",
    "ap-qos": "Ändert U-APSD für unterstützte AP-Funkbänder; Geräte-/Clientwirkung ist nicht live geprüft.",
    "switch-cable-test": "Startet einen Kabeltest an genau einem Switch-Port; der Port kann währenddessen beeinträchtigt sein.",
    "switch-cable-test-cancel": "Sendet einen Abbruch für einen zuvor freigegebenen Kabeltest; der Endzustand wird separat geprüft.",
    "controller-radius-proxy": "Kann die RADIUS-Authentifizierung von Clients unterbrechen; Nullwerte kennzeichnen in der Vorschau nicht gelieferte optionale Einstellungen.",
}


class ApprovalInputError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ApprovalInputError("duplicate_json_key")
        result[key] = value
    return result


def _request_impl(data: bytes) -> tuple[dict[str, Any], str | None]:
    if len(data) > 32768:
        raise ApprovalInputError("input_too_large")
    try:
        outer = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ApprovalInputError("invalid_json")))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ApprovalInputError("invalid_json") from None
    warning = None
    if isinstance(outer, dict) and "approval_request" in outer:
        request = outer["approval_request"]
        warning_value = outer.get("warning")
        if isinstance(warning_value, str):
            warning = warning_value
    else:
        request = outer
    if not isinstance(request, dict) or set(request) != FIELDS:
        raise ApprovalInputError("request_fields_invalid")
    # Validate the same constrained shapes that approval_plans exports.
    op, plan_id = request["operation"], request["plan_id"]
    refs, before, target, before_hash, digest = (request[k] for k in ("target_refs", "before", "target", "before_hash", "digest"))
    if not isinstance(op, str) or op not in OPS or not isinstance(plan_id, str) or not PID.fullmatch(plan_id):
        raise ApprovalInputError("request_invalid")
    if not isinstance(refs, dict) or not isinstance(before, dict) or not isinstance(target, dict):
        raise ApprovalInputError("request_invalid")
    if not isinstance(before_hash, str) or not HEX64.fullmatch(before_hash) or not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise ApprovalInputError("request_invalid")
    def ref(v: Any) -> bool:
        return isinstance(v, str) and bool(REF.fullmatch(v))
    def exact(obj: dict[str, Any], names: set[str]) -> bool:
        return set(obj) == names
    if op == "controller-radius-proxy":
        fields = {"enable", "port", "requireMessageAuthenticator", "limitProxyState"}
        valid = exact(refs, {}) and exact(before, fields) and exact(target, fields)
        for state in (before, target):
            valid &= (type(state.get("enable")) is bool and type(state.get("port")) is int
                      and -(2**31) <= state["port"] < 2**31 and
                      all(state.get(key) is None or type(state.get(key)) is bool
                          for key in ("requireMessageAuthenticator", "limitProxyState")))
        valid &= before != target
    elif op == "radio":
        valid = exact(refs, {"site_ref", "device_ref"}) and all(ref(v) for v in refs.values())
        valid &= bool(before) and set(before) == set(target) and set(before) <= {"radioSetting2g", "radioSetting5g", "radioSetting5g1", "radioSetting5g2", "radioSetting6g"}
        if not valid:
            raise ApprovalInputError("request_shape_invalid")
        for band in before:
            old, new = before[band], target[band]
            valid &= isinstance(old, dict) and isinstance(new, dict)
            if not valid:
                break
            if set(old) == set(new) == {"txPowerLevel"}:
                valid &= all(type(v["txPowerLevel"]) is int and v["txPowerLevel"] in (0, 1, 2, 4) for v in (old, new))
            elif set(old) == {"channel"} and set(new) in ({"channel"}, {"channel", "freq"}):
                valid &= band in {"radioSetting2g", "radioSetting6g"}
                valid &= type(old["channel"]) is int and 0 <= old["channel"] <= 1024
                if set(new) == {"channel"}:
                    valid &= new["channel"] == "0"
                else:
                    ch, freq = new["channel"], new["freq"]
                    valid &= (isinstance(ch, str) and len(ch) <= 4 and ch.isascii()
                              and ch.isdecimal() and str(int(ch)) == ch and 1 <= int(ch) <= 1024)
                    valid &= type(freq) is int and 2000 <= freq <= 8000
            else:
                valid = False
    elif op == "dns-cache":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        valid &= exact(before, {"enable", "ttl"}) and exact(target, {"enable", "ttl"})
        valid &= all(type(x.get("enable")) is bool and type(x.get("ttl")) is int and 1 <= x["ttl"] <= 86400 for x in (before, target))
    elif op == "ssid":
        valid = exact(refs, {"site_ref", "ssid_ref"}) and all(ref(v) for v in refs.values())
        valid &= exact(before, {"ssidEnable"}) and exact(target, {"ssidEnable"})
        valid &= all(type(x.get("ssidEnable")) is bool for x in (before, target))
    elif op == "gateway-ipv6":
        valid = exact(refs, {"site_ref", "gateway_ref"}) and all(ref(v) for v in refs.values())
        valid &= exact(before, {"enable"}) and exact(target, {"enable"})
        valid &= all(type(x.get("enable")) is bool for x in (before, target))
    elif op == "poe":
        valid = exact(refs, {"site_ref", "switch_ref", "port"}) and ref(refs.get("site_ref")) and ref(refs.get("switch_ref"))
        valid &= type(refs.get("port")) is int and 0 <= refs["port"] <= 4096
        valid &= exact(before, {"poe", "supportPoe", "profileOverrideEnable"}) and exact(target, {"poeMode"})
        valid &= type(before.get("poe")) is int and before.get("poe") in (0, 1) and before.get("supportPoe") is True and before.get("profileOverrideEnable") is True
        valid &= type(target.get("poeMode")) is int and target.get("poeMode") in (0, 1)
    elif op == "switch-port-status":
        valid = exact(refs, {"site_ref", "switch_ref", "port"}) and ref(refs.get("site_ref")) and ref(refs.get("switch_ref"))
        valid &= type(refs.get("port")) is int and 0 <= refs["port"] <= 4096
        valid &= exact(before, {"status"}) and exact(target, {"status"})
        valid &= all(type(x.get("status")) is int and x["status"] in (0, 1) for x in (before, target))
    elif op == "switch-port-name":
        valid = exact(refs, {"site_ref", "switch_ref", "port"})
        valid &= ref(refs.get("site_ref")) and ref(refs.get("switch_ref"))
        valid &= type(refs.get("port")) is int and 0 <= refs["port"] <= 4096
        valid &= exact(before, {"name"}) and exact(target, {"name"})
        valid &= _valid_current_port_name(before.get("name")) and _valid_port_name(target.get("name"))
        valid &= before.get("name") != target.get("name")
    elif op == "site-dpi":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        fields = {"dpi", "loggingTraffic"}
        valid &= exact(before, fields) and exact(target, fields)
        valid &= all(type(state.get(field)) is bool for state in (before, target)
                     for field in fields)
        if valid:
            valid = sum(before[field] != target[field] for field in fields) == 1
    elif op == "gateway-voip":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        fields = {"enable", "sipUdpPort"}
        valid &= exact(before, fields) and exact(target, fields)
        valid &= all(type(state.get("enable")) is bool
                     and type(state.get("sipUdpPort")) is int
                     and 0 <= state["sipUdpPort"] <= 65535
                     for state in (before, target))
        if valid:
            valid = (before["sipUdpPort"] == target["sipUdpPort"]
                     and before["enable"] != target["enable"])
    elif op == "gateway-tag-qos":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        allowed_dscp = {"8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "30", "32", "34", "36", "38", "40", "46", "48", "56"}
        def valid_tag_state(state: dict[str, Any]) -> bool:
            if not exact(state, {"tagConfigList"}):
                return False
            rows = state["tagConfigList"]
            return (type(rows) is list and len(rows) == 4
                    and all(type(row) is dict
                            and exact(row, {"classType", "enable", "dscp"})
                            and type(row["classType"]) is int
                            and row["classType"] in (0, 1, 2, 3)
                            and type(row["enable"]) is bool
                            and type(row["dscp"]) is str and row["dscp"] in allowed_dscp
                            for row in rows)
                    and {row["classType"] for row in rows} == {0, 1, 2, 3})
        valid &= valid_tag_state(before) and valid_tag_state(target)
        if valid:
            old_rows, new_rows = before["tagConfigList"], target["tagConfigList"]
            valid = (all(old["classType"] == new["classType"] and old["dscp"] == new["dscp"]
                         for old, new in zip(old_rows, new_rows))
                     and sum(old["enable"] != new["enable"]
                             for old, new in zip(old_rows, new_rows)) == 1)
    elif op == "band-steering":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        valid &= exact(before, {"mode"}) and exact(target, {"mode"})
        valid &= all(type(x.get("mode")) is int and x["mode"] in (0, 1, 2)
                     for x in (before, target))
    elif op == "rrm-mode":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        fields = {"mode", "timeRangeEnable", "resource", "timeRangeId", "timeRangeAction"}
        valid &= exact(before, fields) and exact(target, fields)
        valid &= all(type(x.get("mode")) is int and x["mode"] in (0, 1)
                     and x.get("timeRangeEnable") is False
                     and type(x.get("resource")) is int and x["resource"] in (0, 1, 2)
                     and type(x.get("timeRangeId")) is str and x["timeRangeId"] == ""
                     and type(x.get("timeRangeAction")) is int and x["timeRangeAction"] in (0, 1)
                     for x in (before, target))
        if valid:
            valid = all(before[field] == target[field] for field in
                        ("timeRangeEnable", "resource", "timeRangeId", "timeRangeAction"))
    elif op == "site-led":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        valid &= exact(before, {"enable"}) and exact(target, {"enable"})
        valid &= all(type(x.get("enable")) is bool for x in (before, target))
    elif op == "ap-afc":
        valid = exact(refs, {"site_ref", "device_ref"}) and all(ref(v) for v in refs.values())
        valid &= exact(before, {"supportAfc", "enable"}) and before.get("supportAfc") is True
        valid &= type(before.get("enable")) is bool
        valid &= exact(target, {"enable"}) and type(target.get("enable")) is bool
    elif op == "site-lldp":
        valid = exact(refs, {"site_ref"}) and ref(refs.get("site_ref"))
        valid &= exact(before, {"enable"}) and exact(target, {"enable"})
        valid &= all(type(x.get("enable")) is bool for x in (before, target))
    elif op == "ap-channel-limit":
        valid = exact(refs, {"site_ref", "device_ref"}) and all(ref(v) for v in refs.values())
        valid &= exact(before, {"supportChannelLimit", "channelLimitType",
                                "defaultInstType5g", "defaultInstType6g"})
        valid &= before.get("supportChannelLimit") is True
        valid &= type(before.get("channelLimitType")) is int and before["channelLimitType"] in (0, 1, 2)
        valid &= type(before.get("defaultInstType5g")) is bool and type(before.get("defaultInstType6g")) is bool
        valid &= exact(target, {"channelLimitType"})
        valid &= type(target.get("channelLimitType")) is int and target["channelLimitType"] in (0, 1, 2)
    elif op == "ap-ofdma":
        valid = exact(refs, {"site_ref", "device_ref"}) and all(ref(v) for v in refs.values())
        fields = {"ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g",
                  "supportOfdma2g", "supportOfdma5g", "supportOfdma5g2", "supportOfdma6g"}
        valid &= exact(before, fields) and exact(target, fields)
        valid &= all(type(state.get(field)) is bool for state in (before, target) for field in fields)
        valid &= not before.get("support5g2") or before.get("support5g")
        enables = {"ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g"}
        if valid:
            changed = [field for field in enables if before[field] != target[field]]
            valid &= len(changed) == 1
            valid &= all(before[field] == target[field] for field in fields - enables)
            if len(changed) == 1:
                support_field = changed[0].replace("ofdmaEnable", "supportOfdma", 1)
                valid &= before[support_field] is True
    elif op == "ap-qos":
        valid = exact(refs, {"site_ref", "device_ref"}) and all(ref(v) for v in refs.values())
        support_fields = {"support2g", "support5g", "support5g2", "support6g"}
        enable_to_support = {"deliveryEnable2g": "support2g", "deliveryEnable5g": "support5g",
                             "deliveryEnable5g2": "support5g2", "deliveryEnable6g": "support6g"}
        valid &= support_fields <= set(before) and support_fields <= set(target)
        valid &= all(type(state.get(field)) is bool for state in (before, target)
                     for field in support_fields)
        if valid:
            valid &= all(before[field] == target[field] for field in support_fields)
            valid &= not before["support5g2"] or before["support5g"]
            supported_enables = {field for field, support in enable_to_support.items()
                                 if before[support] is True}
            fields = support_fields | supported_enables
            valid &= exact(before, fields) and exact(target, fields)
            valid &= all(type(state.get(field)) is bool for state in (before, target)
                         for field in supported_enables)
        enables = set(enable_to_support)
        if valid:
            changed = [field for field in supported_enables if before[field] != target[field]]
            valid &= len(changed) == 1
            valid &= all(before[field] == target[field] for field in fields - enables)
            if len(changed) == 1:
                support = enable_to_support[changed[0]]
                valid &= before[support] is True
    elif op == "switch-cable-test":
        valid = exact(refs, {"site_ref", "switch_ref"}) and all(ref(v) for v in refs.values())
        state_fields = {"copper", "disabled", "editEnable", "stack_port", "upper_port"}
        valid &= exact(before, {"port_state", "logs_digest"})
        valid &= isinstance(before.get("port_state"), dict) and exact(before["port_state"], state_fields)
        valid &= all(type(v) is bool for v in before.get("port_state", {}).values())
        valid &= isinstance(before.get("logs_digest"), str) and bool(HEX64.fullmatch(before["logs_digest"]))
        valid &= exact(target, {"port", "max_runtime_seconds"})
        valid &= type(target.get("port")) is int and 1 <= target.get("port", 0) <= 4096
        valid &= type(target.get("max_runtime_seconds")) is int and target.get("max_runtime_seconds") == 60
    elif op == "switch-cable-test-cancel":
        valid = exact(refs, {"site_ref", "switch_ref"}) and all(ref(v) for v in refs.values())
        valid &= exact(before, {"parent_plan_id", "parent_state"})
        valid &= isinstance(before.get("parent_plan_id"), str) and bool(PID.fullmatch(before.get("parent_plan_id", "")))
        valid &= before.get("parent_state") in {"running", "in_doubt"}
        valid &= exact(target, {"action", "parent_plan_id"}) and target.get("action") == "cancel"
        valid &= target.get("parent_plan_id") == before.get("parent_plan_id")
    if not valid:
        raise ApprovalInputError("request_shape_invalid")
    payload = {k: request[k] for k in FIELDS - {"digest"}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    expected = hashlib.sha256(canonical).hexdigest()
    if not __import__("hmac").compare_digest(expected, digest):
        raise ApprovalInputError("digest_mismatch")
    return request, warning


def _valid_port_name(value: Any) -> bool:
    """Use the strict common subset of the three documented name schemas."""
    if (type(value) is not str or not 1 <= len(value) <= 128 or
            unicodedata.normalize("NFC", value) != value or
            any(unicodedata.category(char).startswith("C") for char in value)):
        return False
    return (not value[0].isspace() and not value[-1].isspace() and
            "?" not in value and '"' not in value)


def _valid_current_port_name(value: Any) -> bool:
    """Accept bounded legacy before-labels while rejecting display controls."""
    if (type(value) is not str or len(value) > 128 or
            unicodedata.normalize("NFC", value) != value or
            any(unicodedata.category(char).startswith("C") for char in value)):
        return False
    return not value or (not value[0].isspace() and not value[-1].isspace())


def _request(data: bytes) -> tuple[dict[str, Any], str | None]:
    """Collapse malformed input failures to a safe, stable error."""
    try:
        return _request_impl(data)
    except ApprovalInputError:
        raise
    except Exception:
        # JSON-derived structures can trigger incidental KeyError/TypeError or
        # integer conversion failures. Never expose their details or traceback.
        raise ApprovalInputError("request_invalid") from None


def approve(data: bytes, tty: TextIO, *, key_file: str, operator_id: str,
            expires_in: int = 60, now: int | None = None,
            key_loader: Callable[[str], bytes] = load_operator_key,
            signer: Callable[..., dict[str, Any]] = sign_approval) -> dict[str, Any]:
    if not getattr(tty, "isatty", lambda: False)():
        raise ApprovalInputError("tty_required")
    if not isinstance(operator_id, str) or not OPERATOR.fullmatch(operator_id):
        raise ApprovalInputError("operator_id_invalid")
    if type(expires_in) is not int or not 1 <= expires_in <= 120:
        raise ApprovalInputError("expiry_invalid")
    request, warning = _request(data)
    summary = {k: request[k] for k in FIELDS - {"digest"}}
    tty.write("Freigabe anfordern (HMAC weist nur Schlüsselbesitz nach):\n")
    tty.write(json.dumps(summary, ensure_ascii=True, sort_keys=True, indent=2) + "\n")
    tty.write("Achtung: " + WARNINGS[request["operation"]] + "\n")
    if (request["operation"] == "site-dpi" and
            request["target"].get("loggingTraffic") is True):
        tty.write("Achtung: loggingTraffic=true kann Nutzungsdaten protokollieren.\n")
    if request["operation"] in {"switch-cable-test", "switch-cable-test-cancel"}:
        tty.write("Achtung: Der Switch-Kabeltest kann Portverkehr unterbrechen. Timeout oder fehlende Zuordnung bleibt unklar; niemals automatisch wiederholen.\n")
    if warning:
        tty.write("Warnung: " + json.dumps(warning, ensure_ascii=True) + "\n")
    tty.write("Zum Signieren exakt FREIGEBEN eingeben: ")
    tty.flush()
    response = tty.readline()
    if response.rstrip("\r\n") != "FREIGEBEN":
        raise ApprovalInputError("approval_declined")
    current = int(time.time()) if now is None else now
    if type(current) is not int or current < 0:
        raise ApprovalInputError("time_invalid")
    key = key_loader(key_file)
    return signer(key, operation=request["operation"], plan_id=request["plan_id"],
                  plan_digest=request["digest"], operator_id=operator_id,
                  expires_at=current + expires_in, now=current)


class _ApprovalTerminal:
    """Combine separate readable and writable streams for a real terminal."""

    def __init__(self, reader: TextIO, writer: TextIO) -> None:
        self.reader = reader
        self.writer = writer

    def isatty(self) -> bool:
        return self.reader.isatty() and self.writer.isatty()

    def write(self, value: str) -> int:
        return self.writer.write(value)

    def flush(self) -> None:
        self.writer.flush()

    def readline(self) -> str:
        return self.reader.readline()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--expires-in", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        with open("/dev/tty", "r", encoding="utf-8", buffering=1) as tty_in, \
                open("/dev/tty", "w", encoding="utf-8", buffering=1) as tty_out:
            tty = _ApprovalTerminal(tty_in, tty_out)
            result = approve(sys.stdin.buffer.read(32769), tty, key_file=args.key_file,
                             operator_id=args.operator_id, expires_in=args.expires_in)
        sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
        return 0
    except (ApprovalInputError, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, ApprovalInputError) else "approval_failed"
        sys.stderr.write(code + "\n")
        return 2
    except Exception:
        sys.stderr.write("approval_failed\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
