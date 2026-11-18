import unittest
from unittest.mock import patch

from app import rrm_mode_changes as rrm


SITE = "a" * 24
BASE = {"mode": 0, "timeRangeEnable": False, "resource": 2,
        "timeRangeId": "", "timeRangeAction": 1}


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
            raise OSError("private journal detail")
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


class RrmModePlanTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(BASE)
        self.writes = []
        self.journal = FakeJournal()

    def read(self, site_ref):
        self.assertEqual(site_ref, SITE)
        return dict(self.state)

    def write(self, site_ref, value):
        self.writes.append((site_ref, dict(value)))
        self.state = dict(value)

    def manager(self, **kwargs):
        return rrm.RrmModePlans(self.read, self.write, **kwargs)

    def preview(self, manager, mode=1):
        return manager.preview(SITE, {"mode": mode}, disruption_confirmed=True)

    def test_preview_requires_ack_and_preserves_full_safe_state(self):
        manager = self.manager()
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "disruption_confirmation_required"):
            manager.preview(SITE, {"mode": 1})
        preview = self.preview(manager)
        expected = dict(BASE, mode=1)
        self.assertEqual(preview["before"], BASE)
        self.assertEqual(preview["target"], expected)
        self.assertEqual(preview["rollback"], BASE)
        self.assertEqual(preview["warning"],
                         "rrm_optimization_may_change_wifi_radio_parameters_or_interrupt_connections")
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(self.writes, [])

    def test_only_exact_mode_change_input_is_accepted(self):
        manager = self.manager()
        for change in ({"mode": True}, {"mode": 2}, {"mode": -1},
                       {"mode": 1, "resource": 0}, {}, {"mode": "1"}):
            with self.subTest(change=change), self.assertRaises(rrm.RrmModeChangeError):
                manager.preview(SITE, change, disruption_confirmed=True)
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "no_change"):
            manager.preview(SITE, {"mode": 0}, disruption_confirmed=True)

    def test_unsafe_or_incomplete_read_state_blocks_preview(self):
        invalid_states = [
            {**BASE, "timeRangeEnable": True},
            {**BASE, "timeRangeId": "private-id"},
            {key: value for key, value in BASE.items() if key != "timeRangeId"},
            {**BASE, "extra": 1},
            {**BASE, "mode": True},
            {**BASE, "resource": True},
            {**BASE, "timeRangeAction": 2},
            {**BASE, "timeRangeEnable": 0},
        ]
        for state in invalid_states:
            with self.subTest(state=state):
                manager = rrm.RrmModePlans(lambda _site, s=state: s, self.write)
                with self.assertRaisesRegex(rrm.RrmModeChangeError, "rrm_state_unsupported"):
                    manager.preview(SITE, {"mode": 1}, disruption_confirmed=True)

    def test_default_off_and_required_journal_fail_closed(self):
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "journal_required"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        readonly = self.manager()
        plan = self.preview(readonly)["plan_id"]
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "writes_disabled"):
            readonly.apply(plan)
        self.assertEqual(self.writes, [])

    def test_apply_passes_whole_target_once_and_verifies_readback(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        result = manager.apply(plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["after"], dict(BASE, mode=1))
        self.assertEqual(self.writes, [(SITE, dict(BASE, mode=1))])
        self.assertEqual(self.journal.events[0][0], "intent")
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "verified_readback"))
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_stale_and_journal_failure_do_not_dispatch(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state["resource"] = 1
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "state_changed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        self.state = dict(BASE)
        self.journal.fail_intent = True
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "journal_unavailable"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_ttl_checked_before_write_and_after_intent_fsync(self):
        now = [0.0]
        manager = rrm.RrmModePlans(self.read, self.write, writes_enabled=True,
                                   clock=lambda: now[0], journal=self.journal,
                                   require_journal=True)
        plan = self.preview(manager)["plan_id"]
        now[0] = 300
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        now[0] = 400
        plan = self.preview(manager)["plan_id"]
        self.journal.after_intent = lambda: now.__setitem__(0, 700)
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_timeout_recovery_inspection_and_close_never_replay(self):
        def timeout(site_ref, value):
            self.writes.append((site_ref, dict(value)))
            raise TimeoutError("sensitive diagnostic")

        manager = rrm.RrmModePlans(self.read, timeout, writes_enabled=True,
                                   journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "change_in_doubt"):
            manager.apply(plan)
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

        with patch.object(rrm, "ALLOWED_JOURNAL_OPERATIONS",
                          rrm.ALLOWED_JOURNAL_OPERATIONS | {"rrm-mode"}):
            recovered = rrm.RrmModePlans(self.read, self.write, writes_enabled=True,
                                         journal=self.journal)
        inspected = recovered.inspect_in_doubt(plan)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertIn("does_not_prove", inspected["observation_note"])
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "operator_confirmation_required"):
            recovered.close_in_doubt(plan, "retry")
        self.assertEqual(recovered.close_in_doubt(plan, "outcome_unknown_no_retry")["state"],
                         "closed_outcome_unknown")
        self.assertEqual(self.journal.events[-1], ("close", plan, "outcome_unknown_no_retry"))
        self.assertEqual(recovered.list_in_doubt(), [])
        with self.assertRaisesRegex(rrm.RrmModeChangeError, "plan_unknown"):
            recovered.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_recovery_requires_allowlisted_operation_and_valid_full_state(self):
        plan = "f" * 48
        row = {"operation": "rrm-mode", "plan_id": plan, "state": "in_doubt",
               "target_refs": {"site_ref": SITE}, "before": BASE,
               "target": dict(BASE, mode=1)}
        self.journal.rows = [row]
        with patch.object(rrm, "ALLOWED_JOURNAL_OPERATIONS",
                          rrm.ALLOWED_JOURNAL_OPERATIONS | {"rrm-mode"}):
            recovered = self.manager(journal=self.journal)
            self.assertEqual(recovered.list_in_doubt()[0]["plan_id"], plan)

        self.journal.rows = [{**row, "target": dict(BASE, mode=1, timeRangeId="leak")}]
        with patch.object(rrm, "ALLOWED_JOURNAL_OPERATIONS",
                          rrm.ALLOWED_JOURNAL_OPERATIONS | {"rrm-mode"}):
            with self.assertRaisesRegex(rrm.RrmModeChangeError, "journal_unavailable"):
                self.manager(journal=self.journal)


if __name__ == "__main__":
    unittest.main()
