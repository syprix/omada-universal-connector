"""Journaled, approval-bound plans for controller RADIUS proxy settings."""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
import time
from typing import Callable

try:
    from .change_journal import ALLOWED_JOURNAL_OPERATIONS
except ImportError:
    from change_journal import ALLOWED_JOURNAL_OPERATIONS


class ControllerRadiusProxyChangeError(RuntimeError):
    """Stable, non-sensitive error codes for RADIUS proxy plans."""


SCOPE = "controller_radius_proxy"
OPERATION = "controller-radius-proxy"
_FIELDS = frozenset({"enable", "port", "requireMessageAuthenticator", "limitProxyState"})
_OPTIONAL = ("requireMessageAuthenticator", "limitProxyState")
_PLAN_ID_LENGTH = 48


def _state(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ControllerRadiusProxyChangeError("state_unavailable")
    if (type(value["enable"]) is not bool or type(value["port"]) is not int or
            not -(2**31) <= value["port"] < 2**31 or
            any(value[field] is not None and type(value[field]) is not bool
                for field in _OPTIONAL)):
        raise ControllerRadiusProxyChangeError("state_unavailable")
    return {field: value[field] for field in sorted(_FIELDS)}


def _body(state: dict[str, object]) -> dict[str, object]:
    value: dict[str, object] = {"enable": state["enable"], "port": state["port"]}
    for field in _OPTIONAL:
        if state[field] is not None:
            value[field] = state[field]
    return value


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


class ControllerRadiusProxyPlans:
    """Prepare a minimal change and verify state before and after dispatch."""

    def __init__(self, read: Callable[[], object],
                 write: Callable[[dict[str, object]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = True):
        if not callable(read) or not callable(write):
            raise ControllerRadiusProxyChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool or type(require_journal) is not bool:
            raise ControllerRadiusProxyChangeError("configuration_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise ControllerRadiusProxyChangeError("plan_ttl_invalid")
        if not callable(clock) or type(limit) is not int or limit < 1:
            raise ControllerRadiusProxyChangeError("configuration_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise ControllerRadiusProxyChangeError("journal_invalid")
        self.read, self.write = read, write
        self.writes_enabled, self.ttl_seconds = writes_enabled, ttl_seconds
        self.clock, self.limit, self.journal = clock, limit, journal
        self.require_journal = require_journal
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        if journal is not None:
            self._recover()

    def _recover(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise ControllerRadiusProxyChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise ControllerRadiusProxyChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise ControllerRadiusProxyChangeError("journal_unavailable")
            operation, plan_id = row.get("operation"), row.get("plan_id")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise ControllerRadiusProxyChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            if (row.get("target_refs") != {} or not isinstance(plan_id, str) or
                    len(plan_id) != _PLAN_ID_LENGTH or row.get("state") != "in_doubt" or
                    plan_id in self.plans):
                raise ControllerRadiusProxyChangeError("journal_unavailable")
            try:
                before, target = _state(row.get("before")), _state(row.get("target"))
            except ControllerRadiusProxyChangeError:
                raise ControllerRadiusProxyChangeError("journal_unavailable") from None
            if before == target:
                raise ControllerRadiusProxyChangeError("journal_unavailable")
            self.plans[plan_id] = {"before": before, "target": target,
                "before_hash": _digest(before), "expires": float("inf"),
                "state": "in_doubt", "journaled": True, "recovered": True}

    def preview(self, changes: object) -> dict[str, object]:
        if (not isinstance(changes, dict) or not changes or len(changes) > len(_FIELDS) or
                set(changes) - _FIELDS or
                any((type(value) is not bool if key in {"enable", *_OPTIONAL} else
                     type(value) is not int or not -(2**31) <= value < 2**31)
                    for key, value in changes.items())):
            raise ControllerRadiusProxyChangeError("change_invalid")
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise ControllerRadiusProxyChangeError("plan_capacity_reached")
            before = self._read_state()
            target = copy.deepcopy(before)
            target.update(changes)
            target = _state(target)
            if target == before:
                raise ControllerRadiusProxyChangeError("no_change")
            plan_id = secrets.token_hex(24)
            self.plans[plan_id] = {"before": before, "target": target,
                "before_hash": _digest(before), "expires": self.clock() + self.ttl_seconds,
                "state": "pending"}
            return {"status": "pending", "plan_id": plan_id, "scope": SCOPE,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                "patch": _body(target), "rollback": _body(before),
                "rollback_requires_new_plan": True, "writes_enabled": self.writes_enabled,
                "warning": "may_interrupt_authentication_for_clients_using_radius_proxy"}

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise ControllerRadiusProxyChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ControllerRadiusProxyChangeError("plan_unknown")
            if plan.get("state") != "pending":
                raise ControllerRadiusProxyChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise ControllerRadiusProxyChangeError("plan_expired")
            before = _state(plan["before"])
            target = _state(plan["target"])
            current = self._read_state()
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise ControllerRadiusProxyChangeError("state_changed")
            if self.require_journal and self.journal is None:
                raise ControllerRadiusProxyChangeError("journal_required")
            if self.journal is not None:
                try:
                    self.journal.record_dispatch_intent(
                        operation=OPERATION, plan_id=plan_id, target_refs={},
                        before=copy.deepcopy(before), target=copy.deepcopy(target))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise ControllerRadiusProxyChangeError("journal_unavailable") from None
            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            try:
                if self.clock() >= plan["expires"]:
                    raise ControllerRadiusProxyChangeError("plan_expired")
                if _digest(self._read_state()) != plan["before_hash"]:
                    raise ControllerRadiusProxyChangeError("state_changed")
                if self.clock() >= plan["expires"]:
                    raise ControllerRadiusProxyChangeError("plan_expired")
                self.write(_body(target))
                after = self._read_state()
                if after != target:
                    raise ControllerRadiusProxyChangeError("readback_mismatch")
            except ControllerRadiusProxyChangeError as exc:
                self._record_unknown(plan_id, plan)
                if str(exc) in {"state_changed", "plan_expired"}:
                    raise
                raise ControllerRadiusProxyChangeError("change_in_doubt") from None
            except Exception:
                self._record_unknown(plan_id, plan)
                raise ControllerRadiusProxyChangeError("change_in_doubt") from None
            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise ControllerRadiusProxyChangeError("change_in_doubt") from None
            plan["state"] = "applied"
            return {"status": "verified", "scope": SCOPE, "plan_id": plan_id,
                "before": before, "after": target, "rollback": _body(before)}

    def _read_state(self) -> dict[str, object]:
        try:
            value = self.read()
        except Exception:
            raise ControllerRadiusProxyChangeError("readback_unavailable") from None
        return _state(value)

    def _record_unknown(self, plan_id: str, plan: dict[str, object]) -> None:
        if plan.get("journaled") and self.journal is not None:
            try:
                self.journal.record_outcome(plan_id, "unknown")
            except Exception:
                pass

    def list_in_doubt(self) -> list[dict[str, object]]:
        with self.lock:
            return [{"plan_id": pid, "state": "in_doubt", "scope": SCOPE,
                     "target_refs": {}} for pid, plan in self.plans.items()
                    if plan.get("state") == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            try:
                current: dict[str, object] = {"status": "observed", "data": self._read_state()}
            except Exception:
                current = {"status": "unavailable"}
            return {"plan_id": plan_id, "scope": SCOPE, "state": "in_doubt",
                "outcome": "unknown", "before": copy.deepcopy(plan["before"]),
                "target": copy.deepcopy(plan["target"]), "target_refs": {},
                "current_observation": current,
                "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        with self.lock:
            if confirmation != "outcome_unknown_no_retry":
                raise ControllerRadiusProxyChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise ControllerRadiusProxyChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "scope": SCOPE,
                    "state": "closed_outcome_unknown", "target_refs": {}}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise ControllerRadiusProxyChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise ControllerRadiusProxyChangeError("plan_not_in_doubt")
        return plan
