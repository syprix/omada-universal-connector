"""Opt-in plan manager for one AP's documented OFDMA band enable field."""
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


class ApOfdmaChangeError(RuntimeError):
    """Stable, redacted error for an AP OFDMA plan."""


SCOPE = "ap_ofdma"
OPERATION = "ap-ofdma"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_ENABLE_FIELDS = frozenset({
    "ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g",
})
_SUPPORT_BY_ENABLE = {
    "ofdmaEnable2g": "supportOfdma2g",
    "ofdmaEnable5g": "supportOfdma5g",
    "ofdmaEnable5g2": "supportOfdma5g2",
    "ofdmaEnable6g": "supportOfdma6g",
}
_READ_FIELDS = frozenset(_ENABLE_FIELDS | frozenset(_SUPPORT_BY_ENABLE.values()))


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise ApOfdmaChangeError(code)
    return value


def _read_state(value: object) -> dict[str, bool]:
    if not isinstance(value, dict) or set(value) != _READ_FIELDS:
        raise ApOfdmaChangeError("ofdma_state_invalid")
    if any(type(value.get(field)) is not bool for field in _READ_FIELDS):
        raise ApOfdmaChangeError("ofdma_state_invalid")
    return {field: value[field] for field in sorted(_READ_FIELDS)}


def _change(value: object) -> dict[str, bool]:
    if (not isinstance(value, dict) or len(value) != 1 or
            next(iter(value), None) not in _ENABLE_FIELDS):
        raise ApOfdmaChangeError("ofdma_change_invalid")
    field, enabled = next(iter(value.items()))
    if type(enabled) is not bool:
        raise ApOfdmaChangeError("ofdma_change_invalid")
    return {field: enabled}


def _journal_change(value: object) -> dict[str, bool]:
    try:
        return _change(value)
    except ApOfdmaChangeError:
        raise ApOfdmaChangeError("journal_invalid") from None


