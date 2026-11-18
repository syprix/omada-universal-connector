"""Opt-in plans for changing one switch port's administrative status."""
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
except ImportError:  # direct-module imports used by local scripts
    from change_journal import ALLOWED_JOURNAL_OPERATIONS


class PortStatusChangeError(RuntimeError):
    """Stable error for a single switch-port status plan."""


SCOPE = "switch_port_admin_status"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise PortStatusChangeError(code)
    return value


def _port(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 4096:
        raise PortStatusChangeError("port_invalid")
    return value


def _status(value: object) -> dict[str, int]:
    if (not isinstance(value, dict) or set(value) != {"status"}
            or type(value.get("status")) is not int or value["status"] not in (0, 1)):
        raise PortStatusChangeError("status_invalid")
    return {"status": value["status"]}


def _digest(value: dict[str, int]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


class SwitchPortStatusPlans:
    """Prepare and verify an explicit ``status`` 0/1 update for one port.

    The caller must pass ``disruption_confirmed=True`` to the preview because
    disabling a port may interrupt access. Values remain numeric; the manager
    assigns no additional meaning to either documented status value.
    """

    def __init__(self, read: Callable[[str, str, int], object],
                 write: Callable[[str, str, int, dict[str, int]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise PortStatusChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise PortStatusChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise PortStatusChangeError("plan_ttl_invalid")
        if not callable(clock):
            raise PortStatusChangeError("clock_invalid")
        if type(limit) is not int or limit < 1:
            raise PortStatusChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise PortStatusChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise PortStatusChangeError("journal_invalid")
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
            raise PortStatusChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise PortStatusChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise PortStatusChangeError("journal_unavailable")
            operation = row.get("operation")
            if (not isinstance(operation, str)
                    or operation not in ALLOWED_JOURNAL_OPERATIONS):
                raise PortStatusChangeError("journal_unavailable")
            if operation != "switch-port-status":
                continue
            refs = row.get("target_refs")
            plan_id = row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "switch_ref", "port"}
                    or not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id)
                    or row.get("state") != "in_doubt" or plan_id in self.plans):
                raise PortStatusChangeError("journal_unavailable")
            try:
                site_ref = _ref(refs["site_ref"], "journal_invalid")
                switch_ref = _ref(refs["switch_ref"], "journal_invalid")
                port = _port(refs["port"])
                before, target = _status(row.get("before")), _status(row.get("target"))
            except PortStatusChangeError:
                raise PortStatusChangeError("journal_unavailable") from None
            self.plans[plan_id] = {
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": float("inf"), "state": "in_doubt", "journaled": True,
            }

    def preview(self, site_ref: str, switch_ref: str, port: int, change: object,
                *, disruption_confirmed: object = False) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        switch_ref = _ref(switch_ref, "switch_ref_invalid")
        port = _port(port)
        if type(disruption_confirmed) is not bool or disruption_confirmed is not True:
            raise PortStatusChangeError("disruption_confirmation_required")
        if not isinstance(change, dict) or set(change) != {"status"}:
            raise PortStatusChangeError("change_invalid")
        target = _status(change)

        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise PortStatusChangeError("plan_capacity_reached")
            before = self._read_status(site_ref, switch_ref, port)
            if target == before:
                raise PortStatusChangeError("no_change")
            plan_id = secrets.token_hex(24)
            created = self.clock()
            self.plans[plan_id] = {
                "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": created + self.ttl_seconds, "state": "pending",
            }
            return {
                "plan_id": plan_id, "scope": SCOPE, "site_ref": site_ref,
                "switch_ref": switch_ref, "port": port,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                "rollback": copy.deepcopy(before), "writes_enabled": self.writes_enabled,
                "warning": "port_status_change_may_interrupt_access",
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise PortStatusChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise PortStatusChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise PortStatusChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise PortStatusChangeError("plan_expired")

            site_ref, switch_ref, port = plan["site_ref"], plan["switch_ref"], plan["port"]
            current = self._read_status(site_ref, switch_ref, port)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise PortStatusChangeError("state_changed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise PortStatusChangeError("plan_expired")

            if self.require_journal and self.journal is None:
                raise PortStatusChangeError("journal_required")
            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation="switch-port-status", plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "switch_ref": switch_ref,
                                     "port": port},
                        before=copy.deepcopy(plan["before"]),
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise PortStatusChangeError("journal_unavailable") from None

            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            try:
                if self.journal is not None:
                    if self.clock() >= plan["expires"]:
                        raise PortStatusChangeError("plan_expired")
                    # Close the gap between the pre-intent read and the write:
                    # the durable journal operation itself may take time.
                    post_intent = self._read_status(site_ref, switch_ref, port)
                    if _digest(post_intent) != plan["before_hash"]:
                        raise PortStatusChangeError("state_changed")
                    if self.clock() >= plan["expires"]:
                        raise PortStatusChangeError("plan_expired")
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, switch_ref, port, target)
                after = self._read_status(site_ref, switch_ref, port)
                if after != target:
                    raise PortStatusChangeError("readback_mismatch")
            except PortStatusChangeError as exc:
                self._record_unknown(plan_id, plan)
                if str(exc) in {"state_changed", "plan_expired"}:
                    raise
                raise PortStatusChangeError("change_in_doubt") from None
            except Exception:
                self._record_unknown(plan_id, plan)
                raise PortStatusChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise PortStatusChangeError("change_in_doubt") from None

            plan["state"] = "applied"
            return {"status": "verified", "scope": SCOPE, "plan_id": plan_id,
                    "site_ref": site_ref, "switch_ref": switch_ref, "port": port,
                    "before": copy.deepcopy(plan["before"]), "after": copy.deepcopy(target),
                    "rollback": copy.deepcopy(plan["before"])}

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
            observation: dict[str, object] = {"status": "unavailable"}
            try:
                current = self._read_status(plan["site_ref"], plan["switch_ref"], plan["port"])
                observation = {"status": "observed", "data": current}
            except Exception:
                pass
            return {"plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                    "scope": SCOPE, "target_refs": self._operator_refs(plan),
                    "before": copy.deepcopy(plan.get("before", {})),
                    "target": copy.deepcopy(plan.get("target", {})),
                    "current_observation": observation,
                    "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        with self.lock:
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise PortStatusChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise PortStatusChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise PortStatusChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise PortStatusChangeError("plan_not_in_doubt")
        return plan

    def _read_status(self, site_ref: str, switch_ref: str, port: int) -> dict[str, int]:
        try:
            raw = self.read(site_ref, switch_ref, port)
        except Exception:
            raise PortStatusChangeError("readback_unavailable") from None
        return _status(raw)
