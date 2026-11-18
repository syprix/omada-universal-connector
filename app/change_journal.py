"""Optional, local append-only journal for connector change-plan dispatches.

The journal records only allowlisted plan metadata and lifecycle events. It has
no controller or write callback. A durable dispatch intent is conservative:
after recovery it is unresolved and must never be replayed automatically.
"""
from __future__ import annotations

import copy
import errno
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import re
import stat
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

try:
    from .ap_qos import ApQosError, normalize_ap_qos_change_state
except ImportError:
    from ap_qos import ApQosError, normalize_ap_qos_change_state


class ChangeJournalError(RuntimeError):
    """Stable, non-sensitive journal error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_SCHEMA_VERSION = 1
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_RECORD_BYTES = 8192
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_REF = re.compile(r"[0-9a-f]{24}\Z")
_BINDING = re.compile(r"[0-9a-f]{64}\Z")
_CONTROLLER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_CANONICAL_CHANNEL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_ZERO_HASH = "0" * 64
_OPERATIONS = frozenset({"radio", "dns-cache", "ssid", "gateway-ipv6", "poe",
                         "switch-port-status", "band-steering", "rrm-mode", "site-led", "ap-afc",
                         "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "switch-port-name",
                         "site-dpi", "gateway-voip", "gateway-tag-qos",
                         "switch-cable-test", "switch-cable-test-cancel",
                         "controller-radius-proxy"})
ALLOWED_JOURNAL_OPERATIONS = _OPERATIONS
_RADIO_BANDS = frozenset({
    "radioSetting2g", "radioSetting5g", "radioSetting5g1",
    "radioSetting5g2", "radioSetting6g",
})
_RADIO_POWER = frozenset({0, 1, 2, 4})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ChangeJournalError("journal_schema_invalid") from None


def _reject_constant(_value: str) -> None:
    raise ValueError("nonstandard_json_constant")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _opaque_ref(value: object) -> bool:
    return isinstance(value, str) and _REF.fullmatch(value) is not None


def _exact_state(value: object, fields: frozenset[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def _radio_fields(value: object, *, target: bool) -> bool:
    if not isinstance(value, dict) or not value or len(value) > len(_RADIO_BANDS):
        return False
    for band, fields in value.items():
        if band not in _RADIO_BANDS or not isinstance(fields, dict):
            return False
        if set(fields) == {"txPowerLevel"}:
            if type(fields["txPowerLevel"]) is not int or fields["txPowerLevel"] not in _RADIO_POWER:
                return False
        elif set(fields) == {"channel"} and not target:
            channel = fields["channel"]
            if type(channel) is not int or not 0 <= channel <= 1024:
                return False
        elif target and set(fields) == {"channel"}:
            if fields["channel"] != "0":
                return False
        elif target and set(fields) == {"channel", "freq"}:
            channel, freq = fields["channel"], fields["freq"]
            if (not isinstance(channel, str) or not _CANONICAL_CHANNEL.fullmatch(channel) or
                    len(channel) > 4 or not 1 <= int(channel) <= 1024 or type(freq) is not int or
                    not 2000 <= freq <= 8000):
                return False
        else:
            return False
    return True


def _validate_plan(operation: object, plan_id: object, target_refs: object,
                   before: object, target: object) -> dict[str, object]:
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        raise ChangeJournalError("journal_schema_invalid")
    if not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
        raise ChangeJournalError("plan_id_invalid")
    if not isinstance(target_refs, dict):
        raise ChangeJournalError("journal_schema_invalid")

    refs: dict[str, object]
    if operation == "controller-radius-proxy":
        if target_refs:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {}
        fields = frozenset({"enable", "port", "requireMessageAuthenticator", "limitProxyState"})
        valid = _exact_state(before, fields) and _exact_state(target, fields)
        if valid:
            valid = (all(type(state["enable"]) is bool and type(state["port"]) is int
                         and -(2**31) <= state["port"] < 2**31 and
                         all(state[key] is None or type(state[key]) is bool
                             for key in ("requireMessageAuthenticator", "limitProxyState"))
                         for state in (before, target)) and before != target)
    elif operation == "radio":
        if set(target_refs) != {"site_ref", "device_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "device_ref": target_refs["device_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _radio_fields(before, target=False) and _radio_fields(target, target=True)
        if valid:
            valid = set(before) == set(target)
            for band in before:
                valid = valid and set(before[band]) == (set(target[band]) & set(before[band]))
    elif operation == "dns-cache":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, frozenset({"enable", "ttl"}))
        valid = valid and _exact_state(target, frozenset({"enable", "ttl"}))
        if valid:
            valid = all(type(value["enable"]) is bool and type(value["ttl"]) is int
                        and 1 <= value["ttl"] <= 86400 for value in (before, target))
    elif operation == "ssid":
        if set(target_refs) != {"site_ref", "ssid_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "ssid_ref": target_refs["ssid_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _exact_state(before, frozenset({"ssidEnable"}))
        valid = valid and _exact_state(target, frozenset({"ssidEnable"}))
        if valid:
            valid = type(before["ssidEnable"]) is bool and type(target["ssidEnable"]) is bool
    elif operation == "gateway-ipv6":
        if set(target_refs) != {"site_ref", "gateway_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "gateway_ref": target_refs["gateway_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _exact_state(before, frozenset({"enable"}))
        valid = valid and _exact_state(target, frozenset({"enable"}))
        if valid:
            valid = type(before["enable"]) is bool and type(target["enable"]) is bool
    elif operation == "poe":
        if set(target_refs) != {"site_ref", "switch_ref", "port"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "switch_ref": target_refs["switch_ref"],
                "port": target_refs["port"]}
        valid = (_opaque_ref(refs["site_ref"]) and _opaque_ref(refs["switch_ref"]) and
                 type(refs["port"]) is int and 0 <= refs["port"] <= 4096)
        valid = valid and _exact_state(before, frozenset({"poeMode"}))
        valid = valid and _exact_state(target, frozenset({"poeMode"}))
        if valid:
            valid = (type(before["poeMode"]) is int and before["poeMode"] in (0, 1) and
                     type(target["poeMode"]) is int and target["poeMode"] in (0, 1))
    elif operation == "switch-port-status":
        if set(target_refs) != {"site_ref", "switch_ref", "port"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "switch_ref": target_refs["switch_ref"],
                "port": target_refs["port"]}
        valid = (_opaque_ref(refs["site_ref"]) and _opaque_ref(refs["switch_ref"]) and
                 type(refs["port"]) is int and 0 <= refs["port"] <= 4096)
        valid = valid and _exact_state(before, frozenset({"status"}))
        valid = valid and _exact_state(target, frozenset({"status"}))
        if valid:
            valid = (type(before["status"]) is int and before["status"] in (0, 1) and
                     type(target["status"]) is int and target["status"] in (0, 1))
    elif operation == "switch-port-name":
        if set(target_refs) != {"site_ref", "switch_ref", "port"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "switch_ref": target_refs["switch_ref"],
                "port": target_refs["port"]}
        valid = (_opaque_ref(refs["site_ref"]) and _opaque_ref(refs["switch_ref"]) and
                 type(refs["port"]) is int and 0 <= refs["port"] <= 4096)
        # Port labels are free text and must never be persisted in this journal.
        # No checksum is accepted either: ordinary hashes of short labels permit
        # offline dictionary guesses. Recovery is deliberately blind/in-doubt.
        redacted = frozenset({"name_redacted"})
        valid = valid and _exact_state(before, redacted) and _exact_state(target, redacted)
        if valid:
            valid = before["name_redacted"] is True and target["name_redacted"] is True
    elif operation == "switch-cable-test":
        if set(target_refs) != {"site_ref", "switch_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "switch_ref": target_refs["switch_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _exact_state(before, frozenset({"port_state_digest", "logs_digest"}))
        valid = valid and all(isinstance(value, str) and _BINDING.fullmatch(value)
                              for value in before.values())
        valid = valid and _exact_state(target, frozenset({"port", "max_runtime_seconds"}))
        if valid:
            valid = (type(target["port"]) is int and 1 <= target["port"] <= 4096 and
                     type(target["max_runtime_seconds"]) is int and
                     1 <= target["max_runtime_seconds"] <= 60)
    elif operation == "switch-cable-test-cancel":
        if set(target_refs) != {"site_ref", "switch_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "switch_ref": target_refs["switch_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _exact_state(before, frozenset({"parent_plan_id"}))
        valid = valid and isinstance(before["parent_plan_id"], str)
        valid = valid and _PLAN_ID.fullmatch(before["parent_plan_id"]) is not None
        valid = valid and _exact_state(target, frozenset({"action"}))
        valid = valid and target.get("action") == "cancel"
    elif operation == "site-dpi":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        fields = frozenset({"dpi", "loggingTraffic"})
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, fields) and _exact_state(target, fields)
        if valid:
            valid = all(type(state[field]) is bool for state in (before, target)
                        for field in fields)
            if valid:
                valid = sum(before[field] != target[field] for field in fields) == 1
    elif operation == "gateway-voip":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        fields = frozenset({"enable", "sipUdpPort"})
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, fields) and _exact_state(target, fields)
        if valid:
            valid = (type(before["enable"]) is bool and type(target["enable"]) is bool
                     and type(before["sipUdpPort"]) is int
                     and 0 <= before["sipUdpPort"] <= 65535
                     and type(target["sipUdpPort"]) is int
                     and target["sipUdpPort"] == before["sipUdpPort"]
                     and before["enable"] != target["enable"])
    elif operation == "gateway-tag-qos":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        fields = frozenset({"tagConfigList"})
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, fields) and _exact_state(target, fields)
        dscp_values = {"8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "30", "32", "34", "36", "38", "40", "46", "48", "56"}
        if valid:
            def valid_list(state: object) -> bool:
                rows = state["tagConfigList"]
                return (type(rows) is list and len(rows) == 4
                        and all(type(row) is dict
                                and set(row) == {"classType", "enable", "dscp"}
                                and type(row["classType"]) is int
                                and row["classType"] in (0, 1, 2, 3)
                                and type(row["enable"]) is bool
                                and type(row["dscp"]) is str
                                and row["dscp"] in dscp_values for row in rows)
                        and {row["classType"] for row in rows} == {0, 1, 2, 3})
            valid = valid_list(before) and valid_list(target)
        if valid:
            old_rows, new_rows = before["tagConfigList"], target["tagConfigList"]
            valid = (all(old["classType"] == new["classType"] and old["dscp"] == new["dscp"]
                         for old, new in zip(old_rows, new_rows))
                     and sum(old["enable"] != new["enable"]
                             for old, new in zip(old_rows, new_rows)) == 1)
    elif operation == "band-steering":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, frozenset({"mode"}))
        valid = valid and _exact_state(target, frozenset({"mode"}))
        if valid:
            valid = (type(before["mode"]) is int and before["mode"] in (0, 1, 2) and
                     type(target["mode"]) is int and target["mode"] in (0, 1, 2))
    elif operation == "rrm-mode":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        fields = frozenset({"mode", "timeRangeEnable", "resource", "timeRangeId", "timeRangeAction"})
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, fields) and _exact_state(target, fields)
        if valid:
            valid = all(type(state["mode"]) is int and state["mode"] in (0, 1)
                        and state["timeRangeEnable"] is False
                        and type(state["resource"]) is int and state["resource"] in (0, 1, 2)
                        and type(state["timeRangeId"]) is str and state["timeRangeId"] == ""
                        and type(state["timeRangeAction"]) is int and state["timeRangeAction"] in (0, 1)
                        for state in (before, target))
            if valid:
                valid = all(before[field] == target[field]
                            for field in ("timeRangeEnable", "resource", "timeRangeId", "timeRangeAction"))
    elif operation == "site-led":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, frozenset({"enable"}))
        valid = valid and _exact_state(target, frozenset({"enable"}))
        if valid:
            valid = type(before["enable"]) is bool and type(target["enable"]) is bool
    elif operation == "ap-afc":
        if set(target_refs) != {"site_ref", "device_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "device_ref": target_refs["device_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _exact_state(before, frozenset({"enable"}))
        valid = valid and _exact_state(target, frozenset({"enable"}))
        if valid:
            valid = type(before["enable"]) is bool and type(target["enable"]) is bool
    elif operation == "site-lldp":
        if set(target_refs) != {"site_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"]}
        valid = _opaque_ref(refs["site_ref"])
        valid = valid and _exact_state(before, frozenset({"enable"}))
        valid = valid and _exact_state(target, frozenset({"enable"}))
        if valid:
            valid = type(before["enable"]) is bool and type(target["enable"]) is bool
    elif operation == "ap-channel-limit":
        if set(target_refs) != {"site_ref", "device_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "device_ref": target_refs["device_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        valid = valid and _exact_state(before, frozenset({"channelLimitType"}))
        valid = valid and _exact_state(target, frozenset({"channelLimitType"}))
        if valid:
            valid = (type(before["channelLimitType"]) is int and before["channelLimitType"] in (0, 1, 2)
                     and type(target["channelLimitType"]) is int and target["channelLimitType"] in (0, 1, 2))
    elif operation == "ap-ofdma":
        if set(target_refs) != {"site_ref", "device_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "device_ref": target_refs["device_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        enable_fields = frozenset({"ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g"})
        valid = valid and isinstance(before, dict) and isinstance(target, dict)
        if valid:
            valid = (len(before) == 1 and set(before) in ({field} for field in enable_fields)
                     and set(target) == set(before)
                     and type(next(iter(before.values()))) is bool
                     and type(next(iter(target.values()))) is bool)
    else:  # ap-qos
        if set(target_refs) != {"site_ref", "device_ref"}:
            raise ChangeJournalError("journal_schema_invalid")
        refs = {"site_ref": target_refs["site_ref"], "device_ref": target_refs["device_ref"]}
        valid = all(_opaque_ref(value) for value in refs.values())
        try:
            before_state = normalize_ap_qos_change_state(before)
            target_state = normalize_ap_qos_change_state(target)
        except ApQosError:
            valid = False
        else:
            valid = valid and set(before_state) == set(target_state)
            before, target = before_state, target_state
            if valid:
                changed = [field for field in before
                           if before[field] != target[field]]
                valid = (len(changed) == 1 and changed[0].startswith("deliveryEnable") and
                         all(before[field] == target[field] for field in set(before) - set(changed)))

    if not valid:
        raise ChangeJournalError("journal_schema_invalid")
    # Round-trip through the bounded, strict JSON encoder to detach caller data.
    return {
        "plan_id": plan_id,
        "operation": operation,
        "target_refs": json.loads(_canonical(refs)),
        "before": json.loads(_canonical(before)),
        "target": json.loads(_canonical(target)),
    }


def _event_digest(event: dict[str, object]) -> str:
    without_hash = {key: value for key, value in event.items() if key != "record_hash"}
    return hashlib.sha256(_canonical(without_hash)).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def derive_controller_binding(reference_key: bytes, base_url: str,
                              controller_id: str) -> str:
    """Derive the opaque controller binding without retaining any input value.

    The 32-byte persistent reference key is an HMAC key. The journal stores
    only the returned digest, never the key, URL, or controller identifier.
    """
    if not isinstance(reference_key, bytes) or len(reference_key) != 32:
        raise ChangeJournalError("journal_binding_invalid")
    if (not isinstance(base_url, str) or base_url != base_url.strip() or
            any(ord(char) < 0x21 or ord(char) > 0x7e for char in base_url) or
            not isinstance(controller_id, str) or not _CONTROLLER_ID.fullmatch(controller_id)):
        raise ChangeJournalError("journal_binding_invalid")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port if parsed.port is not None else 443
        hostname = parsed.hostname
    except ValueError:
        raise ChangeJournalError("journal_binding_invalid") from None
    if (parsed.scheme != "https" or not hostname or parsed.username or parsed.password or
            parsed.path not in ("", "/") or parsed.query or parsed.fragment or
            not 1 <= port <= 65535):
        raise ChangeJournalError("journal_binding_invalid")
    try:
        normalized_host = ipaddress.ip_address(hostname).compressed.lower()
    except ValueError:
        normalized_host = hostname.rstrip(".").lower()
    authority_host = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
    message = f"omada-change-journal-v1\nhttps://{authority_host}:{port}\n{controller_id}".encode("ascii")
    return hmac.new(reference_key, message, hashlib.sha256).hexdigest()


class ChangePlanJournal:
    """A single-process, exclusive-lock JSONL journal.

    ``directory`` must already exist, be owned by the current user, and have
    private permissions. The file and lock are created with mode 0600. No
    automatic directory creation, truncation, repair, controller call, or write
    replay is performed.
    """

    _DATA_NAME = "change-plans.jsonl"
    _LOCK_NAME = "change-plans.lock"

    def __init__(self, directory: str, *, controller_binding: str) -> None:
        if not isinstance(controller_binding, str) or not _BINDING.fullmatch(controller_binding):
            raise ChangeJournalError("journal_binding_invalid")
        self._controller_binding = controller_binding
        self._mutex = threading.RLock()
        self._closed = False
        self._poisoned = False
        self._dir_fd = -1
        self._lock_fd = -1
        self._data_fd = -1
        self._sequence = 0
        self._tail_hash = _ZERO_HASH
        self._plans: dict[str, dict[str, object]] = {}
        try:
            self._dir_fd = self._open_directory(directory)
            self._lock_fd = self._open_private_file(self._LOCK_NAME, os.O_RDWR | os.O_CREAT)
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ChangeJournalError("journal_locked") from None
            self._data_fd = self._open_private_file(
                self._DATA_NAME, os.O_RDWR | os.O_APPEND | os.O_CREAT)
            # Persist directory entries before this journal can authorize any dispatch.
            try:
                os.fsync(self._dir_fd)
            except OSError:
                raise ChangeJournalError("journal_directory_sync_failed") from None
            self._load()
        except Exception:
            self.close()
            raise

    @staticmethod
    def _open_directory(directory: str) -> int:
        if not isinstance(directory, str) or not os.path.isabs(directory):
            raise ChangeJournalError("journal_path_invalid")
        components = directory.split("/")
        if any(component in {".", ".."} for component in components):
            raise ChangeJournalError("journal_path_invalid")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open("/", flags)
        except OSError:
            raise ChangeJournalError("journal_directory_unavailable") from None
        try:
            for component in (item for item in components if item):
                try:
                    next_fd = os.open(component, flags | nofollow, dir_fd=fd)
                except OSError:
                    raise ChangeJournalError("journal_directory_unavailable") from None
                os.close(fd)
                fd = next_fd
            info = os.fstat(fd)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) & 0o077):
                raise ChangeJournalError("journal_permissions_invalid")
            return fd
        except ChangeJournalError:
            os.close(fd)
            raise
        except OSError:
            os.close(fd)
            raise ChangeJournalError("journal_directory_unavailable") from None

    def _open_private_file(self, name: str, flags: int) -> int:
        secure_flags = (flags | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            try:
                fd = os.open(name, secure_flags | os.O_CREAT | os.O_EXCL,
                             0o600, dir_fd=self._dir_fd)
            except FileExistsError:
                fd = os.open(name, secure_flags, dir_fd=self._dir_fd)
        except OSError as exc:
            code = "journal_file_unsafe" if exc.errno == errno.ELOOP else "journal_file_unavailable"
            raise ChangeJournalError(code) from None
        try:
            info = os.fstat(fd)
        except OSError:
            os.close(fd)
            raise ChangeJournalError("journal_file_unavailable") from None
        mode = stat.S_IMODE(info.st_mode)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or mode & 0o077 or not mode & 0o600 == 0o600):
            os.close(fd)
            raise ChangeJournalError("journal_permissions_invalid")
        return fd

    def _ensure_open(self) -> None:
        if self._closed:
            raise ChangeJournalError("journal_closed")
        if self._poisoned:
            raise ChangeJournalError("journal_unavailable")

    @property
    def available(self) -> bool:
        """Whether journal operations remain safe in this process."""
        with self._mutex:
            return not self._closed and not self._poisoned

    def _load(self) -> None:
        try:
            info = os.fstat(self._data_fd)
        except OSError:
            raise ChangeJournalError("journal_file_unavailable") from None
        if info.st_size > _MAX_FILE_BYTES:
            raise ChangeJournalError("journal_full")
        try:
            os.lseek(self._data_fd, 0, os.SEEK_SET)
        except OSError:
            raise ChangeJournalError("journal_file_unavailable") from None
        chunks = bytearray()
        while len(chunks) <= _MAX_FILE_BYTES:
            try:
                chunk = os.read(self._data_fd, min(65536, _MAX_FILE_BYTES + 1 - len(chunks)))
            except OSError:
                raise ChangeJournalError("journal_file_unavailable") from None
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > _MAX_FILE_BYTES:
            raise ChangeJournalError("journal_full")
        if not chunks:
            return
        if not chunks.endswith(b"\n"):
            raise ChangeJournalError("journal_corrupt")

        previous_hash = _ZERO_HASH
        expected_sequence = 1
        for line in chunks.splitlines(keepends=True):
            if len(line) > _MAX_RECORD_BYTES or not line.endswith(b"\n"):
                raise ChangeJournalError("journal_corrupt")
            try:
                event = json.loads(line[:-1], object_pairs_hook=_no_duplicate_keys,
                                   parse_constant=_reject_constant)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
                raise ChangeJournalError("journal_corrupt") from None
            self._validate_event(event, expected_sequence, previous_hash)
            self._apply_event(event)
            previous_hash = event["record_hash"]
            expected_sequence += 1
        self._sequence = expected_sequence - 1
        self._tail_hash = previous_hash
        try:
            os.lseek(self._data_fd, 0, os.SEEK_END)
        except OSError:
            raise ChangeJournalError("journal_file_unavailable") from None

    def _validate_event(self, event: object, sequence: int, previous_hash: str) -> None:
        common = {"schema_version", "sequence", "event_type", "controller_binding", "occurred_at", "plan_id",
                  "operation", "target_refs", "before", "target", "previous_hash", "record_hash"}
        if not isinstance(event, dict):
            raise ChangeJournalError("journal_corrupt")
        event_type = event.get("event_type")
        expected = common | ({"outcome"} if event_type == "dispatch_outcome" else
                             {"confirmation"} if event_type == "operator_closed_unknown" else set())
        try:
            calculated_hash = _event_digest(event)
        except ChangeJournalError:
            raise ChangeJournalError("journal_corrupt") from None
        if (set(event) != expected or type(event.get("schema_version")) is not int or
                event.get("schema_version") != _SCHEMA_VERSION or
                type(event.get("sequence")) is not int or event["sequence"] != sequence or
                event.get("previous_hash") != previous_hash or
                not isinstance(event.get("record_hash"), str) or
                re.fullmatch(r"[0-9a-f]{64}", event["record_hash"]) is None or
                not hmac.compare_digest(event["record_hash"], calculated_hash)):
            raise ChangeJournalError("journal_corrupt")
        timestamp = event.get("occurred_at")
        try:
            parsed_time = datetime.fromisoformat(timestamp[:-1] + "+00:00") if isinstance(timestamp, str) and timestamp.endswith("Z") else None
        except ValueError:
            parsed_time = None
        if parsed_time is None or parsed_time.utcoffset() is None:
            raise ChangeJournalError("journal_corrupt")
        if event.get("controller_binding") != self._controller_binding:
            raise ChangeJournalError("journal_binding_mismatch")
        try:
            plan = _validate_plan(event.get("operation"), event.get("plan_id"),
                                  event.get("target_refs"), event.get("before"), event.get("target"))
        except ChangeJournalError:
            raise ChangeJournalError("journal_corrupt") from None
        if any(event.get(key) != value for key, value in plan.items()):
            raise ChangeJournalError("journal_corrupt")
        if event_type not in {"dispatch_intent", "dispatch_outcome", "operator_closed_unknown"}:
            raise ChangeJournalError("journal_corrupt")
        if (event_type == "dispatch_outcome" and
                (type(event.get("outcome")) is not str or
                 event.get("outcome") not in {"verified_readback", "unknown"})):
            raise ChangeJournalError("journal_corrupt")
        if (event_type == "operator_closed_unknown" and
                event.get("confirmation") != "outcome_unknown_no_retry"):
            raise ChangeJournalError("journal_corrupt")

    def _apply_event(self, event: dict[str, object]) -> None:
        plan_id = event["plan_id"]
        event_type = event["event_type"]
        prior = self._plans.get(plan_id)
        if event_type == "dispatch_intent":
            if prior is not None:
                raise ChangeJournalError("journal_corrupt")
            state = "in_doubt"
            outcome_written = False
        else:
            if prior is None or prior["state"] != "in_doubt":
                raise ChangeJournalError("journal_corrupt")
            for key in ("operation", "target_refs", "before", "target"):
                if event[key] != prior[key]:
                    raise ChangeJournalError("journal_corrupt")
            if event_type == "dispatch_outcome":
                if prior["outcome_written"]:
                    raise ChangeJournalError("journal_corrupt")
                outcome_written = True
                state = "verified" if event["outcome"] == "verified_readback" else "in_doubt"
            else:
                state = "closed_outcome_unknown"
                outcome_written = bool(prior["outcome_written"])
        self._plans[plan_id] = {
            "plan_id": plan_id, "operation": event["operation"],
            "target_refs": copy.deepcopy(event["target_refs"]),
            "before": copy.deepcopy(event["before"]),
            "target": copy.deepcopy(event["target"]),
            "state": state, "outcome_written": outcome_written,
        }

    def _append(self, event_type: str, plan: dict[str, object], *,
                outcome: str | None = None, confirmation: str | None = None) -> None:
        self._ensure_open()
        event: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "sequence": self._sequence + 1,
            "event_type": event_type,
            "controller_binding": self._controller_binding,
            "occurred_at": _utc_now(),
            "plan_id": plan["plan_id"],
            "operation": plan["operation"],
            "target_refs": plan["target_refs"],
            "before": plan["before"],
            "target": plan["target"],
            "previous_hash": self._tail_hash,
        }
        if outcome is not None:
            event["outcome"] = outcome
        if confirmation is not None:
            event["confirmation"] = confirmation
        event["record_hash"] = _event_digest(event)
        encoded = _canonical(event) + b"\n"
        if len(encoded) > _MAX_RECORD_BYTES:
            raise ChangeJournalError("journal_record_too_large")
        try:
            file_size = os.fstat(self._data_fd).st_size
        except OSError:
            self._poisoned = True
            raise ChangeJournalError("journal_file_unavailable") from None
        if file_size + len(encoded) > _MAX_FILE_BYTES:
            raise ChangeJournalError("journal_full")
        try:
            view = memoryview(encoded)
            while view:
                count = os.write(self._data_fd, view)
                if count <= 0:
                    raise OSError("short_write")
                view = view[count:]
            os.fsync(self._data_fd)
        except OSError:
            self._poisoned = True
            raise ChangeJournalError("journal_write_failed") from None
        try:
            self._apply_event(event)
        except ChangeJournalError:
            self._poisoned = True
            raise ChangeJournalError("journal_unavailable") from None
        self._sequence += 1
        self._tail_hash = event["record_hash"]

    def record_dispatch_intent(self, *, operation: str, plan_id: str,
                               target_refs: dict[str, object], before: object,
                               target: object) -> None:
        """Durably record dispatch intent before the caller performs a write."""
        with self._mutex:
            self._ensure_open()
            plan = _validate_plan(operation, plan_id, target_refs, before, target)
            if plan_id in self._plans:
                raise ChangeJournalError("plan_id_reused")
            plan.update({"state": "in_doubt", "outcome_written": False})
            self._append("dispatch_intent", plan)

    def record_outcome(self, plan_id: str, outcome: str) -> None:
        """Append one immutable post-write result; unknown remains unresolved."""
        with self._mutex:
            self._ensure_open()
            plan = self._plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ChangeJournalError("plan_unknown")
            if plan["state"] != "in_doubt" or plan["outcome_written"]:
                raise ChangeJournalError("plan_transition_invalid")
            if type(outcome) is not str or outcome not in {"verified_readback", "unknown"}:
                raise ChangeJournalError("journal_schema_invalid")
            self._append("dispatch_outcome", plan, outcome=outcome)

    def close_unknown(self, plan_id: str, confirmation: object) -> None:
        """Durably close an unresolved plan without changing its unknown outcome."""
        with self._mutex:
            self._ensure_open()
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise ChangeJournalError("operator_confirmation_required")
            plan = self._plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ChangeJournalError("plan_unknown")
            if plan["state"] != "in_doubt":
                raise ChangeJournalError("plan_transition_invalid")
            self._append("operator_closed_unknown", plan,
                         confirmation="outcome_unknown_no_retry")

    def in_doubt_plans(self) -> list[dict[str, object]]:
        """Return recovered unresolved plans; these records are never executable."""
        with self._mutex:
            self._ensure_open()
            return [copy.deepcopy({key: plan[key] for key in
                                   ("plan_id", "operation", "target_refs", "before", "target", "state")})
                    for plan in self._plans.values() if plan["state"] == "in_doubt"]

    def plan_state(self, plan_id: str) -> str:
        """Return historical status only; this class never executes plans."""
        with self._mutex:
            self._ensure_open()
            plan = self._plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ChangeJournalError("plan_unknown")
            return str(plan["state"])

    def close(self) -> None:
        mutex = getattr(self, "_mutex", None)
        if mutex is None:
            return
        with mutex:
            if self._closed:
                return
            self._closed = True
            for name in ("_data_fd", "_lock_fd", "_dir_fd"):
                fd = getattr(self, name)
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    setattr(self, name, -1)

    def __enter__(self) -> "ChangePlanJournal":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
