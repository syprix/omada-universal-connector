"""One-port, journaled switch cable-test actions with explicit approval."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import threading
import time
from typing import Any, Callable


OPERATION = "switch-cable-test"
CANCEL_OPERATION = "switch-cable-test-cancel"
SCOPE = "switch_cable_test"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LOG_PORT_FIELDS = ("test_ports", "complete_ports", "cancelled_ports", "timed_out_ports")


class SwitchCableTestError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _ref(value: object) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise SwitchCableTestError("reference_invalid")
    return value


class SwitchCableTestPlans:
    """Prepare, start once, inspect and explicitly cancel one cable test.

    This is an active diagnostic. The fixed outer approval callback must guard
    each start/cancel dispatch. Uncertain outcomes remain in-doubt and are
    never replayed. A log row is accepted only when its timestamp is new and
    its port/result records correlate exactly.
    """

    ttl_seconds = 300
    max_runtime_seconds = 60

    def __init__(self, *, read_ports: Callable[[str, str], object],
                 read_logs: Callable[[str, str], object],
                 read_results: Callable[[str, str], object],
                 start: Callable[[str, str, list[int]], object],
                 cancel: Callable[[str, str], object],
                 writes_enabled: bool = False, clock: Callable[[], float] = time.monotonic,
                 journal: object | None = None, require_journal: bool = True,
                 limit: int = 100):
        for callback in (read_ports, read_logs, read_results, start, cancel, clock):
            if not callable(callback):
                raise SwitchCableTestError("callbacks_invalid")
        if type(writes_enabled) is not bool or type(require_journal) is not bool:
            raise SwitchCableTestError("configuration_invalid")
        if type(limit) is not int or limit < 1:
            raise SwitchCableTestError("plan_limit_invalid")
        if require_journal and journal is None:
            # Construction is allowed with an unavailable journal; preview
            # remains possible, but apply refuses until a durable journal exists.
            pass
        elif journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise SwitchCableTestError("journal_invalid")
        self.read_ports, self.read_logs, self.read_results = read_ports, read_logs, read_results
        self.start, self.cancel = start, cancel
        self.writes_enabled, self.clock = writes_enabled, clock
        self.journal, self.require_journal, self.limit = journal, require_journal, limit
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        if journal is not None:
            self._recover()

    @staticmethod
    def _port_state(value: object, port: int) -> dict[str, object]:
        if (not isinstance(value, dict) or value.get("status") != "ok" or
                value.get("resource") != "switch_cable_test_ports"):
            raise SwitchCableTestError("cable_test_inventory_incomplete")
        data = value.get("data")
        rows = data.get("ports") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) > 512:
            raise SwitchCableTestError("cable_test_inventory_invalid")
        matches = [row for row in rows if isinstance(row, dict) and row.get("port") == port]
        if not matches:
            raise SwitchCableTestError("cable_test_port_unknown")
        if len(matches) != 1:
            raise SwitchCableTestError("cable_test_port_ambiguous")
        row = matches[0]
        required = {"editEnable", "copper", "upper_port", "stack_port", "disabled"}
        if required - set(row):
            raise SwitchCableTestError("cable_test_port_state_unknown")
        if any(type(row[field]) is not bool for field in required):
            raise SwitchCableTestError("cable_test_port_state_invalid")
        if (row["editEnable"] is not True or row["copper"] is not True or
                row["upper_port"] or row["stack_port"]):
            raise SwitchCableTestError("cable_test_port_unsupported")
        return {field: row[field] for field in sorted(required)}

    @staticmethod
    def _logs(value: object) -> list[dict[str, object]]:
        if (not isinstance(value, dict) or value.get("status") != "ok" or
                value.get("resource") != "switch_cable_test_logs"):
            raise SwitchCableTestError("cable_test_logs_incomplete")
        data = value.get("data")
        rows = data.get("logs") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) > 64:
            raise SwitchCableTestError("cable_test_logs_invalid")
        normalized = []
        for row in rows:
            if (not isinstance(row, dict) or type(row.get("timestamp_value")) is not int or
                    any(not isinstance(row.get(field), list) or
                        any(type(port) is not int or not 1 <= port <= 4096
                            for port in row[field]) for field in _LOG_PORT_FIELDS)):
                raise SwitchCableTestError("cable_test_logs_invalid")
            normalized.append({"timestamp_value": row["timestamp_value"],
                               **{field: sorted(row[field]) for field in _LOG_PORT_FIELDS}})
        return normalized

    def _read_before(self, site_ref: str, switch_ref: str, port: int) -> tuple[dict[str, object], list[dict[str, object]]]:
        state = self._port_state(self.read_ports(site_ref, switch_ref), port)
        logs = self._logs(self.read_logs(site_ref, switch_ref))
        return state, logs

    def preview(self, site_ref: str, switch_ref: str, port: object,
                disruption_confirmed: object) -> dict[str, object]:
        site_ref, switch_ref = _ref(site_ref), _ref(switch_ref)
        if type(port) is not int or not 1 <= port <= 4096:
            raise SwitchCableTestError("cable_test_port_invalid")
        if disruption_confirmed is not True:
            raise SwitchCableTestError("disruption_confirmation_required")
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan.get("state") in {"running", "in_doubt", "cancel_pending"}
                          or now < plan.get("expires", 0)}
            if len(self.plans) >= self.limit:
                raise SwitchCableTestError("plan_capacity_reached")
            state, logs = self._read_before(site_ref, switch_ref, port)
            plan_id = secrets.token_hex(24)
            before = {"port_state": state, "logs_digest": _digest(logs)}
            target = {"port": port, "max_runtime_seconds": self.max_runtime_seconds}
            self.plans[plan_id] = {
                "operation": OPERATION, "site_ref": site_ref, "switch_ref": switch_ref,
                "port": port, "before": before, "target": target,
                "before_hash": _digest(before),
                "baseline_logs": [_digest(row) for row in logs],
                "expires": now + self.ttl_seconds, "state": "pending",
                "journaled": False,
            }
            return {"status": "preview", "scope": SCOPE, "plan_id": plan_id,
                    "site_ref": site_ref, "switch_ref": switch_ref,
                    "target": copy.deepcopy(target), "expires_in_seconds": self.ttl_seconds,
                    "writes_enabled": self.writes_enabled,
                    "effect_note": "A cable test can affect the selected switch port; duration is capped at 60 seconds by this workflow. A timeout remains unresolved; no retry is automatic."}

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise SwitchCableTestError("writes_disabled")
            plan = self._pending(plan_id, OPERATION)
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise SwitchCableTestError("plan_expired")
            site_ref, switch_ref, port = plan["site_ref"], plan["switch_ref"], plan["port"]
            state, logs = self._read_before(site_ref, switch_ref, port)
            current_before = {"port_state": state, "logs_digest": _digest(logs)}
            if _digest(current_before) != plan["before_hash"]:
                plan["state"] = "stale"
                raise SwitchCableTestError("state_changed")
            if self.require_journal and self.journal is None:
                raise SwitchCableTestError("journal_required")
            plan["state"] = "in_doubt"
            if self.journal is not None:
                try:
                    self.journal.record_dispatch_intent(
                        operation=OPERATION, plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "switch_ref": switch_ref},
                        before={"port_state_digest": _digest(state), "logs_digest": _digest(logs)},
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    raise SwitchCableTestError("journal_unavailable") from None
                plan["journaled"] = True
            try:
                self.start(site_ref, switch_ref, [port])
            except Exception:
                self._record_unknown(plan_id, plan)
                raise SwitchCableTestError("cable_test_outcome_unknown") from None
            plan["started_at"] = self.clock()
            plan["state"] = "running"
            return {"status": "started", "scope": SCOPE, "plan_id": plan_id,
                    "state": "running", "max_runtime_seconds": self.max_runtime_seconds,
                    "no_retry": True}

    def status(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if not isinstance(plan, dict) or plan.get("operation") != OPERATION:
                raise SwitchCableTestError("plan_unknown")
            if plan.get("state") == "recovered_unknown":
                return self._unknown_status(plan_id, plan, "recovered_without_baseline")
            if plan.get("state") not in {"running", "in_doubt"}:
                raise SwitchCableTestError("plan_not_running")
            if not isinstance(plan.get("baseline_logs"), list):
                return self._unknown_status(plan_id, plan, "baseline_unavailable")
            logs = self._logs(self.read_logs(plan["site_ref"], plan["switch_ref"]))
            baseline = set(plan["baseline_logs"])
            port = plan["port"]
            new_rows = [row for row in logs if _digest(row) not in baseline and
                        row["test_ports"] == [port]]
            if len(new_rows) > 1:
                return self._unknown_status(plan_id, plan, "multiple_matching_log_rows")
            if new_rows:
                row = new_rows[0]
                complete = port in row["complete_ports"]
                cancelled = port in row["cancelled_ports"]
                timed_out = port in row["timed_out_ports"]
                if sum((complete, cancelled, timed_out)) != 1:
                    return self._unknown_status(plan_id, plan, "log_state_unresolved")
                if complete:
                    results = self.read_results(plan["site_ref"], plan["switch_ref"])
                    clean = self._result_for(results, port, row["timestamp_value"])
                    if clean is None:
                        return self._unknown_status(plan_id, plan, "result_not_correlated")
                    self._record_verified(plan_id, plan)
                    plan["state"] = "completed"
                    return {"status": "completed", "scope": SCOPE, "plan_id": plan_id,
                            "port": port, "result": clean, "no_retry": True}
                state = "cancelled" if cancelled else "timed_out"
                self._record_verified(plan_id, plan)
                plan["state"] = state
                cancel_plan_id = plan.get("cancel_plan_id")
                cancel_plan = self.plans.get(cancel_plan_id) if isinstance(cancel_plan_id, str) else None
                if isinstance(cancel_plan, dict) and cancel_plan.get("journaled"):
                    self._record_verified(cancel_plan_id, cancel_plan)
                    cancel_plan["state"] = "cancelled_verified"
                return {"status": state, "scope": SCOPE, "plan_id": plan_id,
                        "port": port, "no_retry": True}
            started_at = plan.get("started_at")
            elapsed = self.clock() - started_at if type(started_at) in (float, int) else self.max_runtime_seconds
            if elapsed >= self.max_runtime_seconds:
                return self._unknown_status(plan_id, plan, "runtime_limit_exceeded")
            return {"status": "running", "scope": SCOPE, "plan_id": plan_id,
                    "elapsed_seconds": max(0, int(elapsed)), "no_retry": True}

    def preview_cancel(self, plan_id: str, disruption_confirmed: object) -> dict[str, object]:
        if disruption_confirmed is not True:
            raise SwitchCableTestError("disruption_confirmation_required")
        with self.lock:
            parent = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if not isinstance(parent, dict) or parent.get("operation") != OPERATION:
                raise SwitchCableTestError("plan_unknown")
            if parent.get("state") not in {"running", "in_doubt"}:
                raise SwitchCableTestError("cable_test_not_cancellable")
            cancel_id = secrets.token_hex(24)
            before = {"parent_plan_id": plan_id, "parent_state": parent["state"]}
            target = {"action": "cancel", "parent_plan_id": plan_id}
            self.plans[cancel_id] = {
                "operation": CANCEL_OPERATION, "site_ref": parent["site_ref"],
                "switch_ref": parent["switch_ref"], "parent_plan_id": plan_id,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": self.clock() + self.ttl_seconds, "state": "pending",
                "journaled": False,
            }
            return {"status": "preview", "scope": SCOPE, "plan_id": cancel_id,
                    "target_plan_id": plan_id, "expires_in_seconds": self.ttl_seconds,
                    "writes_enabled": self.writes_enabled,
                    "effect_note": "Sends one cancel request for the referenced cable test; its final outcome must be checked separately."}

    def apply_cancel(self, cancel_plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise SwitchCableTestError("writes_disabled")
            plan = self._pending(cancel_plan_id, CANCEL_OPERATION)
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise SwitchCableTestError("plan_expired")
            if self.require_journal and self.journal is None:
                raise SwitchCableTestError("journal_required")
            parent = self.plans.get(plan["parent_plan_id"])
            if not isinstance(parent, dict) or parent.get("state") not in {"running", "in_doubt"}:
                plan["state"] = "stale"
                raise SwitchCableTestError("cable_test_not_cancellable")
            plan["state"] = "in_doubt"
            if self.journal is not None:
                try:
                    self.journal.record_dispatch_intent(
                        operation=CANCEL_OPERATION, plan_id=cancel_plan_id,
                        target_refs={"site_ref": plan["site_ref"], "switch_ref": plan["switch_ref"]},
                        before={"parent_plan_id": plan["parent_plan_id"]},
                        target={"action": "cancel"})
                except Exception:
                    raise SwitchCableTestError("journal_unavailable") from None
                plan["journaled"] = True
            try:
                self.cancel(plan["site_ref"], plan["switch_ref"])
            except Exception:
                self._record_unknown(cancel_plan_id, plan)
                raise SwitchCableTestError("cable_test_cancel_outcome_unknown") from None
            parent["cancel_requested"] = True
            parent["cancel_plan_id"] = cancel_plan_id
            plan["state"] = "cancel_sent_unknown"
            return {"status": "cancel_sent", "scope": SCOPE,
                    "plan_id": cancel_plan_id, "target_plan_id": plan["parent_plan_id"],
                    "outcome": "unknown_until_status_read", "no_retry": True}

    def list_in_doubt(self) -> list[dict[str, object]]:
        with self.lock:
            return [{"plan_id": plan_id, "state": plan["state"], "scope": SCOPE,
                     "target_refs": {"site_ref": plan["site_ref"],
                                     "switch_ref": plan["switch_ref"]}}
                    for plan_id, plan in self.plans.items()
                    if plan.get("state") in {"in_doubt", "recovered_unknown", "cancel_sent_unknown"}]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if not isinstance(plan, dict) or plan.get("state") not in {
                    "in_doubt", "recovered_unknown", "cancel_sent_unknown"}:
                raise SwitchCableTestError("plan_not_in_doubt")
            if plan.get("operation") == OPERATION:
                return self.status(plan_id)
            return {"status": "unknown", "scope": SCOPE, "plan_id": plan_id,
                    "target_plan_id": plan.get("parent_plan_id"),
                    "reason": "cancel_outcome_requires_parent_status", "no_retry": True}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        with self.lock:
            if confirmation != "outcome_unknown_no_retry":
                raise SwitchCableTestError("operator_confirmation_required")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if not isinstance(plan, dict) or plan.get("state") not in {
                    "in_doubt", "recovered_unknown", "cancel_sent_unknown"}:
                raise SwitchCableTestError("plan_not_in_doubt")
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise SwitchCableTestError("journal_unavailable") from None
            refs = {"site_ref": plan["site_ref"], "switch_ref": plan["switch_ref"]}
            del self.plans[plan_id]
            return {"status": "closed_outcome_unknown", "plan_id": plan_id,
                    "scope": SCOPE, "target_refs": refs}

    def _recover(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise SwitchCableTestError("journal_unavailable") from None
        for row in rows:
            operation = row.get("operation") if isinstance(row, dict) else None
            if operation not in {OPERATION, CANCEL_OPERATION}:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "switch_ref"} or
                    not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id)):
                raise SwitchCableTestError("journal_unavailable")
            self.plans[plan_id] = {
                "operation": operation, "site_ref": _ref(refs["site_ref"]),
                "switch_ref": _ref(refs["switch_ref"]), "port": row["target"].get("port"),
                "target": row["target"], "before": row["before"],
                "before_hash": _digest(row["before"]), "baseline_logs": None,
                "state": "recovered_unknown", "journaled": True,
                "parent_plan_id": row["target"].get("parent_plan_id"),
                "expires": float("inf"),
            }

    def _result_for(self, value: object, port: int, timestamp: int) -> dict[str, object] | None:
        if (not isinstance(value, dict) or value.get("status") != "ok" or
                value.get("resource") != "switch_cable_test_full_results"):
            return None
        data = value.get("data")
        rows = data.get("ports") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return None
        matches = [row for row in rows if isinstance(row, dict) and row.get("port") == port
                   and row.get("timestamp_value") == timestamp]
        if len(matches) != 1:
            return None
        row = matches[0]
        if (not isinstance(row.get("state_codes"), list) or
                not isinstance(row.get("length_values"), list)):
            return None
        return {"state_codes": row["state_codes"], "length_values": row["length_values"]}

    def _record_verified(self, plan_id: str, plan: dict[str, object]) -> None:
        if plan.get("journaled"):
            try:
                self.journal.record_outcome(plan_id, "verified_readback")
            except Exception:
                plan["state"] = "in_doubt"
                raise SwitchCableTestError("journal_unavailable") from None

    def _record_unknown(self, plan_id: str, plan: dict[str, object]) -> None:
        if plan.get("journaled"):
            try:
                self.journal.record_outcome(plan_id, "unknown")
            except Exception:
                pass

    def _pending(self, plan_id: str, operation: str) -> dict[str, object]:
        if not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
            raise SwitchCableTestError("plan_invalid")
        plan = self.plans.get(plan_id)
        if not isinstance(plan, dict) or plan.get("operation") != operation:
            raise SwitchCableTestError("plan_unknown")
        if plan.get("state") != "pending":
            raise SwitchCableTestError("plan_already_consumed")
        return plan

    @staticmethod
    def _unknown_status(plan_id: str, plan: dict[str, object], reason: str) -> dict[str, object]:
        return {"status": "unknown", "scope": SCOPE, "plan_id": plan_id,
                "port": plan.get("port"), "reason": reason,
                "cancel_available": True, "no_retry": True}
