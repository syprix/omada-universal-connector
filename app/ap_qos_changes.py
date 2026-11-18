"""Journaled plans for documented per-band AP Advanced QoS changes."""
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
    from .ap_qos import ApQosError, normalize_ap_qos_change_state
except ImportError:
    from change_journal import ALLOWED_JOURNAL_OPERATIONS
    from ap_qos import ApQosError, normalize_ap_qos_change_state


class ApQosChangeError(RuntimeError):
    """Stable error codes for AP QoS change plans."""


SCOPE = "ap_qos"
OPERATION = "ap-qos"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN = re.compile(r"[0-9a-f]{48}\Z")
_CHANGE_FIELDS = frozenset({"deliveryEnable2g", "deliveryEnable5g",
                            "deliveryEnable5g2", "deliveryEnable6g"})


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise ApQosChangeError(code)
    return value


def _state(value: object) -> dict[str, bool]:
    try:
        state = normalize_ap_qos_change_state(value)
    except ApQosError:
        raise ApQosChangeError("ap_qos_state_unavailable")
    return state


def _digest(value: dict[str, bool]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


def _patch(state: dict[str, bool]) -> dict[str, bool]:
    """Build the complete supported PATCH body from the documented GET state."""
    body: dict[str, bool] = {}
    if state["support2g"]:
        body["deliveryEnable2g"] = state["deliveryEnable2g"]
    if state["support5g"]:
        # The GET's deliveryEnable5g describes 5GHz-1 when split. PATCH calls
        # that same first segment deliveryEnable5g1.
        key = "deliveryEnable5g1" if state["support5g2"] else "deliveryEnable5g"
        body[key] = state["deliveryEnable5g"]
        if state["support5g2"]:
            body["deliveryEnable5g2"] = state["deliveryEnable5g2"]
    if state["support6g"]:
        body["deliveryEnable6g"] = state["deliveryEnable6g"]
    if not body:
        raise ApQosChangeError("ap_qos_no_supported_bands")
    return body


class ApQosPlans:
    """Preview, journal, dispatch and verify a full supported-band QoS state."""

    def __init__(self, read: Callable[[str, str], object],
                 write: Callable[[str, str, dict[str, bool]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = True):
        if not callable(read) or not callable(write):
            raise ApQosChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool or type(require_journal) is not bool:
            raise ApQosChangeError("configuration_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise ApQosChangeError("plan_ttl_invalid")
        if not callable(clock) or type(limit) is not int or limit < 1:
            raise ApQosChangeError("configuration_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise ApQosChangeError("journal_invalid")
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
            raise ApQosChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise ApQosChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise ApQosChangeError("journal_unavailable")
            operation = row.get("operation")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise ApQosChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "device_ref"} or
                    not isinstance(plan_id, str) or not _PLAN.fullmatch(plan_id) or
                    row.get("state") != "in_doubt" or plan_id in self.plans):
                raise ApQosChangeError("journal_unavailable")
            before, target = _state(row.get("before")), _state(row.get("target"))
            site_ref = _ref(refs["site_ref"], "journal_invalid")
            device_ref = _ref(refs["device_ref"], "journal_invalid")
            if before == target:
                raise ApQosChangeError("journal_unavailable")
            self.plans[plan_id] = {"site_ref": site_ref, "device_ref": device_ref,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": float("inf"), "state": "in_doubt", "journaled": True,
                "recovered": True}

    def preview(self, site_ref: str, device_ref: str, change: object, *,
                disruption_confirmed: object = False) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        device_ref = _ref(device_ref, "device_ref_invalid")
        if type(disruption_confirmed) is not bool or not disruption_confirmed:
            raise ApQosChangeError("disruption_confirmation_required")
        if (not isinstance(change, dict) or len(change) != 1 or
                next(iter(change), None) not in _CHANGE_FIELDS or
                type(next(iter(change.values()), None)) is not bool):
            raise ApQosChangeError("ap_qos_change_invalid")
        field, enabled = next(iter(change.items()))
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise ApQosChangeError("plan_capacity_reached")
            before = _state(self.read(site_ref, device_ref))
            if field == "deliveryEnable2g" and not before["support2g"]:
                raise ApQosChangeError("ap_qos_band_not_reported_supported")
            if field == "deliveryEnable5g" and not before["support5g"]:
                raise ApQosChangeError("ap_qos_band_not_reported_supported")
            if field == "deliveryEnable5g2" and not before["support5g2"]:
                raise ApQosChangeError("ap_qos_band_not_reported_supported")
            if field == "deliveryEnable6g" and not before["support6g"]:
                raise ApQosChangeError("ap_qos_band_not_reported_supported")
            if before[field] is enabled:
                raise ApQosChangeError("no_change")
            target = copy.deepcopy(before)
            target[field] = enabled
            plan_id = secrets.token_hex(24)
            expires = self.clock() + self.ttl_seconds
            self.plans[plan_id] = {"site_ref": site_ref, "device_ref": device_ref,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": expires, "state": "pending"}
            return {"plan_id": plan_id, "scope": SCOPE, "site_ref": site_ref,
                "device_ref": device_ref, "field": field,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                "patch": _patch(target), "rollback": _patch(before),
                "rollback_requires_new_plan": True, "writes_enabled": self.writes_enabled,
                "warning": "ap_qos_change_may_affect_client_power_save_behavior"}

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise ApQosChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ApQosChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise ApQosChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise ApQosChangeError("plan_expired")
            site_ref, device_ref = plan["site_ref"], plan["device_ref"]
            current = _state(self.read(site_ref, device_ref))
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise ApQosChangeError("state_changed")
            if self.require_journal and self.journal is None:
                raise ApQosChangeError("journal_required")
            if self.journal is not None:
                try:
                    self.journal.record_dispatch_intent(operation=OPERATION, plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "device_ref": device_ref},
                        before=plan["before"], target=plan["target"])
                except Exception:
                    plan["state"] = "in_doubt"
                    raise ApQosChangeError("journal_unavailable") from None
            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            try:
                if self.journal is not None:
                    dispatch_state = _state(self.read(site_ref, device_ref))
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise ApQosChangeError("state_changed")
                    if self.clock() >= plan["expires"]:
                        raise ApQosChangeError("plan_expired")
                self.write(site_ref, device_ref, _patch(plan["target"]))
                after = _state(self.read(site_ref, device_ref))
                if after != plan["target"]:
                    raise ApQosChangeError("readback_mismatch")
            except Exception:
                self._outcome_unknown(plan_id, plan)
                raise ApQosChangeError("change_in_doubt") from None
            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise ApQosChangeError("change_in_doubt") from None
            plan["state"] = "applied"
            return {"status": "verified", "scope": SCOPE, "plan_id": plan_id,
                "site_ref": site_ref, "device_ref": device_ref,
                "before": copy.deepcopy(plan["before"]),
                "after": copy.deepcopy(plan["target"]), "patch": _patch(plan["target"]),
                "rollback": _patch(plan["before"]), "rollback_requires_new_plan": True}

    def _outcome_unknown(self, plan_id: str, plan: dict[str, object]) -> None:
        if plan.get("journaled"):
            try:
                self.journal.record_outcome(plan_id, "unknown")
            except Exception:
                pass

    def list_in_doubt(self) -> list[dict[str, object]]:
        with self.lock:
            return [{"plan_id": key, "state": "in_doubt", "scope": SCOPE,
                     "target_refs": {"site_ref": plan["site_ref"],
                                     "device_ref": plan["device_ref"]}}
                    for key, plan in self.plans.items() if plan["state"] == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            plan = self._in_doubt(plan_id)
            try:
                current = {"status": "observed",
                           "data": _state(self.read(plan["site_ref"], plan["device_ref"]))}
            except Exception:
                current = {"status": "unavailable"}
            return {"plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                "scope": SCOPE, "target_refs": {"site_ref": plan["site_ref"],
                    "device_ref": plan["device_ref"]}, "before": plan["before"],
                "target": plan["target"], "current_observation": current,
                "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        if confirmation != "outcome_unknown_no_retry":
            raise ApQosChangeError("operator_confirmation_required")
        with self.lock:
            plan = self._in_doubt(plan_id)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise ApQosChangeError("journal_unavailable") from None
            refs = {"site_ref": plan["site_ref"], "device_ref": plan["device_ref"]}
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise ApQosChangeError("plan_unknown")
        if plan["state"] != "in_doubt":
            raise ApQosChangeError("plan_not_in_doubt")
        return plan
