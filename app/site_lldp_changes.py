"""Opt-in plans for one site-wide LLDP enable flag."""
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


class SiteLldpChangeError(RuntimeError):
    """Stable, redacted error for a site LLDP change plan."""


SCOPE = "site_lldp"
OPERATION = "site-lldp"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")


def _ref(value: object, code: str = "site_ref_invalid") -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise SiteLldpChangeError(code)
    return value


def _state(value: object) -> dict[str, bool]:
    if (not isinstance(value, dict) or set(value) != {"enable"}
            or type(value.get("enable")) is not bool):
        raise SiteLldpChangeError("state_invalid")
    return {"enable": value["enable"]}


def _digest(value: dict[str, bool]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class SiteLldpPlans:
    """Prepare and verify one five-minute site-wide LLDP Boolean change.

    The manager passes only ``{"enable": bool}`` to its callback. Any
    controller-specific wire envelope is the adapter's responsibility.
    """

    def __init__(self, read: Callable[[str], object],
                 write: Callable[[str, dict[str, bool]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise SiteLldpChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise SiteLldpChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise SiteLldpChangeError("plan_ttl_invalid")
        if not callable(clock):
            raise SiteLldpChangeError("clock_invalid")
        if type(limit) is not int or limit < 1:
            raise SiteLldpChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise SiteLldpChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise SiteLldpChangeError("journal_invalid")
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
        site_ref = plan.get("site_ref")
        return {"site_ref": site_ref if isinstance(site_ref, str) and _REF.fullmatch(site_ref) else None}

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise SiteLldpChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise SiteLldpChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise SiteLldpChangeError("journal_unavailable")
            operation = row.get("operation")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise SiteLldpChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref"}
                    or not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id)
                    or row.get("state") != "in_doubt" or plan_id in self.plans):
                raise SiteLldpChangeError("journal_unavailable")
            try:
                site_ref = _ref(refs["site_ref"], "journal_invalid")
                before, target = _state(row.get("before")), _state(row.get("target"))
            except SiteLldpChangeError:
                raise SiteLldpChangeError("journal_unavailable") from None
            if before == target:
                raise SiteLldpChangeError("journal_unavailable")
            self.plans[plan_id] = {
                "site_ref": site_ref, "before": before, "target": target,
                "before_hash": _digest(before), "expires": float("inf"),
                "state": "in_doubt", "journaled": True,
            }

    def preview(self, site_ref: str, change: object, *,
                disruption_confirmed: object = False) -> dict[str, object]:
        site_ref = _ref(site_ref)
        if type(disruption_confirmed) is not bool or disruption_confirmed is not True:
            raise SiteLldpChangeError("disruption_confirmation_required")
        if (not isinstance(change, dict) or set(change) != {"enable"}
                or type(change.get("enable")) is not bool):
            raise SiteLldpChangeError("change_invalid")
        target = {"enable": change["enable"]}
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise SiteLldpChangeError("plan_capacity_reached")
            before = self._read_state(site_ref)
            if target == before:
                raise SiteLldpChangeError("no_change")
            plan_id = secrets.token_hex(24)
            created = self.clock()
            self.plans[plan_id] = {
                "site_ref": site_ref, "before": before, "target": target,
                "before_hash": _digest(before), "expires": created + self.ttl_seconds,
                "state": "pending",
            }
            return {"plan_id": plan_id, "scope": SCOPE, "site_ref": site_ref,
                    "expires_in_seconds": self.ttl_seconds,
                    "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                    "rollback": copy.deepcopy(before), "writes_enabled": self.writes_enabled,
                    "effect_note": "site_lldp_device_effect_depends_on_controller"}

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise SiteLldpChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise SiteLldpChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise SiteLldpChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise SiteLldpChangeError("plan_expired")

            site_ref = plan["site_ref"]
            current = self._read_state(site_ref)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise SiteLldpChangeError("state_changed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise SiteLldpChangeError("plan_expired")
            if self.require_journal and self.journal is None:
                raise SiteLldpChangeError("journal_required")

            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation=OPERATION, plan_id=plan_id,
                        target_refs={"site_ref": site_ref},
                        before=copy.deepcopy(plan["before"]),
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise SiteLldpChangeError("journal_unavailable") from None

            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                self._record_unknown(plan_id, plan)
                raise SiteLldpChangeError("plan_expired")
            if self.journal is not None:
                # Recheck after the durable intent so changes during fsync do
                # not get overwritten. Without controller CAS, a final race
                # between this GET and PUT remains possible.
                try:
                    dispatch_state = self._read_state(site_ref)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise SiteLldpChangeError("state_changed")
                except Exception:
                    self._record_unknown(plan_id, plan)
                    raise SiteLldpChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    self._record_unknown(plan_id, plan)
                    raise SiteLldpChangeError("plan_expired")
            try:
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, target)
                after = self._read_state(site_ref)
                if after != target:
                    raise SiteLldpChangeError("readback_mismatch")
            except Exception:
                self._record_unknown(plan_id, plan)
                raise SiteLldpChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise SiteLldpChangeError("change_in_doubt") from None
            plan["state"] = "applied"
            return {"status": "verified", "scope": SCOPE, "plan_id": plan_id,
                    "site_ref": site_ref, "before": copy.deepcopy(plan["before"]),
                    "after": copy.deepcopy(target), "rollback": copy.deepcopy(plan["before"])}

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
                observation = {"status": "observed", "data": self._read_state(plan["site_ref"])}
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
                raise SiteLldpChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise SiteLldpChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise SiteLldpChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise SiteLldpChangeError("plan_not_in_doubt")
        return plan

    def _read_state(self, site_ref: str) -> dict[str, bool]:
        try:
            raw = self.read(site_ref)
        except Exception:
            raise SiteLldpChangeError("readback_unavailable") from None
        return _state(raw)
