"""Opt-in plans for one gateway's IPv6 IP-passthrough enable flag.

The documented OpenAPI shape is GET/PATCH
``/sites/{siteId}/gateways/{gatewayMac}/network/ipv6`` with a single Boolean
``enable`` field. This is specifically an IP-passthrough setting, not a general
IPv6 control. The route/schema appears in the supplied Hardware Controller
6.3.0, ER7212PC 6.2.14, and Omada CBC Standard 6.3.0 exports.
"""
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


class GatewayIpv6ChangeError(RuntimeError):
    """Stable error for a gateway IPv6 IP-passthrough change plan."""


SCOPE = "gateway_ipv6_ip_passthrough"
_FIELDS = frozenset(("enable",))
_REF = re.compile(r"[0-9a-f]{24}\Z")


def _reference(value: object, code: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise GatewayIpv6ChangeError(code)
    return value


def _state(value: object) -> dict[str, bool]:
    if not isinstance(value, dict) or set(value) != _FIELDS or type(value.get("enable")) is not bool:
        raise GatewayIpv6ChangeError("state_invalid")
    return {"enable": value["enable"]}


def _digest(value: dict[str, bool]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


class GatewayIpv6IpPassthroughPlans:
    """Prepare and verify one ``enable`` Boolean with a short-lived plan.

    ``read(site_ref, gateway_ref)`` returns exactly ``{"enable": bool}``.
    ``write(site_ref, gateway_ref, patch)`` receives exactly one Boolean field.
    Rollback is never automatic; prepare it as a separate preview using the
    prior value returned by the original plan/application.
    """

    def __init__(self, read: Callable[[str, str], object],
                 write: Callable[[str, str, dict[str, bool]], object], *,
                 writes_enabled: bool = False, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic, limit: int = 100,
                 journal: object | None = None, require_journal: bool = False):
        if not callable(read) or not callable(write):
            raise GatewayIpv6ChangeError("callbacks_invalid")
        if type(writes_enabled) is not bool:
            raise GatewayIpv6ChangeError("writes_enabled_invalid")
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise GatewayIpv6ChangeError("plan_ttl_invalid")
        if type(limit) is not int or limit < 1:
            raise GatewayIpv6ChangeError("plan_limit_invalid")
        if not callable(clock):
            raise GatewayIpv6ChangeError("clock_invalid")
        if type(require_journal) is not bool:
            raise GatewayIpv6ChangeError("require_journal_invalid")
        if journal is not None and not callable(getattr(journal, "record_dispatch_intent", None)):
            raise GatewayIpv6ChangeError("journal_invalid")
        self.read = read
        self.write = write
        self.writes_enabled = writes_enabled
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.limit = limit
        self.plans: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()
        self.journal, self.require_journal = journal, require_journal
        if journal is not None:
            self._recover_journal_plans()

    def _recover_journal_plans(self) -> None:
        try:
            rows = self.journal.in_doubt_plans()
        except Exception:
            raise GatewayIpv6ChangeError("journal_unavailable") from None
        if not isinstance(rows, list):
            raise GatewayIpv6ChangeError("journal_unavailable")
        for row in rows:
            if not isinstance(row, dict):
                raise GatewayIpv6ChangeError("journal_unavailable")
            operation = row.get("operation")
            if operation not in ALLOWED_JOURNAL_OPERATIONS:
                raise GatewayIpv6ChangeError("journal_unavailable")
            if operation != "gateway-ipv6":
                continue
            try:
                plan_id, refs = row.get("plan_id"), row.get("target_refs")
                if not isinstance(refs, dict) or set(refs) != {"site_ref", "gateway_ref"}:
                    raise GatewayIpv6ChangeError("journal_invalid")
                site_ref = _reference(refs.get("site_ref"), "journal_invalid")
                gateway_ref = _reference(refs.get("gateway_ref"), "journal_invalid")
                before, target = _state(row.get("before")), _state(row.get("target"))
                if (not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{48}", plan_id)
                        or row.get("state") != "in_doubt"):
                    raise GatewayIpv6ChangeError("journal_invalid")
                if plan_id in self.plans:
                    raise GatewayIpv6ChangeError("journal_invalid")
            except GatewayIpv6ChangeError:
                raise GatewayIpv6ChangeError("journal_unavailable") from None
            self.plans[plan_id] = {
                "site_ref": site_ref, "gateway_ref": gateway_ref,
                "before": before, "target": target, "before_hash": _digest(before),
                "expires": float("inf"), "state": "in_doubt", "journaled": True,
            }

    @staticmethod
    def _operator_refs(plan: dict[str, object]) -> dict[str, str | None]:
        refs = (plan.get("site_ref"), plan.get("gateway_ref"))
        return {key: value if isinstance(value, str) and _REF.fullmatch(value) else None
                for key, value in zip(("site_ref", "gateway_ref"), refs)}

    def list_in_doubt(self) -> list[dict[str, object]]:
        """List unresolved plans using only opaque references; performs no I/O."""
        with self.lock:
            return [{"plan_id": ident, "state": "in_doubt", "scope": SCOPE,
                     "target_refs": self._operator_refs(plan)}
                    for ident, plan in self.plans.items() if plan.get("state") == "in_doubt"]

    def inspect_in_doubt(self, plan_id: str) -> dict[str, object]:
        """Inspect one unresolved plan without attributing current state to its write."""
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            observation: dict[str, object] = {"status": "unavailable"}
            try:
                current = self._read_state(plan["site_ref"], plan["gateway_ref"])
                observation = {"status": "observed", "data": copy.deepcopy(current)}
            except Exception:
                pass
            return {"plan_id": plan_id, "state": "in_doubt", "outcome": "unknown",
                    "scope": SCOPE, "target_refs": self._operator_refs(plan),
                    "before": copy.deepcopy(plan.get("before", {})),
                    "target": copy.deepcopy(plan.get("target", {})),
                    "current_observation": observation,
                    "observation_note": "current_state_does_not_prove_original_write_outcome"}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict[str, object]:
        """Close an unresolved plan without retry; its outcome remains unknown."""
        with self.lock:
            if confirmation != "outcome_unknown_no_retry":
                raise GatewayIpv6ChangeError("operator_confirmation_required")
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get("journaled"):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise GatewayIpv6ChangeError("journal_unavailable") from None
            del self.plans[plan_id]
            return {"plan_id": plan_id, "state": "closed_outcome_unknown",
                    "scope": SCOPE, "target_refs": refs}

    def _require_in_doubt(self, plan_id: str) -> dict[str, object]:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise GatewayIpv6ChangeError("plan_unknown")
        if plan.get("state") != "in_doubt":
            raise GatewayIpv6ChangeError("plan_not_in_doubt")
        return plan

    def preview(self, site_ref: str, gateway_ref: str,
                change: object) -> dict[str, object]:
        site_ref = _reference(site_ref, "site_ref_invalid")
        gateway_ref = _reference(gateway_ref, "gateway_ref_invalid")
        if (not isinstance(change, dict) or len(change) != 1 or
                set(change) != _FIELDS or type(change.get("enable")) is not bool):
            raise GatewayIpv6ChangeError("change_invalid")

        with self.lock:
            now = self.clock()
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan["state"] == "in_doubt" or now < plan["expires"]}
            if len(self.plans) >= self.limit:
                raise GatewayIpv6ChangeError("plan_capacity_reached")
            before = self._read_state(site_ref, gateway_ref)
            target = {"enable": change["enable"]}
            if target == before:
                raise GatewayIpv6ChangeError("no_change")
            plan_id = secrets.token_hex(24)
            self.plans[plan_id] = {
                "site_ref": site_ref,
                "gateway_ref": gateway_ref,
                "before": before,
                "target": target,
                "before_hash": _digest(before),
                "expires": now + self.ttl_seconds,
                "state": "pending",
            }
            return {
                "plan_id": plan_id,
                "scope": SCOPE,
                "site_ref": site_ref,
                "gateway_ref": gateway_ref,
                "expires_in_seconds": self.ttl_seconds,
                "before": copy.deepcopy(before),
                "target": copy.deepcopy(target),
                "rollback": copy.deepcopy(before),
                "writes_enabled": self.writes_enabled,
                "warning": "may_affect_gateway_ipv6_ip_passthrough_connectivity",
            }

    def apply(self, plan_id: str) -> dict[str, object]:
        with self.lock:
            if not self.writes_enabled:
                raise GatewayIpv6ChangeError("writes_disabled")
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise GatewayIpv6ChangeError("plan_unknown")
            if plan["state"] != "pending":
                raise GatewayIpv6ChangeError("plan_already_consumed")
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise GatewayIpv6ChangeError("plan_expired")

            site_ref, gateway_ref = plan["site_ref"], plan["gateway_ref"]
            current = self._read_state(site_ref, gateway_ref)
            if _digest(current) != plan["before_hash"]:
                plan["state"] = "stale"
                raise GatewayIpv6ChangeError("state_changed")
            # A slow GET must not allow a plan to cross its deadline before PATCH.
            if self.clock() >= plan["expires"]:
                plan["state"] = "expired"
                raise GatewayIpv6ChangeError("plan_expired")

            # Consume before dispatch: a timeout may happen after the PATCH landed.
            if self.require_journal and self.journal is None:
                raise GatewayIpv6ChangeError("journal_required")
            if self.journal is not None:
                plan["journaled"] = True
                try:
                    self.journal.record_dispatch_intent(
                        operation="gateway-ipv6", plan_id=plan_id,
                        target_refs={"site_ref": site_ref, "gateway_ref": gateway_ref},
                        before=copy.deepcopy(plan["before"]),
                        target=copy.deepcopy(plan["target"]))
                except Exception:
                    plan["state"] = "in_doubt"
                    raise GatewayIpv6ChangeError("journal_unavailable") from None
            plan["state"] = "in_doubt"
            plan["journaled"] = self.journal is not None
            if self.journal is not None and self.clock() >= plan["expires"]:
                self._record_unknown(plan_id, plan)
                raise GatewayIpv6ChangeError("plan_expired")
            if self.journal is not None:
                try:
                    dispatch_state = self._read_state(site_ref, gateway_ref)
                    if _digest(dispatch_state) != plan["before_hash"]:
                        raise GatewayIpv6ChangeError("state_changed")
                except Exception:
                    self._record_unknown(plan_id, plan)
                    raise GatewayIpv6ChangeError("change_in_doubt") from None
                if self.clock() >= plan["expires"]:
                    self._record_unknown(plan_id, plan)
                    raise GatewayIpv6ChangeError("plan_expired")
            try:
                target = copy.deepcopy(plan["target"])
                self.write(site_ref, gateway_ref, target)
                after = self._read_state(site_ref, gateway_ref)
                if after != target:
                    raise GatewayIpv6ChangeError("readback_mismatch")
            except Exception:
                if plan.get("journaled"):
                    try:
                        self.journal.record_outcome(plan_id, "unknown")
                    except Exception:
                        pass
                raise GatewayIpv6ChangeError("change_in_doubt") from None

            if plan.get("journaled"):
                try:
                    self.journal.record_outcome(plan_id, "verified_readback")
                except Exception:
                    raise GatewayIpv6ChangeError("change_in_doubt") from None

            plan["state"] = "applied"
            return {
                "status": "verified",
                "scope": SCOPE,
                "plan_id": plan_id,
                "site_ref": site_ref,
                "gateway_ref": gateway_ref,
                "before": copy.deepcopy(plan["before"]),
                "after": copy.deepcopy(target),
                "rollback": copy.deepcopy(plan["before"]),
            }

    def _read_state(self, site_ref: str, gateway_ref: str) -> dict[str, bool]:
        try:
            raw = self.read(site_ref, gateway_ref)
        except Exception:
            raise GatewayIpv6ChangeError("readback_unavailable") from None
        return _state(raw)

    def _record_unknown(self, plan_id: str, plan: dict[str, object]) -> None:
        if not plan.get("journaled"):
            return
        try:
            self.journal.record_outcome(plan_id, "unknown")
        except Exception:
            pass
