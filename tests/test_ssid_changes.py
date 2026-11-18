from __future__ import annotations

import unittest

from app.ssid_changes import SsidChangeError, SsidChangePlans


SITE = "a" * 24
SSID = "b" * 24


class SsidChangePlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.status = {"ssidEnable": True}
        self.writes: list[tuple[str, str, dict[str, bool]]] = []

        def read(site_ref: str, ssid_ref: str):
            self.assertEqual((site_ref, ssid_ref), (SITE, SSID))
            return dict(self.status)

        def write(site_ref: str, ssid_ref: str, target: dict[str, bool]):
            self.writes.append((site_ref, ssid_ref, dict(target)))
            self.status = dict(target)

        self.engine = SsidChangePlans(read, write, writes_enabled=True)

    def test_preview_only_plans_boolean_and_returns_rollback(self) -> None:
        preview = self.engine.preview(SITE, SSID, {"ssidEnable": False})
        self.assertEqual(preview["site_ref"], SITE)
        self.assertEqual(preview["ssid_ref"], SSID)
        self.assertRegex(preview["site_ref"], r"^[0-9a-f]{24}$")
        self.assertRegex(preview["ssid_ref"], r"^[0-9a-f]{24}$")
        self.assertNotIn("raw-site-id", str(preview))
        self.assertNotIn("private-ssid", str(preview))
        self.assertEqual(preview["before"], {"ssidEnable": True})
        self.assertEqual(preview["target"], {"ssidEnable": False})
        self.assertEqual(preview["rollback"], {"ssidEnable": True})
        self.assertEqual(self.writes, [])

    def test_default_off_and_verified_single_patch(self) -> None:
        self.engine.writes_enabled = False
        preview = self.engine.preview(SITE, SSID, {"ssidEnable": False})
        self.assertFalse(preview["writes_enabled"])
        with self.assertRaisesRegex(SsidChangeError, "writes_disabled"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(self.writes, [])

        self.engine.writes_enabled = True
        preview = self.engine.preview(SITE, SSID, {"ssidEnable": False})
        result = self.engine.apply(preview["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [(SITE, SSID, {"ssidEnable": False})])
        with self.assertRaisesRegex(SsidChangeError, "plan_already_consumed"):
            self.engine.apply(preview["plan_id"])

    def test_rollback_requires_a_new_preview(self) -> None:
        first = self.engine.preview(SITE, SSID, {"ssidEnable": False})
        self.engine.apply(first["plan_id"])
        rollback = self.engine.preview(SITE, SSID, first["rollback"])
        result = self.engine.apply(rollback["plan_id"])
        self.assertEqual(result["after"], {"ssidEnable": True})
        self.assertEqual(len(self.writes), 2)

    def test_noop_stale_expired_capacity_and_expiry_during_read(self) -> None:
        with self.assertRaisesRegex(SsidChangeError, "no_change"):
            self.engine.preview(SITE, SSID, {"ssidEnable": True})
        self.assertEqual(self.engine.plans, {})

        stale = self.engine.preview(SITE, SSID, {"ssidEnable": False})
        self.status["ssidEnable"] = False
        with self.assertRaisesRegex(SsidChangeError, "state_changed"):
            self.engine.apply(stale["plan_id"])
        self.assertEqual(self.writes, [])

        now = [5.0]
        calls = [0]

        def read(_site, _ssid):
            calls[0] += 1
            if calls[0] == 2:
                now[0] = 10.0
            return {"ssidEnable": True}

        expiring = SsidChangePlans(read, lambda *_: self.fail("expired plan wrote"),
                                   writes_enabled=True, ttl_seconds=5,
                                   clock=lambda: now[0], limit=1)
        plan = expiring.preview(SITE, SSID, {"ssidEnable": False})
        with self.assertRaisesRegex(SsidChangeError, "plan_expired"):
            expiring.apply(plan["plan_id"])
        with self.assertRaisesRegex(SsidChangeError, "plan_already_consumed"):
            expiring.apply(plan["plan_id"])
        replacement = expiring.preview(SITE, SSID, {"ssidEnable": False})
        self.assertFalse(expiring.plans[replacement["plan_id"]]["state"] == "expired")

    def test_timeout_and_readback_mismatch_are_in_doubt_without_replay(self) -> None:
        plan = self.engine.preview(SITE, SSID, {"ssidEnable": False})

        def uncertain_write(site_ref, ssid_ref, target):
            self.status = dict(target)
            raise TimeoutError()

        self.engine.write = uncertain_write
        with self.assertRaisesRegex(SsidChangeError, "change_in_doubt"):
            self.engine.apply(plan["plan_id"])
        with self.assertRaisesRegex(SsidChangeError, "plan_already_consumed"):
            self.engine.apply(plan["plan_id"])

        mismatch = SsidChangePlans(lambda *_: {"ssidEnable": True}, lambda *_: None,
                                   writes_enabled=True)
        plan = mismatch.preview(SITE, SSID, {"ssidEnable": False})
        with self.assertRaisesRegex(SsidChangeError, "change_in_doubt"):
            mismatch.apply(plan["plan_id"])
        with self.assertRaisesRegex(SsidChangeError, "plan_already_consumed"):
            mismatch.apply(plan["plan_id"])

    def test_invalid_refs_fields_and_missing_readback_block_safely(self) -> None:
        for args in (("bad", SSID), (SITE, "BAD" * 8)):
            with self.subTest(args=args), self.assertRaises(SsidChangeError):
                self.engine.preview(args[0], args[1], {"ssidEnable": False})
        for change in ({}, {"ssidEnable": 0}, {"ssidEnable": None},
                       {"ssidEnable": False, "extra": True}, {"enable": False}):
            with self.subTest(change=change), self.assertRaisesRegex(SsidChangeError, "change_invalid"):
                self.engine.preview(SITE, SSID, change)

        for bad_status in (None, {}, {"ssidEnable": 1},
                           {"ssidEnable": True, "unknown": "discard-me"}):
            self.engine.read = lambda *_args, bad_status=bad_status: bad_status
            with self.subTest(status=bad_status), self.assertRaisesRegex(SsidChangeError, "status_invalid"):
                self.engine.preview(SITE, SSID, {"ssidEnable": False})

        self.engine.read = lambda *_: (_ for _ in ()).throw(RuntimeError("unsupported API"))
        with self.assertRaisesRegex(SsidChangeError, "readback_unavailable"):
            self.engine.preview(SITE, SSID, {"ssidEnable": False})


if __name__ == "__main__":
    unittest.main()
