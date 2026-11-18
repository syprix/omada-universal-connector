"""Opt-in plans for the documented AP channel-limit type setting."""
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


class ApChannelLimitChangeError(RuntimeError):
    """Stable, redacted error for an AP channel-limit plan."""


SCOPE = "ap_channel_limit_type"
OPERATION = "ap-channel-limit"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_READ_FIELDS = frozenset({"supportChannelLimit", "channelLimitType",
                          "defaultInstType5g", "defaultInstType6g"})


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise ApChannelLimitChangeError(code)
    return value


def _read_state(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _READ_FIELDS:
        raise ApChannelLimitChangeError("channel_limit_state_invalid")
    if (type(value.get("supportChannelLimit")) is not bool
            or value["supportChannelLimit"] is not True
            or type(value.get("channelLimitType")) is not int
            or value["channelLimitType"] not in (0, 1, 2)
            or type(value.get("defaultInstType5g")) is not bool
            or type(value.get("defaultInstType6g")) is not bool):
        raise ApChannelLimitChangeError("channel_limit_unsupported_or_invalid")
    return {"supportChannelLimit": True,
            "channelLimitType": value["channelLimitType"],
            "defaultInstType5g": value["defaultInstType5g"],
            "defaultInstType6g": value["defaultInstType6g"]}


def _change(value: object) -> dict[str, int]:
    if (not isinstance(value, dict) or set(value) != {"channelLimitType"}
            or type(value.get("channelLimitType")) is not int
            or value["channelLimitType"] not in (0, 1, 2)):
        raise ApChannelLimitChangeError("channel_limit_change_invalid")
    return {"channelLimitType": value["channelLimitType"]}


def _journal_state(value: object) -> dict[str, int]:
    try:
        return _change(value)
    except ApChannelLimitChangeError:
        raise ApChannelLimitChangeError("journal_invalid") from None


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class ApChannelLimitPlans:
    """Prepare and verify one five-minute AP channelLimitType change.

    The pending snapshot binds support and both default-installation values.
    Journal records intentionally contain only the changed field; recovered
    in-doubt plans never recreate support/default values.
    """

    def __init__(self, read: Callable[[str, str], object],
                 write: Callable[[str, str, dict[str, int]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise ApChannelLimitChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise ApChannelLimitChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise ApChannelLimitChangeError("plan_ttl_invalid")
        if not callable(clock):
            raise ApChannelLimitChangeError("clock_invalid")
        if type(limit) is not int or limit < 1:
            raise ApChannelLimitChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise ApChannelLimitChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise ApChannelLimitChangeError("journal_invalid")
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
            raise ApChannelLimitChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise ApChannelLimitChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise ApChannelLimitChangeError("journal_unavailable")
            operation = row.get("operation")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise ApChannelLimitChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref", "device_ref"}
                    or not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id)
                    or row.get("state") != "in_doubt" or plan_id in self.plans):
                raise ApChannelLimitChangeError("journal_unavailable")
            try:
                site_ref = _ref(refs["site_ref"], "journal_invalid")
                device_ref = _ref(refs["device_ref"], "journal_invalid")
                before, target = _journal_state(row.get("before")), _journal_state(row.get("target"))
            except ApChannelLimitChangeError:
                raise ApChannelLimitChangeError("journal_unavailable") from None
            if before == target:
                raise ApChannelLimitChangeError("journal_unavailable")
            self.plans[plan_id] = {
                "site_ref": site_ref, "device_ref": device_ref,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": float("inf"), "state": "in_doubt", "journaled": True,
            }

    def preview(self, site_ref: str, device_ref: str, change: object, *,
                disruption_confirmed: object = False) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        device_ref = _ref(device_ref, "device_ref_invalid")
        if type(disruption_confirmed) is not bool or disruption_confirmed is not True:
            raise ApChannelLimitChangeError("disruption_confirmation_required")
        target = _change(change)
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise ApChannelLimitChangeError("plan_capacity_reached")
            before = self._read_state(site_ref, device_ref)
            if target["channelLimitType"] == before["channelLimitType"]:
                raise ApChannelLimitChangeError("no_change")
            plan_id = secrets.token_hex(24)
            created = self.clock()
            self.plans[plan_id] = {
                "site_ref": site_ref, "device_ref": device_ref,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": created + self.ttl_seconds, "state": "pending",
            }
            return {"plan_id": plan_id, "scope": SCOPE, "site_ref": site_ref,
                    "device_ref": device_ref, "expires_in_seconds": self.ttl_seconds,
                    "before": copy.deepcopy(before), "target": copy.deepcopy(target),
                    "rollback": {"channelLimitType": before["channelLimitType"]},
                    "writes_enabled": self.writes_enabled,
                    "effect_note": "ap_channel_limit_effect_depends_on_controller"}

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise ApChannelLimitChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ApChannelLimitChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise ApChannelLimitChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise ApChannelLimitChangeError("plan_expired")

            site_ref, device_ref = plan["site_ref"], plan["device_ref"]
            current = self._read_state(site_ref, device_ref)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise ApChannelLimitChangeError("state_changed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise ApChannelLimitChangeError("plan_expired")
            if self.require_journal and self.journal is None:
                raise ApChannelLimitChangeError("journal_required")

            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation=OPERATION, plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "device_ref": device_ref},
                        before={"channelLimitType": plan["before"]["channelLimitType"]},
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise ApChannelLimitChangeError("journal_unavailable") from None

            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                self._record_unknown(plan_id, plan)
                raise ApChannelLimitChangeError("plan_expired")
            if self.journal is not None:
                # Recheck the full support/default-state snapshot after the
                # durable intent; a final external race remains without CAS.
                try:
                    dispatch_state = self._read_state(site_ref, device_ref)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise ApChannelLimitChangeError("state_changed")
                except Exception:
                    self._record_unknown(plan_id, plan)
                    raise ApChannelLimitChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    self._record_unknown(plan_id, plan)
                    raise ApChannelLimitChangeError("plan_expired")
            try:
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, device_ref, target)
                after = self._read_state(site_ref, device_ref)
                expected = copy.deepcopy(plan["before"])
                expected["channelLimitType"] = target["channelLimitType"]
                if after != expected:
                    raise ApChannelLimitChangeError("readback_mismatch")
            except Exception:
                self._record_unknown(plan_id, plan)
                raise ApChannelLimitChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise ApChannelLimitChangeError("change_in_doubt") from None
            plan["state"] = "applied"
            return {"status": "verified", "scope": SCOPE, "plan_id": plan_id,
                    "site_ref": site_ref, "device_ref": device_ref,
                    "before": copy.deepcopy(plan["before"]), "after": copy.deepcopy(target),
                    "rollback": {"channelLimitType": plan["before"]["channelLimitType"]}}

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
            return {"plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                    "scope": SCOPE, "target_refs": self._operator_refs(plan),
                    "before": copy.deepcopy(plan.get("before", {})),
                    "target": copy.deepcopy(plan.get("target", {})),
                    "current_observation": observation,
                    "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        with self.lock:
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise ApChannelLimitChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise ApChannelLimitChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise ApChannelLimitChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise ApChannelLimitChangeError("plan_not_in_doubt")
        return plan

    def _read_state(self, site_ref: str, device_ref: str) -> dict[str, object]:
        try:
            raw = self.read(site_ref, device_ref)
        except Exception:
            raise ApChannelLimitChangeError("readback_unavailable") from None
        return _read_state(raw)
