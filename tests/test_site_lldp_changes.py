import unittest
from unittest.mock import patch

from app import site_lldp_changes as lldp


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
            raise OSError("private journal information")
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


class SiteLldpPlanTests(unittest.TestCase):
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
        return lldp.SiteLldpPlans(self.read, self.write, **kwargs)

    def preview(self, manager, enabled=True):
        return manager.preview(SITE, {"enable": enabled}, disruption_confirmed=True)

    def test_preview_requires_confirmation_and_only_states_controller_uncertainty(self):
        manager = self.manager()
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "disruption_confirmation_required"):
            manager.preview(SITE, {"enable": True})
        preview = self.preview(manager)
        self.assertEqual(preview["before"], {"enable": False})
        self.assertEqual(preview["target"], {"enable": True})
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(preview["effect_note"], "site_lldp_device_effect_depends_on_controller")
        self.assertEqual(self.writes, [])

    def test_exact_boolean_schema_and_no_change(self):
        manager = self.manager()
        for change in ({"enable": 1}, {"enable": "true"},
                       {"enable": True, "extra": False}, {}):
            with self.subTest(change=change), self.assertRaises(lldp.SiteLldpChangeError):
                manager.preview(SITE, change, disruption_confirmed=True)
        for state in ({"enable": 1}, {}, {"enable": False, "extra": 0}):
            bad = lldp.SiteLldpPlans(lambda _site, s=state: s, self.write)
            with self.subTest(state=state), self.assertRaisesRegex(lldp.SiteLldpChangeError, "state_invalid"):
                bad.preview(SITE, {"enable": True}, disruption_confirmed=True)
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "no_change"):
            manager.preview(SITE, {"enable": False}, disruption_confirmed=True)

    def test_default_off_and_required_journal_fail_closed(self):
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "journal_required"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        readonly = self.manager()
        plan = self.preview(readonly)["plan_id"]
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "writes_disabled"):
            readonly.apply(plan)
        self.assertEqual(self.writes, [])

    def test_intent_then_one_write_and_verified_readback(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        result = manager.apply(plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [(SITE, {"enable": True})])
        intent = self.journal.events[0][1]
        self.assertEqual(intent["operation"], "site-lldp")
        self.assertEqual(intent["target_refs"], {"site_ref": SITE})
        self.assertEqual(intent["before"], {"enable": False})
        self.assertEqual(intent["target"], {"enable": True})
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "verified_readback"))
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_stale_and_failed_intent_prevent_write(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state["enable"] = True
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "state_changed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        self.state = {"enable": False}
        self.journal.fail_intent = True
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "journal_unavailable"):
            manager.apply(plan)
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")
        self.assertEqual(self.writes, [])

    def test_ttl_checked_before_apply_and_after_intent_fsync(self):
        now = [0.0]
        manager = lldp.SiteLldpPlans(self.read, self.write, writes_enabled=True,
                                     clock=lambda: now[0], journal=self.journal,
                                     require_journal=True)
        plan = self.preview(manager)["plan_id"]
        now[0] = 300.0
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        now[0] = 400.0
        plan = self.preview(manager)["plan_id"]
        self.journal.after_intent = lambda: now.__setitem__(0, 700.0)
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_timeout_recovery_close_and_replay_block(self):
        def timeout(site_ref, change):
            self.writes.append((site_ref, dict(change)))
            raise TimeoutError("controller details")

        manager = lldp.SiteLldpPlans(self.read, timeout, writes_enabled=True,
                                     journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "change_in_doubt"):
            manager.apply(plan)
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

        with patch.object(lldp, "ALLOWED_JOURNAL_OPERATIONS",
                          lldp.ALLOWED_JOURNAL_OPERATIONS | {"site-lldp"}):
            recovered = lldp.SiteLldpPlans(self.read, self.write, writes_enabled=True,
                                           journal=self.journal)
        inspected = recovered.inspect_in_doubt(plan)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertIn("does_not_prove", inspected["observation_note"])
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "operator_confirmation_required"):
            recovered.close_in_doubt(plan, "retry")
        self.assertEqual(recovered.close_in_doubt(plan, "outcome_unknown_no_retry")["state"],
                         "closed_outcome_unknown")
        self.assertEqual(self.journal.events[-1], ("close", plan, "outcome_unknown_no_retry"))
        self.assertEqual(recovered.list_in_doubt(), [])
        with self.assertRaisesRegex(lldp.SiteLldpChangeError, "plan_unknown"):
            recovered.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_recovery_rejects_invalid_rows(self):
        row = {"operation": "site-lldp", "plan_id": "f" * 48, "state": "in_doubt",
               "target_refs": {"site_ref": SITE}, "before": {"enable": False},
               "target": {"enable": True}}
        self.journal.rows = [row]
        with patch.object(lldp, "ALLOWED_JOURNAL_OPERATIONS",
                          lldp.ALLOWED_JOURNAL_OPERATIONS | {"site-lldp"}):
            recovered = self.manager(journal=self.journal)
            self.assertEqual(recovered.list_in_doubt()[0]["plan_id"], "f" * 48)
        self.journal.rows = [{**row, "target": {"enable": 1}}]
        with patch.object(lldp, "ALLOWED_JOURNAL_OPERATIONS",
                          lldp.ALLOWED_JOURNAL_OPERATIONS | {"site-lldp"}):
            with self.assertRaisesRegex(lldp.SiteLldpChangeError, "journal_unavailable"):
                self.manager(journal=self.journal)


if __name__ == "__main__":
    unittest.main()
