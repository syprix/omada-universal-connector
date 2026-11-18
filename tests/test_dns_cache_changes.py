from __future__ import annotations

import unittest

from app.dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans


SITE = "a" * 24


class DnsCacheChangePlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {"enable": True, "ttl": 600}
        self.writes: list[dict[str, object]] = []

        def read(site_ref: str):
            self.assertEqual(site_ref, SITE)
            return dict(self.state)

        def write(site_ref: str, target: dict[str, object]):
            self.assertEqual(site_ref, SITE)
            self.writes.append(dict(target))
            self.state = dict(target)

        self.engine = DnsCacheChangePlans(read, write, writes_enabled=True)

    def test_preview_changes_one_field_and_returns_rollback_state(self) -> None:
        preview = self.engine.preview(SITE, {"ttl": 900})
        self.assertEqual(preview["site_ref"], SITE)
        self.assertRegex(preview["site_ref"], r"^[0-9a-f]{24}$")
        self.assertNotIn("raw-site-id", str(preview))
        self.assertEqual(preview["before"], {"enable": True, "ttl": 600})
        self.assertEqual(preview["target"], {"enable": True, "ttl": 900})
        self.assertEqual(preview["rollback"], {"enable": True, "ttl": 600})
        self.assertEqual(self.writes, [])

    def test_preview_rejects_unchanged_values_without_creating_plan(self) -> None:
        for change in ({"enable": True}, {"ttl": 600}):
            with self.subTest(change=change), self.assertRaisesRegex(DnsCacheChangeError, "no_change"):
                self.engine.preview(SITE, change)
        self.assertEqual(self.engine.plans, {})
        self.assertEqual(self.writes, [])

    def test_default_disabled_and_verified_full_state_write(self) -> None:
        self.engine.writes_enabled = False
        preview = self.engine.preview(SITE, {"enable": False})
        with self.assertRaisesRegex(DnsCacheChangeError, "writes_disabled"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(self.writes, [])

        self.engine.writes_enabled = True
        preview = self.engine.preview(SITE, {"enable": False})
        applied = self.engine.apply(preview["plan_id"])
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["after"], {"enable": False, "ttl": 600})
        self.assertEqual(self.writes, [{"enable": False, "ttl": 600}])
        with self.assertRaisesRegex(DnsCacheChangeError, "consumed"):
            self.engine.apply(preview["plan_id"])

    def test_rollback_requires_a_separate_preview_plan(self) -> None:
        first = self.engine.preview(SITE, {"ttl": 900})
        self.engine.apply(first["plan_id"])
        rollback = self.engine.preview(SITE, {"ttl": first["rollback"]["ttl"]})
        result = self.engine.apply(rollback["plan_id"])
        self.assertEqual(result["after"], {"enable": True, "ttl": 600})
        self.assertEqual(len(self.writes), 2)

    def test_changed_state_expiry_and_capacity_never_write(self) -> None:
        preview = self.engine.preview(SITE, {"ttl": 700})
        self.state["enable"] = False
        with self.assertRaisesRegex(DnsCacheChangeError, "state_changed"):
            self.engine.apply(preview["plan_id"])
        self.assertEqual(self.writes, [])

        now = [1.0]
        self.engine = DnsCacheChangePlans(lambda _: dict(self.state),
                                          lambda *_: self.fail("expired plan wrote"),
                                          writes_enabled=True, ttl_seconds=5,
                                          clock=lambda: now[0], limit=1)
        expired = self.engine.preview(SITE, {"ttl": 800})
        now[0] = 6.0
        with self.assertRaisesRegex(DnsCacheChangeError, "plan_expired"):
            self.engine.apply(expired["plan_id"])
        replacement = self.engine.preview(SITE, {"ttl": 900})
        with self.assertRaisesRegex(DnsCacheChangeError, "plan_capacity_reached"):
            self.engine.preview(SITE, {"ttl": 1000})
        self.assertEqual(self.writes, [])

    def test_expiry_during_pre_dispatch_read_prevents_write(self) -> None:
        now = [1.0]
        calls = [0]

        def read(_site_ref):
            calls[0] += 1
            if calls[0] == 2:  # The apply-time GET reaches the plan deadline.
                now[0] = 6.0
            return {"enable": True, "ttl": 600}

        writes: list[dict[str, object]] = []
        engine = DnsCacheChangePlans(read, lambda _site, body: writes.append(body),
                                     writes_enabled=True, ttl_seconds=5,
                                     clock=lambda: now[0])
        preview = engine.preview(SITE, {"ttl": 700})
        with self.assertRaisesRegex(DnsCacheChangeError, "plan_expired"):
            engine.apply(preview["plan_id"])
        self.assertEqual(writes, [])
        with self.assertRaisesRegex(DnsCacheChangeError, "consumed"):
            engine.apply(preview["plan_id"])

    def test_write_failure_or_readback_mismatch_is_in_doubt_and_not_replayed(self) -> None:
        preview = self.engine.preview(SITE, {"ttl": 800})

        def uncertain_write(site_ref, target):
            self.state = dict(target)
            raise TimeoutError()

        self.engine.write = uncertain_write
        with self.assertRaisesRegex(DnsCacheChangeError, "change_in_doubt"):
            self.engine.apply(preview["plan_id"])
        with self.assertRaisesRegex(DnsCacheChangeError, "consumed"):
            self.engine.apply(preview["plan_id"])

        self.engine = DnsCacheChangePlans(lambda _: dict(self.state), lambda *_: None,
                                          writes_enabled=True)
        mismatch = self.engine.preview(SITE, {"ttl": 900})
        with self.assertRaisesRegex(DnsCacheChangeError, "change_in_doubt"):
            self.engine.apply(mismatch["plan_id"])
        with self.assertRaisesRegex(DnsCacheChangeError, "consumed"):
            self.engine.apply(mismatch["plan_id"])

    def test_rejects_bad_references_changes_and_read_states(self) -> None:
        for ref in ("bad", "A" * 24, "a" * 23):
            with self.subTest(ref=ref), self.assertRaisesRegex(DnsCacheChangeError, "site_ref_invalid"):
                self.engine.preview(ref, {"enable": False})
        for change in ({}, {"enable": 1}, {"ttl": True}, {"ttl": 0},
                       {"ttl": 86401}, {"enable": False, "ttl": 500}, {"other": 1}):
            with self.subTest(change=change), self.assertRaises(DnsCacheChangeError):
                self.engine.preview(SITE, change)

        for bad_state in ({"enable": True}, {"enable": True, "ttl": 600, "extra": 1},
                          {"enable": 1, "ttl": 600}, {"enable": False, "ttl": True},
                          {"enable": True, "ttl": 86401}):
            self.engine.read = lambda _, bad_state=bad_state: bad_state
            with self.subTest(state=bad_state), self.assertRaisesRegex(DnsCacheChangeError, "state_invalid"):
                self.engine.preview(SITE, {"ttl": 700})


if __name__ == "__main__":
    unittest.main()
