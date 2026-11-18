"""Opt-in, one-use plans for site-wide gateway tag-outbound QoS."""
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


class GatewayTagQosChangeError(RuntimeError):
    """Stable, redacted error for a gateway tag-QoS plan."""


SCOPE = "gateway_tag_outbound_traffic"
OPERATION = "gateway-tag-qos"
_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_CLASSES = frozenset({0, 1, 2, 3})
# Canonical decimal strings from the three supplied descriptions. Values such
# as "08" are deliberately not normalized or accepted.
_DSCP_VALUES = frozenset({
    "8", "16", "24", "32", "40", "48", "56", "10", "12", "14", "18", "20",
    "22", "26", "28", "30", "34", "36", "38", "46",
})


def _site_ref(value: object, code: str = "site_ref_invalid") -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise GatewayTagQosChangeError(code)
    return value


def _state(value: object, code: str = "state_invalid") -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"tagConfigList"}:
        raise GatewayTagQosChangeError(code)
    rows = value.get("tagConfigList")
    if not isinstance(rows, list) or len(rows) != 4:
        raise GatewayTagQosChangeError(code)
    seen: set[int] = set()
    result: list[dict[str, object]] = []
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"classType", "enable", "dscp"} or
                type(row.get("classType")) is not int or row["classType"] not in _CLASSES or
                row["classType"] in seen or type(row.get("enable")) is not bool or
                not isinstance(row.get("dscp"), str) or row["dscp"] not in _DSCP_VALUES):
            raise GatewayTagQosChangeError(code)
        seen.add(row["classType"])
        result.append({"classType": row["classType"], "enable": row["enable"],
                       "dscp": row["dscp"]})
    if seen != _CLASSES:
        raise GatewayTagQosChangeError(code)
    return {"tagConfigList": result}


def _change(value: object) -> dict[str, object]:
    if (not isinstance(value, dict) or set(value) != {"classType", "enable"} or
            type(value.get("classType")) is not int or value["classType"] not in _CLASSES or
            type(value.get("enable")) is not bool):
        raise GatewayTagQosChangeError("change_invalid")
    return {"classType": value["classType"], "enable": value["enable"]}


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _valid_transition(before: dict[str, object], target: dict[str, object]) -> bool:
    before_rows = before.get("tagConfigList")
    target_rows = target.get("tagConfigList")
    if not isinstance(before_rows, list) or not isinstance(target_rows, list) or len(before_rows) != 4 or len(target_rows) != 4:
        return False
    changed = 0
    for old, new in zip(before_rows, target_rows):
        if (not isinstance(old, dict) or not isinstance(new, dict) or
                old.get("classType") != new.get("classType") or
                old.get("dscp") != new.get("dscp")):
            return False
        if old.get("enable") != new.get("enable"):
            changed += 1
    return changed == 1


