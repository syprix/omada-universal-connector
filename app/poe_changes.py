"""Isolated, single-port PoE-mode change plans.

The plan writes only the documented ``poeMode`` value through a callback. The
callback must target one already validated inventory row and perform the
controller's dedicated per-port PUT. This module deliberately has no HTTP or
controller integration.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import threading
import time
from typing import Callable

try:
    from .change_journal import ALLOWED_JOURNAL_OPERATIONS
except ImportError:  # pragma: no cover - direct app-module execution
    from change_journal import ALLOWED_JOURNAL_OPERATIONS


class PoeChangeError(RuntimeError):
    """Stable error for an isolated switch-port PoE change plan."""


SCOPE = "switch_port_poe_mode"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_READ_FIELDS = frozenset(("poe", "supportPoe", "profileOverrideEnable"))
_WRITE_FIELDS = frozenset(("poeMode",))


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise PoeChangeError(code)
    return value


def _port(value: object) -> int:
    # Port is numeric in the inventory schema and a path segment in the PUT.
    # Keep the accepted representation unambiguous; booleans are not integers
    # for this API even though Python treats them as such.
    if type(value) is not int or not 0 <= value <= 4096:
        raise PoeChangeError("port_invalid")
    return value


def _mode(value: object) -> int:
    if type(value) is not int or value not in (0, 1):
        raise PoeChangeError("poe_mode_invalid")
    return value


def _read_state(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _READ_FIELDS:
        raise PoeChangeError("read_state_invalid")
    mode = value.get("poe")
    if type(mode) is not int or mode not in (0, 1):
        raise PoeChangeError("read_state_invalid")
    support_poe = value.get("supportPoe")
    if type(support_poe) is not bool:
        raise PoeChangeError("read_state_invalid")
    if support_poe is False:
        raise PoeChangeError("poe_unsupported")
    profile_override = value.get("profileOverrideEnable")
    if type(profile_override) is not bool:
        raise PoeChangeError("read_state_invalid")
    if profile_override is False:
        raise PoeChangeError("profile_override_required")
    return {"poe": mode, "supportPoe": True, "profileOverrideEnable": True}


def _change(value: object) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != _WRITE_FIELDS:
        raise PoeChangeError("change_invalid")
    return {"poeMode": _mode(value.get("poeMode"))}


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


class PoeModePlans:
    """Short-lived, one-use plans for a single port's PoE on/off mode.

    ``read(site_ref, switch_ref, port)`` returns exactly the three documented
    read fields ``poe``, ``supportPoe`` and ``profileOverrideEnable``.
    ``write(site_ref, switch_ref, port, body)`` receives exactly
    ``{"poeMode": 0|1}``. It must use a unique, inventory-validated port row.
    """

    def __init__(self, read: Callable[[str, str, int], object],
                 write: Callable[[str, str, int, dict[str, int]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise PoeChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise PoeChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise PoeChangeError("plan_ttl_invalid")
        if type(limit) is not int or limit < 1:
            raise PoeChangeError("plan_limit_invalid")
        if not callable(clock):
            raise PoeChangeError("clock_invalid")
        if type(require_journal) is not bool:
            raise PoeChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise PoeChangeError("journal_invalid")
        self.read = read
        self.write = write
        self.writes_enabled = writes_enabled
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.limit = limit
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        self.journal, self.require_journal = journal, require_journal
        if journal is not None:
            self._recover_journal_plans()

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise PoeChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise PoeChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise PoeChangeError("journal_unavailable")
            operation = row.get("operation")
            if operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise PoeChangeError("journal_unavailable")
            if operation != "poe":
                continue
            refs = row.get("target_refs")
            before, target = row.get("before"), row.get("target")
            plan_id = row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "switch_ref", "port"}
                    or not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{48}", plan_id)
                    or row.get("state") != "in_doubt"):
                raise PoeChangeError("journal_unavailable")
            if plan_id in self.plans:
                raise PoeChangeError("journal_unavailable")
            try:
                site_ref = _ref(refs["site_ref"], "journal_invalid")
                switch_ref = _ref(refs["switch_ref"], "journal_invalid")
                port = _port(refs["port"])
                if (not isinstance(before, dict) or set(before) != {"poeMode"}
                        or not isinstance(target, dict) or set(target) != {"poeMode"}):
                    raise PoeChangeError("journal_invalid")
                before_state = {"poeMode": _mode(before["poeMode"])}
                target_state = _change(target)
            except PoeChangeError:
                raise PoeChangeError("journal_unavailable") from None
            # Recovered state contains only the journal's whitelisted poeMode;
            # never fabricate support/profile flags needed for a future write.
            self.plans[plan_id] = {
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": before_state, "target": target_state,
                "expires": float("inf"), "state": "in_doubt", "journaled": True,
            }

    @staticmethod
    def _operator_refs(plan: dict[str, object]) -> dict[str, object]:
        site_ref, switch_ref, port = (plan.get("site_ref"), plan.get("switch_ref"),
                                      plan.get("port"))
        return {
            "site_ref": site_ref if isinstance(site_ref, str) and _REF.fullmatch(site_ref) else None,
            "switch_ref": switch_ref if isinstance(switch_ref, str) and _REF.fullmatch(switch_ref) else None,
            "port": port if type(port) is int and 0 <= port <= 4096 else None,
        }

    def list_in_doubt(self) -> list[dict[str, object]]:
        """List unresolved plans with opaque target refs; performs no I/O."""
        with self.lock:
            return [{"plan_id": ident, "state": "in_doubt", "scope": SCOPE,
                     "target_refs": self._operator_refs(plan)}
                    for ident, plan in self.plans.items() if plan.get("state") == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        """Make at most one sanitized observation without resolving write outcome."""
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            observation: dict[str, object] = {"status": "unavailable"}
            try:
                current = self._read_state(plan["site_ref"], plan["switch_ref"], plan["port"])
                observation = {"status": "observed", "data": {"poeMode": current["poe"]}}
            except Exception:
                pass
            return {
                "plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                "scope": SCOPE, "target_refs": self._operator_refs(plan),
                "before": copy.deepcopy(plan.get("before", {})),
                "target": copy.deepcopy(plan.get("target", {})),
                "current_observation": observation,
                "observation_note": "current_state_does_not_prove_original_write_outcome",
            }

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        """Close an uncertain plan only with exact confirmation; never retries."""
        with self.lock:
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise PoeChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise PoeChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise PoeChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise PoeChangeError("plan_not_in_doubt")
        return plan

    def preview(self, site_ref: str, switch_ref: str, port: int,
                change: object) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        switch_ref = _ref(switch_ref, "switch_ref_invalid")
        port = _port(port)
        target = _change(change)

        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise PoeChangeError("plan_capacity_reached")
            before = self._read_state(site_ref, switch_ref, port)
            created_at = self.clock()
            before_mode = before["poe"]
            assert type(before_mode) is int
            if target["poeMode"] == before_mode:
                raise PoeChangeError("no_change")
            plan_id = secrets.token_hex(24)
            self.plans[plan_id] = {
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": created_at + self.ttl_seconds, "state": "pending",
            }
            return {
                "plan_id": plan_id, "scope": SCOPE, "site_ref": site_ref,
                "switch_ref": switch_ref, "port": port,
                "expires_in_seconds": self.ttl_seconds,
                "before": {"poeMode": before_mode}, "target": copy.deepcopy(target),
                "rollback": {"poeMode": before_mode},
                "writes_enabled": self.writes_enabled,
                "warning": "poe_change_may_interrupt_power_to_connected_device",
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise PoeChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise PoeChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise PoeChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise PoeChangeError("plan_expired")

            site_ref, switch_ref, port = plan["site_ref"], plan["switch_ref"], plan["port"]
            current = self._read_state(site_ref, switch_ref, port)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise PoeChangeError("state_changed")
            # Recheck after GET; a slow read must not extend the plan lifetime.
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise PoeChangeError("plan_expired")

            # Consume before dispatch because a failed response may follow a landed PUT.
            if self.require_journal and self.journal is None:
                raise PoeChangeError("journal_required")
            journal_before = {"poeMode": plan["before"]["poe"]}
            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation="poe", plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "switch_ref": switch_ref, "port": port},
                        before=journal_before, target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise PoeChangeError("journal_unavailable") from None
            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                try:
                    self.journal.record_outcome(plan_id, "unknown")
                except Exception:
                    pass
                raise PoeChangeError("plan_expired")
            if self.journal is not None:
                try:
                    dispatch_state = self._read_state(site_ref, switch_ref, port)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise PoeChangeError("state_changed")
                except Exception:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    raise PoeChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    raise PoeChangeError("plan_expired")
            try:
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, switch_ref, port, target)
                after = self._read_state(site_ref, switch_ref, port)
                if after["poe"] != target["poeMode"]:
                    raise PoeChangeError("readback_mismatch")
            except Exception:
                if plan.get("journaled"):
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                raise PoeChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise PoeChangeError("change_in_doubt") from None

            plan["state"] = "applied"
            return {
                "status": "verified", "scope": SCOPE, "plan_id": plan_id,
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": {"poeMode": plan["before"]["poe"]},
                "after": copy.deepcopy(target),
                "rollback": {"poeMode": plan["before"]["poe"]},
            }

    def _read_state(self, site_ref: str, switch_ref: str, port: int) -> dict[str, object]:
        try:
            raw = self.read(site_ref, switch_ref, port)
        except PoeChangeError:
            raise
        except Exception:
            raise PoeChangeError("readback_unavailable") from None
        return _read_state(raw)
