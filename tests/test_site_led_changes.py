import unittest
from unittest.mock import patch

from app import site_led_changes as led


SITE = "a" * 24


class FakeJournal:
    def __init__(self):
        self.rows = []
        self.events = []
        self.fail_intent = False
        self.after_intent = None

    def in_doubt_plans(self):
        return [dict(row) for row in self.rows if row["state"] == "in_doubt"]

    def record_dispatch_intent(self, **event):
        if self.fail_intent:
            raise OSError("sensitive path detail")
        self.events.append(("intent", event.copy()))
        self.rows.append({**event, "state": "in_doubt"})
        if self.after_intent:
            self.after_intent()

    def record_outcome(self, plan_id, outcome):
        self.events.append(("outcome", plan_id, outcome))
        if outcome == "verified_readback":
            for row in self.rows:
                if row["plan_id"] == plan_id:
                    row["state"] = "verified"

    def close_unknown(self, plan_id, confirmation):
        self.events.append(("close", plan_id, confirmation))
        for row in self.rows:
            if row["plan_id"] == plan_id:
                row["state"] = "closed"


class SiteLedPlanTests(unittest.TestCase):
    def setUp(self):
        self.state = {"enable": False}
        self.writes = []
        self.journal = FakeJournal()

    def read(self, site_ref):
        self.assertEqual(site_ref, SITE)
        return dict(self.state)

    def write(self, site_ref, value):
        self.writes.append((site_ref, dict(value)))
        self.state = dict(value)

    def manager(self, **kwargs):
        return led.SiteLedPlans(self.read, self.write, **kwargs)

    def preview(self, manager, enable=True):
        return manager.preview(SITE, {"enable": enable})

    def test_preview_has_controller_scope_note_and_never_writes(self):
        manager = self.manager()
        preview = self.preview(manager)
        self.assertEqual(preview["before"], {"enable": False})
        self.assertEqual(preview["target"], {"enable": True})
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(preview["effect_note"], "site_led_effect_depends_on_controller")
        self.assertEqual(self.writes, [])

    def test_exact_boolean_state_and_change_schema(self):
        manager = self.manager()
        for change in ({"enable": 1}, {"enable": "true"}, {"enable": True, "extra": False}, {}):
            with self.subTest(change=change), self.assertRaises(led.SiteLedChangeError):
                manager.preview(SITE, change)
        for state in ({"enable": 1}, {}, {"enable": False, "extra": False}):
            bad = led.SiteLedPlans(lambda _site, s=state: s, self.write)
            with self.subTest(state=state), self.assertRaisesRegex(led.SiteLedChangeError, "state_invalid"):
                bad.preview(SITE, {"enable": True})
        with self.assertRaisesRegex(led.SiteLedChangeError, "no_change"):
            manager.preview(SITE, {"enable": False})

    def test_default_off_and_required_journal_fail_closed(self):
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(led.SiteLedChangeError, "journal_required"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        readonly = self.manager()
        plan = self.preview(readonly)["plan_id"]
        with self.assertRaisesRegex(led.SiteLedChangeError, "writes_disabled"):
            readonly.apply(plan)
        self.assertEqual(self.writes, [])

    def test_success_records_intent_before_one_write_and_readback(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        result = manager.apply(plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [(SITE, {"enable": True})])
        self.assertEqual(self.journal.events[0][0], "intent")
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "verified_readback"))
        with self.assertRaisesRegex(led.SiteLedChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_stale_plan_and_failed_journal_intent_never_write(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state = {"enable": True}
        with self.assertRaisesRegex(led.SiteLedChangeError, "state_changed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        self.state = {"enable": False}
        self.journal.fail_intent = True
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(led.SiteLedChangeError, "journal_unavailable"):
            manager.apply(plan)
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")
        self.assertEqual(self.writes, [])

    def test_expiry_checked_before_apply_and_after_intent_fsync(self):
        now = [0.0]
        manager = led.SiteLedPlans(self.read, self.write, writes_enabled=True,
                                   clock=lambda: now[0], journal=self.journal,
                                   require_journal=True)
        plan = self.preview(manager)["plan_id"]
        now[0] = 300.0
        with self.assertRaisesRegex(led.SiteLedChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        now[0] = 400.0
        plan = self.preview(manager)["plan_id"]
        self.journal.after_intent = lambda: now.__setitem__(0, 700.0)
        with self.assertRaisesRegex(led.SiteLedChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_timeout_recovery_close_and_replay_block(self):
        def timeout(site_ref, value):
            self.writes.append((site_ref, dict(value)))
            raise TimeoutError("controller details")

        manager = led.SiteLedPlans(self.read, timeout, writes_enabled=True,
                                   journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(led.SiteLedChangeError, "change_in_doubt"):
            manager.apply(plan)
        with self.assertRaisesRegex(led.SiteLedChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

        with patch.object(led, "ALLOWED_JOURNAL_OPERATIONS",
                          led.ALLOWED_JOURNAL_OPERATIONS | {"site-led"}):
            recovered = led.SiteLedPlans(self.read, self.write, writes_enabled=True,
                                         journal=self.journal)
        inspected = recovered.inspect_in_doubt(plan)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertIn("does_not_prove", inspected["observation_note"])
        with self.assertRaisesRegex(led.SiteLedChangeError, "operator_confirmation_required"):
            recovered.close_in_doubt(plan, "retry")
        self.assertEqual(recovered.close_in_doubt(plan, "outcome_unknown_no_retry")["state"],
                         "closed_outcome_unknown")
        self.assertEqual(self.journal.events[-1], ("close", plan, "outcome_unknown_no_retry"))
        self.assertEqual(recovered.list_in_doubt(), [])
        with self.assertRaisesRegex(led.SiteLedChangeError, "plan_unknown"):
            recovered.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_recovery_rejects_invalid_schema_and_operation(self):
        row = {"operation": "site-led", "plan_id": "f" * 48, "state": "in_doubt",
               "target_refs": {"site_ref": SITE}, "before": {"enable": False},
               "target": {"enable": True}}
        self.journal.rows = [row]
        with patch.object(led, "ALLOWED_JOURNAL_OPERATIONS",
                          led.ALLOWED_JOURNAL_OPERATIONS | {"site-led"}):
            recovered = self.manager(journal=self.journal)
            self.assertEqual(recovered.list_in_doubt()[0]["plan_id"], "f" * 48)

        self.journal.rows = [{**row, "target": {"enable": 1}}]
        with patch.object(led, "ALLOWED_JOURNAL_OPERATIONS",
                          led.ALLOWED_JOURNAL_OPERATIONS | {"site-led"}):
            with self.assertRaisesRegex(led.SiteLedChangeError, "journal_unavailable"):
                self.manager(journal=self.journal)

        self.journal.rows = [{**row, "operation": "unknown-operation"}]
        with patch.object(led, "ALLOWED_JOURNAL_OPERATIONS",
                          led.ALLOWED_JOURNAL_OPERATIONS | {"site-led"}):
            with self.assertRaisesRegex(led.SiteLedChangeError, "journal_unavailable"):
                self.manager(journal=self.journal)


if __name__ == "__main__":
    unittest.main()
