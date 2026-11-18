from __future__ import annotations

import unittest

from app.gateway_ipv6_changes import (
    GatewayIpv6ChangeError,
    GatewayIpv6IpPassthroughPlans,
    SCOPE,
)


SITE_REF = "a" * 24
GATEWAY_REF = "b" * 24


class GatewayIpv6IpPassthroughPlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {"enable": False}
        self.reads: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, dict[str, bool]]] = []

        def read(site_ref: str, gateway_ref: str):
            self.reads.append((site_ref, gateway_ref))
            return dict(self.state)

        def write(site_ref: str, gateway_ref: str, patch: dict[str, bool]):
            self.writes.append((site_ref, gateway_ref, dict(patch)))
            self.state = dict(patch)

        self.read = read
        self.write = write
        self.engine = GatewayIpv6IpPassthroughPlans(read, write, writes_enabled=True)

    def test_preview_is_one_boolean_scoped_and_performs_no_write(self) -> None:
        result = self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        self.assertEqual(result["scope"], "gateway_ipv6_ip_passthrough")
        self.assertEqual(result["site_ref"], SITE_REF)
        self.assertEqual(result["gateway_ref"], GATEWAY_REF)
        self.assertEqual(result["before"], {"enable": False})
        self.assertEqual(result["target"], {"enable": True})
        self.assertEqual(result["rollback"], {"enable": False})
        self.assertEqual(result["writes_enabled"], True)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.reads, [(SITE_REF, GATEWAY_REF)])
        self.assertNotIn("raw-site-id", str(result))
        self.assertNotIn("raw-gateway-mac", str(result))

    def test_default_off_and_exact_single_write_then_readback(self) -> None:
        self.engine = GatewayIpv6IpPassthroughPlans(self.read, self.write)
        plan = self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "writes_disabled"):
            self.engine.apply(plan["plan_id"])
        self.assertEqual(self.writes, [])

        self.engine.writes_enabled = True
        result = self.engine.apply(plan["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["scope"], SCOPE)
        self.assertEqual(result["after"], {"enable": True})
        self.assertEqual(self.writes, [(SITE_REF, GATEWAY_REF, {"enable": True})])
        self.assertEqual(self.reads, [(SITE_REF, GATEWAY_REF)] * 3)
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "consumed"):
            self.engine.apply(plan["plan_id"])
        self.assertEqual(len(self.writes), 1)

    def test_unchanged_value_and_invalid_scope_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "no_change"):
            self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": False})
        for site_ref in ("bad", "A" * 24, "a" * 23):
            with self.subTest(site_ref=site_ref), self.assertRaisesRegex(
                    GatewayIpv6ChangeError, "site_ref_invalid"):
                self.engine.preview(site_ref, GATEWAY_REF, {"enable": True})
        for gateway_ref in ("bad", "B" * 24, "b" * 23):
            with self.subTest(gateway_ref=gateway_ref), self.assertRaisesRegex(
                    GatewayIpv6ChangeError, "gateway_ref_invalid"):
                self.engine.preview(SITE_REF, gateway_ref, {"enable": True})
        for change in ({}, {"enable": 1}, {"enable": None}, {"enable": True, "mode": 1},
                       {"ipv6_enable": True}):
            with self.subTest(change=change), self.assertRaisesRegex(
                    GatewayIpv6ChangeError, "change_invalid"):
                self.engine.preview(SITE_REF, GATEWAY_REF, change)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.engine.plans, {})

    def test_changed_before_state_expiry_and_capacity_never_write(self) -> None:
        stale = self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        self.state["enable"] = True
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "state_changed"):
            self.engine.apply(stale["plan_id"])
        self.assertEqual(self.writes, [])

        now = [10.0]
        engine = GatewayIpv6IpPassthroughPlans(
            self.read, self.write, writes_enabled=True, ttl_seconds=5,
            clock=lambda: now[0], limit=1)
        self.state["enable"] = False
        expired = engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        now[0] = 15.0
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "plan_expired"):
            engine.apply(expired["plan_id"])
        now[0] = 16.0
        replacement = engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "plan_capacity_reached"):
            engine.preview(SITE_REF, GATEWAY_REF, {"enable": False})
        self.assertEqual(self.writes, [])
        self.assertNotEqual(expired["plan_id"], replacement["plan_id"])

    def test_expiry_during_apply_read_prevents_patch(self) -> None:
        now = [0.0]
        calls = [0]

        def slow_read(_site_ref, _gateway_ref):
            calls[0] += 1
            if calls[0] == 2:
                now[0] = 5.0
            return {"enable": False}

        writes: list[object] = []
        engine = GatewayIpv6IpPassthroughPlans(
            slow_read, lambda *args: writes.append(args), writes_enabled=True,
            ttl_seconds=5, clock=lambda: now[0])
        preview = engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        now[0] = 1.0
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "plan_expired"):
            engine.apply(preview["plan_id"])
        self.assertEqual(writes, [])
        self.assertEqual(engine.plans[preview["plan_id"]]["state"], "expired")

    def test_uncertain_write_and_mismatched_readback_are_in_doubt_not_replayed(self) -> None:
        preview = self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})

        def uncertain(_site_ref, _gateway_ref, patch):
            self.state = dict(patch)
            raise TimeoutError("private controller detail")

        self.engine.write = uncertain
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "change_in_doubt") as caught:
            self.engine.apply(preview["plan_id"])
        self.assertNotIn("private controller detail", str(caught.exception))
        self.assertEqual(self.engine.plans[preview["plan_id"]]["state"], "in_doubt")
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "consumed"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(len(self.writes), 0)

        self.state = {"enable": False}
        engine = GatewayIpv6IpPassthroughPlans(self.read, lambda *_args: None,
                                                writes_enabled=True)
        mismatch = engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "change_in_doubt"):
            engine.apply(mismatch["plan_id"])
        self.assertEqual(engine.plans[mismatch["plan_id"]]["state"], "in_doubt")
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "consumed"):
            engine.apply(mismatch["plan_id"])

    def test_rollback_is_a_new_plan_and_new_single_write(self) -> None:
        first = self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        applied = self.engine.apply(first["plan_id"])
        rollback = self.engine.preview(SITE_REF, GATEWAY_REF, applied["rollback"])
        self.assertNotEqual(first["plan_id"], rollback["plan_id"])
        self.assertEqual(rollback["target"], {"enable": False})
        rolled_back = self.engine.apply(rollback["plan_id"])
        self.assertEqual(rolled_back["after"], {"enable": False})
        self.assertEqual(self.writes, [
            (SITE_REF, GATEWAY_REF, {"enable": True}),
            (SITE_REF, GATEWAY_REF, {"enable": False}),
        ])

    def test_invalid_or_unavailable_readback_never_creates_plan_or_leaks_details(self) -> None:
        for value in ({}, {"enable": 1}, {"enable": True, "raw": "private"},
                      {"enable": None}):
            self.engine.read = lambda _site, _gateway, value=value: value
            with self.subTest(value=value), self.assertRaisesRegex(
                    GatewayIpv6ChangeError, "state_invalid"):
                self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        self.engine.read = lambda *_args: (_ for _ in ()).throw(
            RuntimeError("private network payload"))
        with self.assertRaisesRegex(GatewayIpv6ChangeError, "readback_unavailable") as caught:
            self.engine.preview(SITE_REF, GATEWAY_REF, {"enable": True})
        self.assertNotIn("private network payload", str(caught.exception))
        self.assertEqual(self.engine.plans, {})
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