class GatewayTagQosPlans:
    """Plan one class enable toggle while preserving all four full-state rows."""

    def __init__(self, read: Callable[[str], object],
                 write: Callable[[str, dict[str, object]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise GatewayTagQosChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise GatewayTagQosChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds != 300:
            raise GatewayTagQosChangeError("plan_ttl_invalid")
        if not callable(clock):
            raise GatewayTagQosChangeError("clock_invalid")
        if type(limit) is not int or limit < 1:
            raise GatewayTagQosChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise GatewayTagQosChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise GatewayTagQosChangeError("journal_invalid")
        self.read, self.write = read, write
        self.writes_enabled, self.ttl_seconds = writes_enabled, ttl_seconds
        self.clock, self.limit = clock, limit
        self.journal, self.require_journal = journal, require_journal
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        if journal is not None:
            self._recover_journal_plans()

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise GatewayTagQosChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise GatewayTagQosChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise GatewayTagQosChangeError("journal_unavailable")
            operation = row.get("operation")
            if not isinstance(operation, str) or operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise GatewayTagQosChangeError("journal_unavailable")
            if operation != OPERATION:
                continue
            refs, plan_id = row.get("target_refs"), row.get("plan_id")
            if (not isinstance(refs, dict) or set(refs) != {"site_ref"} or
                    not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id) or
                    row.get("state") != "in_doubt" or plan_id in self.plans):
                raise GatewayTagQosChangeError("journal_unavailable")
            try:
                site_ref = _site_ref(refs["site_ref"], "journal_invalid")
                before = _state(row.get("before"), "journal_invalid")
                target = _state(row.get("target"), "journal_invalid")
            except GatewayTagQosChangeError:
                raise GatewayTagQosChangeError("journal_unavailable") from None
            if not _valid_transition(before, target):
                raise GatewayTagQosChangeError("journal_unavailable")
            self.plans[plan_id] = {
                "site_ref": site_ref, "before": before, "target": target,
                "before_hash": _digest(before), "expires": float("inf"),
                "state": "in_doubt", "journaled": True,
            }

    def preview(self, site_ref: str, change: object, *,
                disruption_confirmed: object = False) -> dict[str, object]:
        site_ref = _site_ref(site_ref)
        if type(disruption_confirmed) is not bool or disruption_confirmed is not True:
            raise GatewayTagQosChangeError("disruption_confirmation_required")
        delta = _change(change)
        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise GatewayTagQosChangeError("plan_capacity_reached")
            before = self._read_state(site_ref)
            target = copy.deepcopy(before)
            rows = target["tagConfigList"]
            assert isinstance(rows, list)
            matching = [row for row in rows if row["classType"] == delta["classType"]]
            if len(matching) != 1:
                raise GatewayTagQosChangeError("state_invalid")
            if matching[0]["enable"] is delta["enable"]:
                raise GatewayTagQosChangeError("no_change")
            matching[0]["enable"] = delta["enable"]
            if not _valid_transition(before, target):
                raise GatewayTagQosChangeError("change_invalid")
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
                    "warning": "This site-wide QoS configuration may affect traffic prioritization across the site; the controller-specific effect and outcome are not guaranteed."}

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise GatewayTagQosChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise GatewayTagQosChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise GatewayTagQosChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise GatewayTagQosChangeError("plan_expired")
            site_ref = plan["site_ref"]
            current = self._read_state(site_ref)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise GatewayTagQosChangeError("state_changed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise GatewayTagQosChangeError("plan_expired")
            if self.require_journal and self.journal is None:
                raise GatewayTagQosChangeError("journal_required")
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
                    raise GatewayTagQosChangeError("journal_unavailable") from None

            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                self._record_unknown(plan_id, plan)
                raise GatewayTagQosChangeError("plan_expired")
            if self.journal is not None:
                try:
                    dispatch_state = self._read_state(site_ref)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise GatewayTagQosChangeError("state_changed")
                except Exception:
                    self._record_unknown(plan_id, plan)
                    raise GatewayTagQosChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    self._record_unknown(plan_id, plan)
                    raise GatewayTagQosChangeError("plan_expired")
            try:
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, target)
                after = self._read_state(site_ref)
                if after != target:
                    raise GatewayTagQosChangeError("readback_mismatch")
            except Exception:
                self._record_unknown(plan_id, plan)
                raise GatewayTagQosChangeError("change_in_doubt") from None
            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise GatewayTagQosChangeError("change_in_doubt") from None
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
                     "target_refs": {"site_ref": plan["site_ref"]}}
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
                    "scope": SCOPE, "target_refs": {"site_ref": plan["site_ref"]},
                    "before": copy.deepcopy(plan.get("before", {})),
                    "target": copy.deepcopy(plan.get("target", {})),
                    "current_observation": observation,
                    "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        with self.lock:
            if type(confirmation) is not str or confirmation != "outcome_unknown_no_retry":
                raise GatewayTagQosChangeError("operator_confirmation_required")
            self._require_in_doubt(plan_id)
            refs = {"site_ref": self.plans[plan_id]["site_ref"]}
            if self.plans[plan_id].get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise GatewayTagQosChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise GatewayTagQosChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise GatewayTagQosChangeError("plan_not_in_doubt")
        return plan

    def _read_state(self, site_ref: str) -> dict[str, object]:
        try:
            return _state(self.read(site_ref))
        except Exception:
            raise GatewayTagQosChangeError("readback_unavailable") from None