def _digest(value: dict[str, bool]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class ApOfdmaPlans:
    """Prepare and verify a single five-minute AP OFDMA band change.

    The pending plan binds all enable/support booleans. PATCH receives only
    the single requested enable field. Because partial-PATCH behavior and its
    effects are undocumented, the preview warns that other settings might be
    affected. No inferred hardware or firmware cause is exposed.
    """

    def __init__(self, read: Callable[[str, str], object],
                 write: Callable[[str, str, dict[str, bool]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise ApOfdmaChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise ApOfdmaChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise ApOfdmaChangeError("plan_ttl_invalid")
        if not callable(clock):
            raise ApOfdmaChangeError("clock_invalid")
        if type(limit) is not int or limit < 1:
            raise ApOfdmaChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise ApOfdmaChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise ApOfdmaChangeError("journal_invalid")
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
        site_ref, device_ref = plan.get("site_ref"), plan.get("device_ref")
        return {
            "site_ref": site_ref if isinstance(site_ref, str) and _REF.fullmatch(site_ref) else None,
            "device_ref": device_ref if isinstance(device_ref, str) and _REF.fullmatch(device_ref) else None,
        }

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise ApOfdmaChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise ApOfdmaChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise ApOfdmaChangeError("journal_unavailable")
            operation = row.get("operation")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise ApOfdmaChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "device_ref"}
                    or not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id)
                    or row.get("state") != "in_doubt" or plan_id in self.plans):
                raise ApOfdmaChangeError("journal_unavailable")
            try:
                site_ref = _ref(refs["site_ref"], "journal_invalid")
                device_ref = _ref(refs["device_ref"], "journal_invalid")
                before = _journal_change(row.get("before"))
                target = _journal_change(row.get("target"))
            except ApOfdmaChangeError:
                raise ApOfdmaChangeError("journal_unavailable") from None
            if set(before) != set(target) or before == target:
                raise ApOfdmaChangeError("journal_unavailable")
            field = next(iter(before))
            self.plans[plan_id] = {
                "site_ref": site_ref, "device_ref": device_ref,
                "field": field, "before": before, "target": target,
                "before_hash": _digest(before), "expires": float("inf"),
                "state": "in_doubt", "journaled": True, "recovered": True,
            }

    def preview(self, site_ref: str, device_ref: str, change: object, *,
                disruption_confirmed: object = False) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        device_ref = _ref(device_ref, "device_ref_invalid")
        if type(disruption_confirmed) is not bool or disruption_confirmed is not True:
            raise ApOfdmaChangeError("disruption_confirmation_required")
        patch = _change(change)
        field, enabled = next(iter(patch.items()))
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise ApOfdmaChangeError("plan_capacity_reached")
            before = self._read_state(site_ref, device_ref)
            support_field = _SUPPORT_BY_ENABLE[field]
            if before[support_field] is not True:
                raise ApOfdmaChangeError("ofdma_band_not_reported_supported")
            if before[field] is enabled:
                raise ApOfdmaChangeError("no_change")
            target = copy.deepcopy(before)
            target[field] = enabled
            plan_id = secrets.token_hex(24)
            created = self.clock()
            self.plans[plan_id] = {
                "site_ref": site_ref, "device_ref": device_ref,
                "field": field, "before": before, "target": target,
                "patch_before": {field: before[field]}, "patch_target": patch,
                "before_hash": _digest(before), "expires": created + self.ttl_seconds,
                "state": "pending",
            }
            return {
                "plan_id": plan_id, "scope": SCOPE,
                "site_ref": site_ref, "device_ref": device_ref,
                "band_field": field, "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                "rollback": copy.deepcopy(self.plans[plan_id]["patch_before"]),
                "rollback_requires_new_plan": True,
                "writes_enabled": self.writes_enabled,
                "warning": "ofdma_partial_patch_effect_unknown_other_settings_might_be_affected",
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise ApOfdmaChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ApOfdmaChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise ApOfdmaChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise ApOfdmaChangeError("plan_expired")

            site_ref, device_ref = plan["site_ref"], plan["device_ref"]
            current = self._read_state(site_ref, device_ref)
            field = plan["field"]
            if current[_SUPPORT_BY_ENABLE[field]] is not True:
                plan["state"] = "stale"
                raise ApOfdmaChangeError("ofdma_support_state_changed")
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise ApOfdmaChangeError("state_changed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise ApOfdmaChangeError("plan_expired")
            if self.require_journal and self.journal is None:
                raise ApOfdmaChangeError("journal_required")

            journal_before = copy.deepcopy(plan["patch_before"])
            journal_target = copy.deepcopy(plan["patch_target"])
            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation=OPERATION, plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "device_ref": device_ref},
                        before=journal_before, target=journal_target)
                except Exception:
                    plan["state"] = "in_doubt"
                    raise ApOfdmaChangeError("journal_unavailable") from None

            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                self._record_unknown(plan_id, plan)
                raise ApOfdmaChangeError("plan_expired")
            if self.journal is not None:
                # Check the entire band/support snapshot again after fsync.
                # The controller cannot provide an atomic CAS through this API.
                try:
                    dispatch_state = self._read_state(site_ref, device_ref)
                    if (dispatch_state[_SUPPORT_BY_ENABLE[field]] is not True
                            or _digest(dispatch_state) != plan["before_hash"]):
                        raise ApOfdmaChangeError("state_changed")
                except Exception:
                    self._record_unknown(plan_id, plan)
                    raise ApOfdmaChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    self._record_unknown(plan_id, plan)
                    raise ApOfdmaChangeError("plan_expired")
            try:
                self.write(site_ref, device_ref, copy.deepcopy(plan["patch_target"]))
                after = self._read_state(site_ref, device_ref)
                if after != plan["target"]:
                    raise ApOfdmaChangeError("readback_mismatch")
            except Exception:
                self._record_unknown(plan_id, plan)
                raise ApOfdmaChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise ApOfdmaChangeError("change_in_doubt") from None
            plan["state"] = "applied"
            return {
                "status": "verified", "scope": SCOPE, "plan_id": plan_id,
                "site_ref": site_ref, "device_ref": device_ref,
                "before": copy.deepcopy(plan["before"]),
                "after": copy.deepcopy(plan["target"]),
                "patch": copy.deepcopy(plan["patch_target"]),
                "rollback": copy.deepcopy(plan["patch_before"]),
                "rollback_requires_new_plan": True,
            }

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
                observation = {"status": "observed",
                               "data": self._read_state(plan["site_ref"], plan["device_ref"])}
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
        with self.lock:
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise ApOfdmaChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise ApOfdmaChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise ApOfdmaChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise ApOfdmaChangeError("plan_not_in_doubt")
        return plan

    def _read_state(self, site_ref: str, device_ref: str) -> dict[str, bool]:
        try:
            raw = self.read(site_ref, device_ref)
        except Exception:
            raise ApOfdmaChangeError("readback_unavailable") from None
        return _read_state(raw)
