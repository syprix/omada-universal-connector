"""Opt-in, bounded plans for site-wide DNS cache settings."""
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


class DnsCacheChangeError(RuntimeError):
    """Stable, non-sensitive DNS cache plan error."""


_FIELDS = frozenset(("enable", "ttl"))
_SITE_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")


def _state(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise DnsCacheChangeError("state_invalid")
    enable, ttl = value["enable"], value["ttl"]
    if type(enable) is not bool or type(ttl) is not int or not 1 <= ttl <= 86400:
        raise DnsCacheChangeError("state_invalid")
    return {"enable": enable, "ttl": ttl}


def _site_ref(value: object) -> str:
    if not isinstance(value, str) or not _SITE_REF.fullmatch(value):
        raise DnsCacheChangeError("site_ref_invalid")
    return value


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


class DnsCacheChangePlans:
    """Plans a single DNS cache field while always writing/verifying full state.

    ``read(site_ref)`` must return exactly ``enable`` and ``ttl``. ``write``
    receives the complete target state. A dispatched write is never repeated,
    including when its outcome or its readback is uncertain.
    """

    def __init__(self, read: Callable[[str], object], write: Callable[[str, dict[str, object]], object],
                 *, writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal=None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise DnsCacheChangeError("callbacks_invalid")
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise DnsCacheChangeError("plan_ttl_invalid")
        if type(limit) is not int or limit < 1:
            raise DnsCacheChangeError("plan_limit_invalid")
        if type(writes_enabled) is not bool:
            raise DnsCacheChangeError("writes_enabled_invalid")
        self.read = read
        self.write = write
        self.writes_enabled = writes_enabled
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.limit = limit
        self.journal = journal
        self.require_journal = require_journal
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        if journal is not None:
            try:
                for item in journal.in_doubt_plans():
                    operation = item.get("operation") if isinstance(item, dict) else None
                    if operation not in ALLOWED_JOURNAL_OPERATIONS:
                        raise DnsCacheChangeError("journal_unavailable")
                    if operation != "dns-cache":
                        continue
                    refs = item.get("target_refs")
                    if (not isinstance(item, dict) or set(item) != {
                            "plan_id", "operation", "target_refs", "before", "target", "state"} or
                            not isinstance(item.get("plan_id"), str) or
                            not _PLAN_ID.fullmatch(item["plan_id"]) or item.get("state") != "in_doubt" or
                            not isinstance(refs, dict) or set(refs) != {"site_ref"} or
                            not isinstance(refs.get("site_ref"), str) or
                            not _SITE_REF.fullmatch(refs["site_ref"]) or
                            _state(item.get("before")) != item.get("before") or
                            _state(item.get("target")) != item.get("target")):
                        raise DnsCacheChangeError("journal_unavailable")
                    self.plans[item["plan_id"]] = {
                        "site_ref": refs["site_ref"],
                        "before": copy.deepcopy(item["before"]),
                        "target": copy.deepcopy(item["target"]),
                        "state": "in_doubt", "journalled": True,
                        "expires": float("inf"),
                    }
            except Exception:
                raise DnsCacheChangeError("journal_unavailable") from None

    def _operator_refs(self, plan: dict[str, object]) -> dict[str, str | None]:
        value = plan.get("site_ref")
        safe = value if isinstance(value, str) and _SITE_REF.fullmatch(value) else None
        return {"site_ref": safe}

    def list_in_doubt(self) -> list[dict[str, object]]:
        """List unresolved plans using only opaque references; performs no I/O."""
        with self.lock:
            return [{"plan_id": ident, "state": "in_doubt", "scope": "dns_cache_settings",
                     "target_refs": self._operator_refs(plan)}
                    for ident, plan in self.plans.items() if plan.get("state") == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        """Inspect one unresolved plan without attributing current state to its write."""
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            observation: dict[str, object] = {"status": "unavailable"}
            try:
                current = self._read_state(plan["site_ref"])
                observation = {"status": "observed", "data": copy.deepcopy(current)}
            except Exception:
                pass
            return {"plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                    "scope": "dns_cache_settings", "target_refs": self._operator_refs(plan),
                    "before": copy.deepcopy(plan.get("before", {})),
                    "target": copy.deepcopy(plan.get("target", {})),
                    "current_observation": observation,
                    "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        """Close an unresolved plan without retry; its outcome remains unknown."""
        with self.lock:
            if confirmation != "outcome_unknown_no_retry":
                raise DnsCacheChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journalled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise DnsCacheChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": "dns_cache_settings", "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise DnsCacheChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise DnsCacheChangeError("plan_not_in_doubt")
        return plan

    def preview(self, site_ref: str, change: object) -> dict[str, object]:
        site_ref = _site_ref(site_ref)
        if not isinstance(change, dict) or len(change) != 1 or not set(change).issubset(_FIELDS):
            raise DnsCacheChangeError("change_invalid")
        field, value = next(iter(change.items()))
        if field == "enable":
            if type(value) is not bool:
                raise DnsCacheChangeError("change_invalid")
        elif field == "ttl":
            if type(value) is not int or not 1 <= value <= 86400:
                raise DnsCacheChangeError("change_invalid")
        else:
            raise DnsCacheChangeError("change_invalid")

        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise DnsCacheChangeError("plan_capacity_reached")
            before = self._read_state(site_ref)
            target = copy.deepcopy(before)
            target[field] = value
            if target == before:
                raise DnsCacheChangeError("no_change")
            ident = secrets.token_hex(24)
            self.plans[ident] = {
                "site_ref": site_ref,
                "before": before,
                "target": target,
                "before_hash": _digest(before),
                "expires": now + self.ttl_seconds,
                "state": "pending",
            }
            return {
                "plan_id": ident,
                "site_ref": site_ref,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before),
                "target": copy.deepcopy(target),
                "rollback": copy.deepcopy(before),
                "writes_enabled": self.writes_enabled,
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise DnsCacheChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise DnsCacheChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise DnsCacheChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise DnsCacheChangeError("plan_expired")
            if self.require_journal and self.journal is None:
                raise DnsCacheChangeError("journal_required")

            site_ref = plan["site_ref"]
            current = self._read_state(site_ref)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise DnsCacheChangeError("state_changed")
            # The GET above may consume most or all remaining plan lifetime.
            # Check again as close as possible to dispatch, while still pending.
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise DnsCacheChangeError("plan_expired")

            if self.journal is not None:
                refs = self._operator_refs(plan)
                if refs["site_ref"] is None:
                    plan["state"] = "in_doubt"
                    plan["journalled"] = True
                    raise DnsCacheChangeError("journal_unavailable")
                try:
                    self.journal.record_dispatch_intent(
                        operation="dns-cache", plan_id=plan_id, target_refs=refs,
                        before=copy.deepcopy(plan["before"]),
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    plan["journalled"] = True
                    raise DnsCacheChangeError("journal_unavailable") from None
                plan["journalled"] = True
                if self.clock() >= plan["expires"]:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    plan["state"] = "in_doubt"
                    raise DnsCacheChangeError("plan_expired")
                try:
                    dispatch_state = self._read_state(site_ref)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise DnsCacheChangeError("state_changed")
                except Exception:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    plan["state"] = "in_doubt"
                    raise DnsCacheChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    plan["state"] = "in_doubt"
                    raise DnsCacheChangeError("plan_expired")

            # Consume before dispatch: a timeout may happen after the remote PUT.
            plan["state"] = "in_doubt"
            try:
                self.write(site_ref, copy.deepcopy(plan["target"]))
                after = self._read_state(site_ref)
                if after != plan["target"]:
                    raise DnsCacheChangeError("readback_mismatch")
            except Exception:
                if plan.get("journalled"):
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                raise DnsCacheChangeError("change_in_doubt") from None

            if plan.get("journalled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                    raise DnsCacheChangeError("change_in_doubt") from None

            plan["state"] = "applied"
            return {"status": "verified", "plan_id": plan_id,
                    "before": copy.deepcopy(plan["before"]),
                    "after": copy.deepcopy(plan["target"]),
                    "rollback": copy.deepcopy(plan["before"])}

    def _read_state(self, site_ref: str) -> dict[str, object]:
        try:
            raw = self.read(site_ref)
        except Exception:
            raise DnsCacheChangeError("readback_unavailable") from None
        return _state(raw)
