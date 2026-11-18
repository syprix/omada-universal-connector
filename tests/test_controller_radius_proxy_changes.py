import unittest

from app.approval_plans import build_approval_summary
from app.controller_radius_proxy_changes import (
    ControllerRadiusProxyChangeError,
    ControllerRadiusProxyPlans,
)


class Journal:
    def __init__(self):
        self.intents = []
        self.outcomes = []
        self.closed = []

    def in_doubt_plans(self):
        return []

    def record_dispatch_intent(self, **item):
        self.intents.append(item)

    def record_outcome(self, plan_id, outcome):
        self.outcomes.append((plan_id, outcome))

    def close_unknown(self, plan_id, confirmation):
        self.closed.append((plan_id, confirmation))


class ControllerRadiusProxyChangeTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.state = {
            "enable": False,
            "port": 1812,
            "requireMessageAuthenticator": None,
            "limitProxyState": None,
        }
        self.writes = []
        self.journal = Journal()

    def manager(self, *, enabled=False, write=None, read=None):
        return ControllerRadiusProxyPlans(
            read or (lambda: dict(self.state)),
            write or (lambda body: self.writes.append(dict(body))),
            writes_enabled=enabled,
            clock=lambda: self.now,
            journal=self.journal,
        )

    def test_preview_emits_minimal_patch_and_approval_snapshot(self):
        manager = self.manager()
        preview = manager.preview({"enable": True})
        self.assertEqual(preview["patch"], {"enable": True, "port": 1812})
        self.assertEqual(preview["rollback"], {"enable": False, "port": 1812})
        self.assertFalse(preview["writes_enabled"])
        summary = build_approval_summary("controller-radius-proxy", preview["plan_id"], manager)
        self.assertEqual(summary["operation"], "controller-radius-proxy")
        self.assertEqual(summary["target_refs"], {})
        self.assertIsNone(summary["before"]["requireMessageAuthenticator"])

    def test_preview_rejects_noop_invalid_and_incomplete_observation(self):
        manager = self.manager()
        with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "no_change"):
            manager.preview({"port": 1812})
        for invalid in ({}, {"port": True}, {"port": 2**31}, {"enable": 1},
                        {"unknown": True}):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "change_invalid"):
                    manager.preview(invalid)
        incomplete = self.manager(read=lambda: {**self.state, "extra": False})
        with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "state_unavailable"):
            incomplete.preview({"enable": True})

    def test_apply_requires_enabled_write_and_fresh_state(self):
        disabled = self.manager()
        pending = disabled.preview({"enable": True})
        with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "writes_disabled"):
            disabled.apply(pending["plan_id"])
        manager = self.manager(enabled=True)
        pending = manager.preview({"enable": True})
        self.state["port"] = 1813
        with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "state_changed"):
            manager.apply(pending["plan_id"])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.journal.intents, [])

    def test_apply_journals_then_verifies_and_records_outcome(self):
        manager = self.manager(enabled=True)
        pending = manager.preview({"enable": True, "port": 1813})

        def write(body):
            self.writes.append(dict(body))
            self.state.update(body)

        manager.write = write
        result = manager.apply(pending["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [{"enable": True, "port": 1813}])
        self.assertEqual(len(self.journal.intents), 1)
        self.assertEqual(self.journal.intents[0]["target_refs"], {})
        self.assertEqual(self.journal.outcomes, [(pending["plan_id"], "verified_readback")])

    def test_failed_dispatch_is_in_doubt_and_is_never_retried(self):
        manager = self.manager(enabled=True, write=lambda _body: (_ for _ in ()).throw(TimeoutError()))
        pending = manager.preview({"enable": True})
        with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "change_in_doubt"):
            manager.apply(pending["plan_id"])
        self.assertEqual(self.journal.outcomes, [(pending["plan_id"], "unknown")])
        with self.assertRaisesRegex(ControllerRadiusProxyChangeError, "plan_already_consumed"):
            manager.apply(pending["plan_id"])
        self.assertEqual(len(self.journal.intents), 1)

    def test_unobserved_optional_fields_are_not_written(self):
        manager = self.manager(enabled=True)
        pending = manager.preview({"port": 1813})

        def write(body):
            self.writes.append(dict(body))
            self.state.update(body)

        manager.write = write
        manager.apply(pending["plan_id"])
        self.assertEqual(self.writes, [{"enable": False, "port": 1813}])


if __name__ == "__main__":
    unittest.main()
