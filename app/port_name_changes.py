"""Opt-in, one-use plans for renaming a single inventoried switch port."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import threading
import time
import unicodedata
from typing import Callable

try:
    from .change_journal import ALLOWED_JOURNAL_OPERATIONS
except ImportError:  # direct-module imports used by local scripts
    from change_journal import ALLOWED_JOURNAL_OPERATIONS


class PortNameChangeError(RuntimeError):
    """Stable error for a single switch-port name plan."""


SCOPE = "switch_port_name"
OPERATION = "switch-port-name"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_NAME_REDACTION_MARKER = {"name_redacted": True}


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise PortNameChangeError(code)
    return value


def _port(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 4096:
        raise PortNameChangeError("port_invalid")
    return value


def _name(value: object, code: str) -> str:
    """Validate the strict common schema and reject ambiguous Unicode text.

    Hardware/CBC specify a regex; ER specifies only the 1..128 character
    limit. Apply the stricter schema to every family. Preserve accepted input
    exactly; callers must never silently normalize an approval target.
    """
    if type(value) is not str or not 1 <= len(value) <= 128:
        raise PortNameChangeError(code)
    if value[0].isspace() or value[-1].isspace() or '?' in value or '"' in value:
        raise PortNameChangeError(code)
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise PortNameChangeError(code) from None
    if unicodedata.normalize("NFC", value) != value:
        raise PortNameChangeError(code)
    # Controls, bidi/format characters, private-use values, surrogates, and
    # unassigned code points can make a displayed plan ambiguous or invisible.
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise PortNameChangeError(code)
    return value


def _read_state(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"name"}:
        raise PortNameChangeError("read_state_unsupported")
    return {"name": _current_name(value.get("name"))}


def _current_name(value: object) -> str:
    """Accept only a safely comparable old value; preserve it byte-for-byte.

    Older controllers may expose an empty label or characters forbidden for
    new values. Those are safe as a before-state only when bounded, valid NFC
    Unicode without control/format characters. Never trim or normalize them.
    """
    if type(value) is not str or not 0 <= len(value) <= 128:
        raise PortNameChangeError("read_state_unsupported")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise PortNameChangeError("read_state_unsupported") from None
    if (unicodedata.normalize("NFC", value) != value or
            any(unicodedata.category(char).startswith("C") for char in value) or
            (value and (value[0].isspace() or value[-1].isspace()))):
        raise PortNameChangeError("read_state_unsupported")
    return value


def _change(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"name"}:
        raise PortNameChangeError("change_invalid")
    return {"name": _name(value.get("name"), "name_invalid")}


def _digest(value: dict[str, str]) -> str:
    # Used only in the current process for stale checking / approval binding.
    # No name-derived digest is sent to the durable journal.
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()


def _journal_redaction_marker(value: object) -> dict[str, bool]:
    # Journal only confirms that the operator-supplied text was deliberately
    # omitted; it contains neither text nor a reversible/unkeyed fingerprint.
    return copy.deepcopy(_NAME_REDACTION_MARKER)


class SwitchPortNamePlans:
    """Prepare and verify a single name update for one switch port.

    ``read(site_ref, switch_ref, port)`` returns exactly ``{"name": str}``.
    ``write(site_ref, switch_ref, port, body)`` receives exactly
    ``{"name": str}``. Names are visible only in authenticated preview output;
    journal events contain a fixed redaction marker, never names or hashes.
    """

    def __init__(self, read: Callable[[str, str, int], object],
                 write: Callable[[str, str, int, dict[str, str]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise PortNameChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise PortNameChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise PortNameChangeError("plan_ttl_invalid")
        if not callable(clock):
            raise PortNameChangeError("clock_invalid")
        if type(limit) is not int or limit < 1:
            raise PortNameChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise PortNameChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise PortNameChangeError("journal_invalid")
        self.read, self.write = read, write
        self.writes_enabled, self.ttl_seconds = writes_enabled, ttl_seconds
        self.clock, self.limit = clock, limit
        self.journal, self.require_journal = journal, require_journal
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        if journal is not None:
            self._recover_journal_plans()

    @staticmethod
    def _operator_refs(plan: dict[str, object]) -> dict[str, object]:
        site_ref, switch_ref, port = (plan.get("site_ref"), plan.get("switch_ref"),
                                      plan.get("port"))
        return {
            "site_ref": site_ref if isinstance(site_ref, str) and _REF.fullmatch(site_ref) else None,
            "switch_ref": switch_ref if isinstance(switch_ref, str) and _REF.fullmatch(switch_ref) else None,
            "port": port if type(port) is int and 0 <= port <= 4096 else None,
        }

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise PortNameChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise PortNameChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise PortNameChangeError("journal_unavailable")
            operation = row.get("operation")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise PortNameChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "switch_ref", "port"}
                    or not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id)
                    or row.get("state") != "in_doubt" or plan_id in self.plans):
                raise PortNameChangeError("journal_unavailable")
            try:
                site_ref = _ref(refs["site_ref"], "journal_invalid")
                switch_ref = _ref(refs["switch_ref"], "journal_invalid")
                port = _port(refs["port"])
                before, target = row.get("before"), row.get("target")
                if (before != _NAME_REDACTION_MARKER or
                        target != _NAME_REDACTION_MARKER):
                    raise PortNameChangeError("journal_invalid")
            except PortNameChangeError:
                raise PortNameChangeError("journal_unavailable") from None
            self.plans[plan_id] = {
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": copy.deepcopy(_NAME_REDACTION_MARKER),
                "target": copy.deepcopy(_NAME_REDACTION_MARKER),
                "before_hash": _digest(_NAME_REDACTION_MARKER),
                "expires": float("inf"), "state": "in_doubt", "journaled": True,
                "recovered_redacted": True,
            }

    def preview(self, site_ref: str, switch_ref: str, port: int,
                change: object) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        switch_ref = _ref(switch_ref, "switch_ref_invalid")
        port = _port(port)
        target = _change(change)
        with self.lock:
            now = self.clock()
            self.plans = {ident: plan for ident, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise PortNameChangeError("plan_capacity_reached")
            before = self._read_name(site_ref, switch_ref, port)
            if target == before:
                raise PortNameChangeError("no_change")
            plan_id = secrets.token_hex(24)
            created = self.clock()
            self.plans[plan_id] = {
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": created + self.ttl_seconds, "state": "pending",
            }
            return {
                "plan_id": plan_id, "scope": SCOPE,
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                "rollback": copy.deepcopy(before), "writes_enabled": self.writes_enabled,
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise PortNameChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise PortNameChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise PortNameChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise PortNameChangeError("plan_expired")
            site_ref, switch_ref, port = plan["site_ref"], plan["switch_ref"], plan["port"]
            current = self._read_name(site_ref, switch_ref, port)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise PortNameChangeError("state_changed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise PortNameChangeError("plan_expired")
            if self.require_journal and self.journal is None:
                raise PortNameChangeError("journal_required")
            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation=OPERATION, plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "switch_ref": switch_ref,
                                     "port": port},
                        before=_journal_redaction_marker(plan["before"]),
                        target=_journal_redaction_marker(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise PortNameChangeError("journal_unavailable") from None

            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            try:
                if self.journal is not None:
                    if self.clock() >= plan["expires"]:
                        raise PortNameChangeError("plan_expired")
                    # Close the gap between the pre-intent read and the write:
                    # the durable journal operation itself may take time.
                    post_intent = self._read_name(site_ref, switch_ref, port)
                    if _digest(post_intent) != plan["before_hash"]:
                        raise PortNameChangeError("state_changed")
                    if self.clock() >= plan["expires"]:
                        raise PortNameChangeError("plan_expired")
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, switch_ref, port, target)
                after = self._read_name(site_ref, switch_ref, port)
                if after != target:
                    raise PortNameChangeError("readback_mismatch")
            except PortNameChangeError as exc:
                self._record_unknown(plan_id, plan)
                if str(exc) in {"state_changed", "plan_expired"}:
                    raise
                raise PortNameChangeError("change_in_doubt") from None
            except Exception:
                self._record_unknown(plan_id, plan)
                raise PortNameChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise PortNameChangeError("change_in_doubt") from None
            plan["state"] = "applied"
            return {"status": "verified", "scope": SCOPE, "plan_id": plan_id,
                    "site_ref": site_ref, "switch_ref": switch_ref, "port": port}

    def _record_unknown(self, plan_id: str, plan: dict[str, object]) -> None:
        if not plan.get("journaled"):
            return
        try:
            self.journal.record_outcome(plan_id, "unknown")
        except Exception:
            pass

    def list_in_doubt(self) -> list[dict[str, object]]:
        with self.lock:
            return [{"plan_id": plan_id, "state": "in_doubt", "scope": SCOPE,
                     "target_refs": self._operator_refs(plan)}
                    for plan_id, plan in self.plans.items() if plan.get("state") == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            observation: dict[str, object] = {"status": "unavailable", "name_redacted": True}
            try:
                self._read_name(plan["site_ref"], plan["switch_ref"], plan["port"])
                observation = {"status": "observed", "name_redacted": True}
            except Exception:
                pass
            return {
                "plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                "scope": SCOPE, "target_refs": self._operator_refs(plan),
                "before": copy.deepcopy(_NAME_REDACTION_MARKER),
                "target": copy.deepcopy(_NAME_REDACTION_MARKER),
                "current_observation": observation,
                "observation_note": "current_state_does_not_prove_original_write_outcome",
            }

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        with self.lock:
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise PortNameChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise PortNameChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise PortNameChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise PortNameChangeError("plan_not_in_doubt")
        return plan

    def _read_name(self, site_ref: str, switch_ref: str, port: int) -> dict[str, str]:
        try:
            raw = self.read(site_ref, switch_ref, port)
        except Exception:
            raise PortNameChangeError("readback_unavailable") from None
        return _read_state(raw)
