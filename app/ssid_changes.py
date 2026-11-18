"""Opt-in plans for the documented site-level SSID enable flag."""
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


class SsidChangeError(RuntimeError):
    """Stable, non-sensitive SSID plan error."""


_REF = re.compile(r"[0-9a-f]{24}\Z")


def _ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise SsidChangeError(code)
    return value


def _status(value: object) -> dict[str, bool]:
    if not isinstance(value, dict) or set(value) != {"ssidEnable"} or type(value["ssidEnable"]) is not bool:
        raise SsidChangeError("status_invalid")
    return {"ssidEnable": value["ssidEnable"]}


def _digest(value: dict[str, bool]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


class SsidChangePlans:
    """Plan one ``ssidEnable`` boolean change with readback and replay protection."""

    def __init__(self, read: Callable[[str, str], object],
                 write: Callable[[str, str, dict[str, bool]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise SsidChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise SsidChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise SsidChangeError("plan_ttl_invalid")
        if type(limit) is not int or limit < 1:
            raise SsidChangeError("plan_limit_invalid")
        if type(require_journal) is not bool:
            raise SsidChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise SsidChangeError("journal_invalid")
        self.read, self.write = read, write
        self.writes_enabled = writes_enabled
        self.ttl_seconds, self.clock, self.limit = ttl_seconds, clock, limit
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        self.journal, self.require_journal = journal, require_journal
        if journal is not None:
            self._recover_journal_plans()

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise SsidChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise SsidChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise SsidChangeError("journal_unavailable")
            operation = row.get("operation")
            if operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise SsidChangeError("journal_unavailable")
            if operation != "ssid":
                continue
            try:
                plan_id = row.get("plan_id")
                refs = row.get("target_refs")
                if not isinstance(refs, dict) or set(refs) != {"site_ref", "ssid_ref"}:
                    raise SsidChangeError("journal_invalid")
                site_ref = _ref(refs.get("site_ref"), "journal_invalid")
                ssid_ref = _ref(refs.get("ssid_ref"), "journal_invalid")
                before, target = _status(row.get("before")), _status(row.get("target"))
                if (not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{48}", plan_id)
                        or row.get("state") != "in_doubt"):
                    raise SsidChangeError("journal_invalid")
                if plan_id in self.plans:
                    raise SsidChangeError("journal_invalid")
            except SsidChangeError:
                raise SsidChangeError("journal_unavailable") from None
            self.plans[plan_id] = {
                "target_refs": (site_ref, ssid_ref), "before": before, "target": target,
                "before_hash": _digest(before), "expires": float("inf"),
                "state": "in_doubt", "journaled": True,
            }

    @staticmethod
    def _operator_refs(plan: dict[str, object]) -> dict[str, str | None]:
        refs = plan.get("target_refs")
        if not isinstance(refs, tuple) or len(refs) != 2:
            return {"site_ref": None, "ssid_ref": None}
        return {key: value if isinstance(value, str) and _REF.fullmatch(value) else None
                for key, value in zip(("site_ref", "ssid_ref"), refs)}

    def list_in_doubt(self) -> list[dict[str, object]]:
        """List unresolved plans using only opaque references; performs no I/O."""
        with self.lock:
            return [{"plan_id": ident, "state": "in_doubt", "scope": "ssid_enable",
                     "target_refs": self._operator_refs(plan)}
                    for ident, plan in self.plans.items() if plan.get("state") == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        """Inspect one unresolved plan without attributing current state to its write."""
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            site_ref, ssid_ref = plan["target_refs"]
            observation: dict[str, object] = {"status": "unavailable"}
            try:
                current = self._read_status(site_ref, ssid_ref)
                observation = {"status": "observed", "data": copy.deepcopy(current)}
            except Exception:
                pass
            return {"plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                    "scope": "ssid_enable", "target_refs": self._operator_refs(plan),
                    "before": copy.deepcopy(plan.get("before", {})),
                    "target": copy.deepcopy(plan.get("target", {})),
                    "current_observation": observation,
                    "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        """Close an unresolved plan without retry; its outcome remains unknown."""
        with self.lock:
            if confirmation != "outcome_unknown_no_retry":
                raise SsidChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise SsidChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": "ssid_enable", "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise SsidChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise SsidChangeError("plan_not_in_doubt")
        return plan

    def preview(self, site_ref: str, ssid_ref: str, change: object) -> dict[str, object]:
        site_ref = _ref(site_ref, "site_ref_invalid")
        ssid_ref = _ref(ssid_ref, "ssid_ref_invalid")
        if (not isinstance(change, dict) or set(change) != {"ssidEnable"} or
                type(change["ssidEnable"]) is not bool):
            raise SsidChangeError("change_invalid")

        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise SsidChangeError("plan_capacity_reached")
            before = self._read_status(site_ref, ssid_ref)
            target = {"ssidEnable": change["ssidEnable"]}
            if target == before:
                raise SsidChangeError("no_change")
            plan_id = secrets.token_hex(24)
            self.plans[plan_id] = {
                "target_refs": (site_ref, ssid_ref),
                "before": before,
                "target": target,
                "before_hash": _digest(before),
                "expires": now + self.ttl_seconds,
                "state": "pending",
            }
            return {
                "plan_id": plan_id,
                "site_ref": site_ref,
                "ssid_ref": ssid_ref,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before),
                "target": copy.deepcopy(target),
                "rollback": copy.deepcopy(before),
                "writes_enabled": self.writes_enabled,
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise SsidChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise SsidChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise SsidChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise SsidChangeError("plan_expired")

            site_ref, ssid_ref = plan["target_refs"]
            current = self._read_status(site_ref, ssid_ref)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise SsidChangeError("state_changed")
            # The read above may have consumed the remaining plan lifetime.
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise SsidChangeError("plan_expired")

            # Consume before dispatch: timeout may occur after a remote PATCH.
            if self.require_journal and self.journal is None:
                raise SsidChangeError("journal_required")
            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation="ssid", plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "ssid_ref": ssid_ref},
                        before=copy.deepcopy(plan["before"]),
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise SsidChangeError("journal_unavailable") from None
            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                try:
                    self.journal.record_outcome(plan_id, "unknown")
                except Exception:
                    pass
                raise SsidChangeError("plan_expired")
            if self.journal is not None:
                try:
                    dispatch_state = self._read_status(site_ref, ssid_ref)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise SsidChangeError("state_changed")
                except Exception:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    raise SsidChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    raise SsidChangeError("plan_expired")
            try:
                self.write(site_ref, ssid_ref, copy.deepcopy(plan["target"]))
                after = self._read_status(site_ref, ssid_ref)
                if after != plan["target"]:
                    raise SsidChangeError("readback_mismatch")
            except Exception:
                if plan.get("journaled"):
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                raise SsidChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise SsidChangeError("change_in_doubt") from None

            plan["state"] = "applied"
            return {"status": "verified", "plan_id": plan_id,
                    "before": copy.deepcopy(plan["before"]),
                    "after": copy.deepcopy(plan["target"]),
                    "rollback": copy.deepcopy(plan["before"])}

    def _read_status(self, site_ref: str, ssid_ref: str) -> dict[str, bool]:
        try:
            value = self.read(site_ref, ssid_ref)
        except Exception:
            raise SsidChangeError("readback_unavailable") from None
        return _status(value)
