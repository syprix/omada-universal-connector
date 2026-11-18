import unittest
from unittest.mock import patch

from app import ap_afc_changes as afc
from app.approval_plans import build_approval_summary


SITE = "a" * 24
DEVICE = "b" * 24


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
            raise OSError("private journal path")
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


class ApAfcPlanTests(unittest.TestCase):
    def setUp(self):
        self.state = {"supportAfc": True, "enable": False}
        self.writes = []
        self.journal = FakeJournal()

    def read(self, site_ref, device_ref):
        self.assertEqual((site_ref, device_ref), (SITE, DEVICE))
        return dict(self.state)

    def write(self, site_ref, device_ref, change):
        self.writes.append((site_ref, device_ref, dict(change)))
        self.state = {"supportAfc": True, **change}

    def manager(self, **kwargs):
        return afc.ApAfcPlans(self.read, self.write, **kwargs)

    def preview(self, manager, enabled=True):
        return manager.preview(SITE, DEVICE, {"enable": enabled}, disruption_confirmed=True)

    def test_preview_requires_acknowledgement_and_warns_without_claims(self):
        manager = self.manager()
        with self.assertRaisesRegex(afc.ApAfcChangeError, "disruption_confirmation_required"):
            manager.preview(SITE, DEVICE, {"enable": True})
        preview = self.preview(manager)
        self.assertEqual(preview["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(preview["target"], {"enable": True})
        self.assertEqual(preview["rollback"], {"enable": False})
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(preview["warning"], "afc_configuration_or_behavior_may_affect_this_ap")
        self.assertEqual(self.writes, [])

    def test_pending_approval_snapshot_binds_support_but_target_is_enable_only(self):
        manager = self.manager()
        plan_id = self.preview(manager)["plan_id"]
        plan = manager.plans[plan_id]
        self.assertEqual(plan["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(plan["target"], {"enable": True})
        summary = build_approval_summary("ap-afc", plan_id, manager)
        self.assertEqual(summary["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(summary["target"], {"enable": True})
        self.assertEqual(summary["before_hash"], afc._digest({"supportAfc": True, "enable": False}))

    def test_invalid_support_and_schema_block_preview(self):
        invalid = [
            {"supportAfc": False, "enable": False},
            {"enable": False},
            {"supportAfc": 1, "enable": False},
            {"supportAfc": True, "enable": 0},
            {"supportAfc": True, "enable": False, "extra": 1},
        ]
        for state in invalid:
            with self.subTest(state=state):
                manager = afc.ApAfcPlans(lambda _site, _device, s=state: s, self.write)
                with self.assertRaises(afc.ApAfcChangeError):
                    manager.preview(SITE, DEVICE, {"enable": True}, disruption_confirmed=True)

    def test_invalid_support_blocks_apply_without_writing(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state = {"supportAfc": False, "enable": False}
        with self.assertRaisesRegex(afc.ApAfcChangeError, "afc_unsupported"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.journal.events, [])

    def test_default_off_and_required_journal_fail_closed(self):
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(afc.ApAfcChangeError, "journal_required"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        readonly = self.manager()
        plan = self.preview(readonly)["plan_id"]
        with self.assertRaisesRegex(afc.ApAfcChangeError, "writes_disabled"):
            readonly.apply(plan)
        self.assertEqual(self.writes, [])

    def test_success_journals_only_enable_and_dispatches_once(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        result = manager.apply(plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(result["rollback"], {"enable": False})
        self.assertEqual(self.writes, [(SITE, DEVICE, {"enable": True})])
        intent = self.journal.events[0][1]
        self.assertEqual(intent["operation"], "ap-afc")
        self.assertEqual(intent["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(intent["before"], {"enable": False})
        self.assertEqual(intent["target"], {"enable": True})
        self.assertNotIn("supportAfc", str(intent))
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "verified_readback"))
        with self.assertRaisesRegex(afc.ApAfcChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_stale_read_and_failed_intent_prevent_write(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state["enable"] = True
        with self.assertRaisesRegex(afc.ApAfcChangeError, "state_changed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        self.state = {"supportAfc": True, "enable": False}
        self.journal.fail_intent = True
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(afc.ApAfcChangeError, "journal_unavailable"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_dispatch_recheck_requires_support_and_target_value(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]

        reads = [0]
        def unsupported_postread(_site, _device):
            reads[0] += 1
            if reads[0] == 1:  # fresh pre-dispatch check
                return {"supportAfc": True, "enable": False}
            return {"supportAfc": False, "enable": True}

        manager.read = unsupported_postread
        with self.assertRaisesRegex(afc.ApAfcChangeError, "change_in_doubt"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 0)
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "unknown"))

    def test_expiry_before_write_and_after_intent_fsync(self):
        now = [0.0]
        manager = afc.ApAfcPlans(self.read, self.write, writes_enabled=True,
                                 clock=lambda: now[0], journal=self.journal,
                                 require_journal=True)
        plan = self.preview(manager)["plan_id"]
        now[0] = 300
        with self.assertRaisesRegex(afc.ApAfcChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        now[0] = 400
        plan = self.preview(manager)["plan_id"]
        self.journal.after_intent = lambda: now.__setitem__(0, 700)
        with self.assertRaisesRegex(afc.ApAfcChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_timeout_recovery_close_no_replay_and_no_support_invention(self):
        def timeout(site_ref, device_ref, change):
            self.writes.append((site_ref, device_ref, dict(change)))
            raise TimeoutError("controller detail")

        manager = afc.ApAfcPlans(self.read, timeout, writes_enabled=True,
                                 journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(afc.ApAfcChangeError, "change_in_doubt"):
            manager.apply(plan)
        with self.assertRaisesRegex(afc.ApAfcChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

        with patch.object(afc, "ALLOWED_JOURNAL_OPERATIONS",
                          afc.ALLOWED_JOURNAL_OPERATIONS | {"ap-afc"}):
            recovered = afc.ApAfcPlans(self.read, self.write, writes_enabled=True,
                                       journal=self.journal)
        recovered_plan = recovered.plans[plan]
        self.assertNotIn("supportAfc", recovered_plan["before"])
        self.assertNotIn("supportAfc", recovered_plan["target"])
        self.assertEqual(recovered_plan["before"], {"enable": False})
        inspected = recovered.inspect_in_doubt(plan)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertIn("does_not_prove", inspected["observation_note"])
        self.assertEqual(inspected["current_observation"]["data"],
                         {"supportAfc": True, "enable": False})
        with self.assertRaisesRegex(afc.ApAfcChangeError, "operator_confirmation_required"):
            recovered.close_in_doubt(plan, "retry")
        self.assertEqual(recovered.close_in_doubt(plan, "outcome_unknown_no_retry")["state"],
                         "closed_outcome_unknown")
        with self.assertRaisesRegex(afc.ApAfcChangeError, "plan_unknown"):
            recovered.apply(plan)
        self.assertEqual(len(self.writes), 1)


if __name__ == "__main__":
    unittest.main()
