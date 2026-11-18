"""Create redacted, immutable approval snapshots from pending change plans.

This module is deliberately read-only: it inspects a manager's in-memory plan
under its lock and returns only explicitly supported fields.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

try:
    from .ap_qos import ApQosError, normalize_ap_qos_change_state
except ImportError:
    from ap_qos import ApQosError, normalize_ap_qos_change_state


class ApprovalPlanError(ValueError):
    """A plan cannot safely be represented as an approval snapshot."""


_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_OPERATIONS = {"radio", "dns-cache", "ssid", "gateway-ipv6", "poe", "switch-port-status", "band-steering", "rrm-mode", "site-led", "ap-afc", "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "switch-port-name", "site-dpi", "gateway-voip", "gateway-tag-qos", "switch-cable-test", "switch-cable-test-cancel", "controller-radius-proxy"}
_BANDS = {"radioSetting2g", "radioSetting5g", "radioSetting5g1", "radioSetting5g2", "radioSetting6g"}
_TAG_DSCP = frozenset({"8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "30", "32", "34", "36", "38", "40", "46", "48", "56"})


def _ref(value: Any) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise ApprovalPlanError("plan_invalid")
    return value


def _state(operation: str, value: Any, *, target: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApprovalPlanError("plan_invalid")
    if operation == "controller-radius-proxy":
        fields = {"enable", "port", "requireMessageAuthenticator", "limitProxyState"}
        if (set(value) != fields or type(value["enable"]) is not bool or
                type(value["port"]) is not int or not -(2**31) <= value["port"] < 2**31 or
                any(value[key] is not None and type(value[key]) is not bool
                    for key in ("requireMessageAuthenticator", "limitProxyState"))):
            raise ApprovalPlanError("plan_invalid")
        return {key: value[key] for key in sorted(fields)}
    if operation == "dns-cache":
        if set(value) != {"enable", "ttl"} or type(value["enable"]) is not bool or type(value["ttl"]) is not int or not 1 <= value["ttl"] <= 86400:
            raise ApprovalPlanError("plan_invalid")
        return {"enable": value["enable"], "ttl": value["ttl"]}
    if operation == "ssid":
        if set(value) != {"ssidEnable"} or type(value["ssidEnable"]) is not bool:
            raise ApprovalPlanError("plan_invalid")
        return {"ssidEnable": value["ssidEnable"]}
    if operation == "gateway-ipv6":
        if set(value) != {"enable"} or type(value["enable"]) is not bool:
            raise ApprovalPlanError("plan_invalid")
        return {"enable": value["enable"]}
    if operation == "poe":
        expected = {"poeMode"} if target else {"poe", "supportPoe", "profileOverrideEnable"}
        if set(value) != expected:
            raise ApprovalPlanError("plan_invalid")
        if target:
            mode = value["poeMode"]
            if type(mode) is not int or mode not in (0, 1):
                raise ApprovalPlanError("plan_invalid")
            return {"poeMode": mode}
        if (type(value["poe"]) is not int or value["poe"] not in (0, 1)
                or value["supportPoe"] is not True or value["profileOverrideEnable"] is not True):
            raise ApprovalPlanError("plan_invalid")
        return {"poe": value["poe"], "supportPoe": True, "profileOverrideEnable": True}
    if operation == "switch-port-status":
        if set(value) != {"status"} or type(value["status"]) is not int or value["status"] not in (0, 1):
            raise ApprovalPlanError("plan_invalid")
        return {"status": value["status"]}
    if operation == "switch-port-name":
        validator = _valid_port_name if target else _valid_current_port_name
        if set(value) != {"name"} or not validator(value.get("name")):
            raise ApprovalPlanError("plan_invalid")
        return {"name": value["name"]}
    if operation == "site-dpi":
        expected = {"dpi", "loggingTraffic"}
        if set(value) != expected or any(type(value[field]) is not bool for field in expected):
            raise ApprovalPlanError("plan_invalid")
        return {"dpi": value["dpi"], "loggingTraffic": value["loggingTraffic"]}
    if operation == "gateway-voip":
        expected = {"enable", "sipUdpPort"}
        if (set(value) != expected or type(value["enable"]) is not bool
                or type(value["sipUdpPort"]) is not int
                or not 0 <= value["sipUdpPort"] <= 65535):
            raise ApprovalPlanError("plan_invalid")
        return {"enable": value["enable"], "sipUdpPort": value["sipUdpPort"]}
    if operation == "gateway-tag-qos":
        if set(value) != {"tagConfigList"}:
            raise ApprovalPlanError("plan_invalid")
        rows = value["tagConfigList"]
        if type(rows) is not list or len(rows) != 4:
            raise ApprovalPlanError("plan_invalid")
        clean = []
        classes = []
        for row in rows:
            if (type(row) is not dict or set(row) != {"classType", "enable", "dscp"}
                    or type(row["classType"]) is not int or row["classType"] not in (0, 1, 2, 3)
                    or type(row["enable"]) is not bool or type(row["dscp"]) is not str
                    or row["dscp"] not in _TAG_DSCP):
                raise ApprovalPlanError("plan_invalid")
            classes.append(row["classType"])
            clean.append({"classType": row["classType"], "enable": row["enable"], "dscp": row["dscp"]})
        if set(classes) != {0, 1, 2, 3}:
            raise ApprovalPlanError("plan_invalid")
        return {"tagConfigList": clean}
    if operation == "band-steering":
        if set(value) != {"mode"} or type(value["mode"]) is not int or value["mode"] not in (0, 1, 2):
            raise ApprovalPlanError("plan_invalid")
        return {"mode": value["mode"]}
    if operation == "rrm-mode":
        expected = {"mode", "timeRangeEnable", "resource", "timeRangeId", "timeRangeAction"}
        if set(value) != expected:
            raise ApprovalPlanError("plan_invalid")
        if (type(value["mode"]) is not int or value["mode"] not in (0, 1)
                or value["timeRangeEnable"] is not False
                or type(value["resource"]) is not int or value["resource"] not in (0, 1, 2)
                or type(value["timeRangeId"]) is not str or value["timeRangeId"] != ""
                or type(value["timeRangeAction"]) is not int or value["timeRangeAction"] not in (0, 1)):
            raise ApprovalPlanError("plan_invalid")
        return {key: value[key] for key in ("mode", "timeRangeEnable", "resource", "timeRangeId", "timeRangeAction")}
    if operation == "site-led":
        if set(value) != {"enable"} or type(value["enable"]) is not bool:
            raise ApprovalPlanError("plan_invalid")
        return {"enable": value["enable"]}
    if operation == "ap-afc":
        if target:
            if set(value) != {"enable"} or type(value["enable"]) is not bool:
                raise ApprovalPlanError("plan_invalid")
            return {"enable": value["enable"]}
        if (set(value) != {"supportAfc", "enable"} or value["supportAfc"] is not True
                or type(value["enable"]) is not bool):
            raise ApprovalPlanError("plan_invalid")
        return {"supportAfc": True, "enable": value["enable"]}
    if operation == "site-lldp":
        if set(value) != {"enable"} or type(value["enable"]) is not bool:
            raise ApprovalPlanError("plan_invalid")
        return {"enable": value["enable"]}
    if operation == "ap-qos":
        try:
            return normalize_ap_qos_change_state(value)
        except ApQosError:
            raise ApprovalPlanError("plan_invalid")
    if operation == "ap-channel-limit":
        if target:
            if set(value) != {"channelLimitType"} or type(value["channelLimitType"]) is not int or value["channelLimitType"] not in (0, 1, 2):
                raise ApprovalPlanError("plan_invalid")
            return {"channelLimitType": value["channelLimitType"]}
        expected = {"supportChannelLimit", "channelLimitType", "defaultInstType5g", "defaultInstType6g"}
        if (set(value) != expected or value["supportChannelLimit"] is not True
                or type(value["channelLimitType"]) is not int or value["channelLimitType"] not in (0, 1, 2)
                or type(value["defaultInstType5g"]) is not bool
                or type(value["defaultInstType6g"]) is not bool):
            raise ApprovalPlanError("plan_invalid")
        return {"supportChannelLimit": True, "channelLimitType": value["channelLimitType"],
                "defaultInstType5g": value["defaultInstType5g"],
                "defaultInstType6g": value["defaultInstType6g"]}
    if operation == "ap-ofdma":
        expected = {
            "ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g",
            "supportOfdma2g", "supportOfdma5g", "supportOfdma5g2", "supportOfdma6g",
        }
        if set(value) != expected or any(type(item) is not bool for item in value.values()):
            raise ApprovalPlanError("plan_invalid")
        return {key: value[key] for key in (
            "ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g",
            "supportOfdma2g", "supportOfdma5g", "supportOfdma5g2", "supportOfdma6g",
        )}
    if operation == "switch-cable-test":
        if target:
            if (set(value) != {"port", "max_runtime_seconds"} or
                    type(value["port"]) is not int or not 1 <= value["port"] <= 4096 or
                    type(value["max_runtime_seconds"]) is not int or
                    value["max_runtime_seconds"] != 60):
                raise ApprovalPlanError("plan_invalid")
            return {"port": value["port"], "max_runtime_seconds": 60}
        fields = {"port_state", "logs_digest"}
        if set(value) != fields or type(value["port_state"]) is not dict or not isinstance(value["logs_digest"], str) or not _HASH.fullmatch(value["logs_digest"]):
            raise ApprovalPlanError("plan_invalid")
        state_fields = {"copper", "disabled", "editEnable", "stack_port", "upper_port"}
        if set(value["port_state"]) != state_fields or any(type(item) is not bool for item in value["port_state"].values()):
            raise ApprovalPlanError("plan_invalid")
        return {"port_state": dict(value["port_state"]), "logs_digest": value["logs_digest"]}
    if operation == "switch-cable-test-cancel":
        if target:
            if (set(value) != {"action", "parent_plan_id"} or value["action"] != "cancel" or
                    type(value["parent_plan_id"]) is not str or not _PLAN_ID.fullmatch(value["parent_plan_id"])):
                raise ApprovalPlanError("plan_invalid")
            return {"action": "cancel", "parent_plan_id": value["parent_plan_id"]}
        if (set(value) != {"parent_plan_id", "parent_state"} or
                type(value["parent_plan_id"]) is not str or not _PLAN_ID.fullmatch(value["parent_plan_id"]) or
                value["parent_state"] not in {"running", "in_doubt"}):
            raise ApprovalPlanError("plan_invalid")
        return {"parent_plan_id": value["parent_plan_id"], "parent_state": value["parent_state"]}
    raise ApprovalPlanError("operation_invalid")


def _valid_port_name(value: object) -> bool:
    """Validate the strictest documented cross-controller port-name shape."""
    if (type(value) is not str or not 1 <= len(value) <= 128 or
            unicodedata.normalize("NFC", value) != value or
            any(unicodedata.category(char).startswith("C") for char in value)):
        return False
    # The hardware/CBC schemas require non-space endpoints and exclude '?' and
    # double quote throughout; ER is less restrictive, so use the intersection.
    return (not value[0].isspace() and not value[-1].isspace() and
            "?" not in value and '"' not in value)


def _valid_current_port_name(value: object) -> bool:
    """Accept a bounded legacy before-label that can still be displayed safely."""
    if (type(value) is not str or len(value) > 128 or
            unicodedata.normalize("NFC", value) != value or
            any(unicodedata.category(char).startswith("C") for char in value)):
        return False
    return not value or (not value[0].isspace() and not value[-1].isspace())


def _radio(previous: Any, changes: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(previous, dict) or not previous or not isinstance(changes, dict) or set(previous) != set(changes):
        raise ApprovalPlanError("plan_invalid")
    before_clean: dict[str, Any] = {}
    target_clean: dict[str, Any] = {}
    for band, old in previous.items():
        new = changes[band]
        if band not in _BANDS or not isinstance(old, dict) or not isinstance(new, dict):
            raise ApprovalPlanError("plan_invalid")
        if set(old) == {"txPowerLevel"} and set(new) == {"txPowerLevel"}:
            if any(type(x["txPowerLevel"]) is not int or x["txPowerLevel"] not in (0, 1, 2, 4) for x in (old, new)):
                raise ApprovalPlanError("plan_invalid")
            before_clean[band], target_clean[band] = {"txPowerLevel": old["txPowerLevel"]}, {"txPowerLevel": new["txPowerLevel"]}
        elif set(old) == {"channel"}:
            channel = old["channel"]
            if type(channel) is not int or not 0 <= channel <= 1024 or band not in {"radioSetting2g", "radioSetting6g"}:
                raise ApprovalPlanError("plan_invalid")
            if set(new) == {"channel"} and new["channel"] == "0":
                clean = {"channel": "0"}
            elif set(new) == {"channel", "freq"}:
                ch, freq = new["channel"], new["freq"]
                if (not isinstance(ch, str) or not ch.isascii() or not ch.isdecimal() or str(int(ch)) != ch
                        or not 1 <= int(ch) <= 1024 or type(freq) is not int or not 2000 <= freq <= 8000):
                    raise ApprovalPlanError("plan_invalid")
                clean = {"channel": ch, "freq": freq}
            else:
                raise ApprovalPlanError("plan_invalid")
            before_clean[band], target_clean[band] = {"channel": channel}, clean
        else:
            raise ApprovalPlanError("plan_invalid")
    return before_clean, target_clean


def build_approval_summary(operation: str, plan_id: str, manager: Any) -> dict[str, Any]:
    """Return a canonical redacted snapshot and its SHA-256 digest.

    The returned object is a detached snapshot; neither the manager nor plan is
    modified. The caller should retain the digest with any subsequent approval.
    """
    if operation not in _OPERATIONS or not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
        raise ApprovalPlanError("request_invalid")
    lock, plans = getattr(manager, "lock", None), getattr(manager, "plans", None)
    if lock is None or not isinstance(plans, dict):
        raise ApprovalPlanError("manager_invalid")
    with lock:
        plan = plans.get(plan_id)
        if not isinstance(plan, dict) or plan.get("state") != "pending":
            raise ApprovalPlanError("plan_unavailable")
        if operation == "controller-radius-proxy":
            if set(plan) != {"before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            if before == target:
                raise ApprovalPlanError("plan_invalid")
        elif operation == "radio":
            if set(plan) != {"target", "changes", "before_hash", "has_catalog", "previous", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs = plan["target"]
            if not isinstance(refs, (tuple, list)) or len(refs) != 2:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(refs[0]), "device_ref": _ref(refs[1])}
            before, target = _radio(plan["previous"], plan["changes"])
        elif operation == "dns-cache":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before, target = _state(operation, plan["before"], target=False), _state(operation, plan["target"], target=True)
        elif operation == "ssid":
            if set(plan) != {"target_refs", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs = plan["target_refs"]
            if not isinstance(refs, (tuple, list)) or len(refs) != 2:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(refs[0]), "ssid_ref": _ref(refs[1])}
            before, target = _state(operation, plan["before"], target=False), _state(operation, plan["target"], target=True)
        elif operation == "gateway-ipv6":
            if set(plan) != {"site_ref", "gateway_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]), "gateway_ref": _ref(plan["gateway_ref"])}
            before, target = _state(operation, plan["before"], target=False), _state(operation, plan["target"], target=True)
        elif operation == "band-steering":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
        elif operation == "rrm-mode":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            if any(before[field] != target[field] for field in
                   ("timeRangeEnable", "resource", "timeRangeId", "timeRangeAction")):
                raise ApprovalPlanError("plan_invalid")
        elif operation == "site-led":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
        elif operation == "ap-afc":
            if set(plan) != {"site_ref", "device_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]),
                        "device_ref": _ref(plan["device_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
        elif operation == "site-lldp":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
        elif operation == "ap-channel-limit":
            if set(plan) != {"site_ref", "device_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]),
                        "device_ref": _ref(plan["device_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
        elif operation == "ap-ofdma":
            if set(plan) != {"site_ref", "device_ref", "before", "target", "field",
                             "patch_before", "patch_target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]),
                        "device_ref": _ref(plan["device_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            enable_fields = {"ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g"}
            changed = [field for field in enable_fields if before[field] != target[field]]
            if (len(changed) != 1 or
                    any(before[field] != target[field] for field in set(before) - enable_fields)):
                raise ApprovalPlanError("plan_invalid")
            support_field = changed[0].replace("ofdmaEnable", "supportOfdma", 1)
            if (before[support_field] is not True or plan["field"] != changed[0] or
                    not isinstance(plan["patch_before"], dict) or
                    set(plan["patch_before"]) != {changed[0]} or
                    type(plan["patch_before"][changed[0]]) is not bool or
                    plan["patch_before"][changed[0]] != before[changed[0]] or
                    not isinstance(plan["patch_target"], dict) or
                    set(plan["patch_target"]) != {changed[0]} or
                    type(plan["patch_target"][changed[0]]) is not bool or
                    plan["patch_target"][changed[0]] != target[changed[0]]):
                raise ApprovalPlanError("plan_invalid")
        elif operation == "ap-qos":
            if set(plan) != {"site_ref", "device_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]),
                        "device_ref": _ref(plan["device_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            if set(before) != set(target):
                raise ApprovalPlanError("plan_invalid")
            changed = [field for field in ("deliveryEnable2g", "deliveryEnable5g",
                        "deliveryEnable5g2", "deliveryEnable6g")
                       if field in before and before[field] != target[field]]
            if (len(changed) != 1 or
                    any(before[field] != target[field] for field in set(before) - set(changed))):
                raise ApprovalPlanError("plan_invalid")
        elif operation == "switch-port-name":
            if set(plan) != {"site_ref", "switch_ref", "port", "before", "target",
                             "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            if type(plan["port"]) is not int or not 0 <= plan["port"] <= 4096:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]),
                        "switch_ref": _ref(plan["switch_ref"]),
                        "port": plan["port"]}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            if before["name"] == target["name"]:
                raise ApprovalPlanError("plan_invalid")
        elif operation == "switch-cable-test":
            required = {"operation", "site_ref", "switch_ref", "port", "before", "target",
                        "before_hash", "baseline_logs", "expires", "state", "journaled"}
            if set(plan) != required or plan.get("state") != "pending" or plan.get("journaled") is not False:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]), "switch_ref": _ref(plan["switch_ref"])}
            if type(plan["port"]) is not int or not 1 <= plan["port"] <= 4096:
                raise ApprovalPlanError("plan_invalid")
            before, target = _state(operation, plan["before"], target=False), _state(operation, plan["target"], target=True)
            if target["port"] != plan["port"] or type(plan["baseline_logs"]) is not list or len(plan["baseline_logs"]) > 64 or any(type(item) is not str or not _HASH.fullmatch(item) for item in plan["baseline_logs"]):
                raise ApprovalPlanError("plan_invalid")
        elif operation == "switch-cable-test-cancel":
            required = {"operation", "site_ref", "switch_ref", "parent_plan_id", "before", "target",
                        "before_hash", "expires", "state", "journaled"}
            if set(plan) != required or plan.get("state") != "pending" or plan.get("journaled") is not False:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]), "switch_ref": _ref(plan["switch_ref"])}
            if type(plan["parent_plan_id"]) is not str or not _PLAN_ID.fullmatch(plan["parent_plan_id"]):
                raise ApprovalPlanError("plan_invalid")
            before, target = _state(operation, plan["before"], target=False), _state(operation, plan["target"], target=True)
            if before["parent_plan_id"] != plan["parent_plan_id"] or target["parent_plan_id"] != plan["parent_plan_id"]:
                raise ApprovalPlanError("plan_invalid")
        elif operation == "site-dpi":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            if sum(before[field] != target[field] for field in ("dpi", "loggingTraffic")) != 1:
                raise ApprovalPlanError("plan_invalid")
        elif operation == "gateway-voip":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            if (before["sipUdpPort"] != target["sipUdpPort"]
                    or before["enable"] == target["enable"]):
                raise ApprovalPlanError("plan_invalid")
        elif operation == "gateway-tag-qos":
            if set(plan) != {"site_ref", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"])}
            before = _state(operation, plan["before"], target=False)
            target = _state(operation, plan["target"], target=True)
            old_rows, new_rows = before["tagConfigList"], target["tagConfigList"]
            if (len(old_rows) != len(new_rows)
                    or any(old["classType"] != new["classType"] or old["dscp"] != new["dscp"]
                           for old, new in zip(old_rows, new_rows))
                    or sum(old["enable"] != new["enable"] for old, new in zip(old_rows, new_rows)) != 1):
                raise ApprovalPlanError("plan_invalid")
        else:
            if set(plan) != {"site_ref", "switch_ref", "port", "before", "target", "before_hash", "expires", "state"}:
                raise ApprovalPlanError("plan_invalid")
            if type(plan["port"]) is not int or not 0 <= plan["port"] <= 4096:
                raise ApprovalPlanError("plan_invalid")
            refs_out = {"site_ref": _ref(plan["site_ref"]), "switch_ref": _ref(plan["switch_ref"]), "port": plan["port"]}
            before, target = _state(operation, plan["before"], target=False), _state(operation, plan["target"], target=True)
        before_hash = plan.get("before_hash")
        if not isinstance(before_hash, str) or not _HASH.fullmatch(before_hash):
            raise ApprovalPlanError("plan_invalid")
        payload = {"operation": operation, "plan_id": plan_id, "target_refs": refs_out,
                   "before": before, "target": target, "before_hash": before_hash}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
        return {**payload, "digest": hashlib.sha256(encoded).hexdigest()}
