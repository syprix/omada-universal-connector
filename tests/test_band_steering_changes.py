import unittest
from unittest.mock import patch

from app.band_steering_changes import (
    BandSteeringChangeError,
    BandSteeringChangePlans,
    OPERATION,
)


SITE = "a" * 24


class FakeJournal:
    def __init__(self):
        self.rows = []
        self.events = []
        self.fail_intent = False
        self.on_intent = None

    def in_doubt_plans(self):
        return [dict(row) for row in self.rows if row["state"] == "in_doubt"]

    def record_dispatch_intent(self, **event):
        if self.fail_intent:
            raise OSError("private journal path")
        self.events.append(("intent", event.copy()))
        self.rows.append({**event, "state": "in_doubt"})
        if self.on_intent:
            self.on_intent()

    def record_outcome(self, plan_id, outcome):
        self.events.append(("outcome", plan_id, outcome))
        for row in self.rows:
            if row["plan_id"] == plan_id:
                row["state"] = "verified" if outcome == "verified_readback" else "in_doubt"

    def close_unknown(self, plan_id, confirmation):
        self.events.append(("close", plan_id, confirmation))
        for row in self.rows:
            if row["plan_id"] == plan_id:
                row["state"] = "closed"


class BandSteeringPlanTests(unittest.TestCase):
    def setUp(self):
        self.state = {"mode": 0}
        self.writes = []
        self.journal = FakeJournal()

    def read(self, site_ref):
        self.assertEqual(site_ref, SITE)
        return dict(self.state)

    def write(self, site_ref, change):
        self.writes.append((site_ref, dict(change)))
        self.state = dict(change)

    def manager(self, **kwargs):
        return BandSteeringChangePlans(self.read, self.write, **kwargs)

    def preview(self, manager, mode=1, **kwargs):
        return manager.preview(SITE, {"mode": mode}, disruption_confirmed=True, **kwargs)

    def test_preview_requires_acknowledgement_and_warns_about_disruption(self):
        manager = self.manager()
        with self.assertRaisesRegex(BandSteeringChangeError, "disruption_confirmation_required"):
            manager.preview(SITE, {"mode": 1})
        result = self.preview(manager, 2)
        self.assertEqual(result["before"], {"mode": 0})
        self.assertEqual(result["target"], {"mode": 2})
        self.assertEqual(result["warning"], "band_steering_may_interrupt_clients")
        self.assertEqual(result["expires_in_seconds"], 300)
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(self.writes, [])

    def test_only_modes_zero_one_two_and_exact_schema_are_accepted(self):
        manager = self.manager()
        for invalid in ({"mode": True}, {"mode": -1}, {"mode": 3},
                        {"mode": 1, "extra": 0}, {"mode": "1"}, {}):
            with self.subTest(invalid=invalid), self.assertRaises(BandSteeringChangeError):
                manager.preview(SITE, invalid, disruption_confirmed=True)
        for mode in (0, 1, 2):
            self.state = {"mode": (mode + 1) % 3}
            self.assertEqual(self.preview(manager, mode)["target"], {"mode": mode})

    def test_read_requires_exact_state_and_opaque_site_ref(self):
        bad = BandSteeringChangePlans(lambda _ref: {"mode": True}, self.write)
        with self.assertRaisesRegex(BandSteeringChangeError, "mode_invalid"):
            bad.preview(SITE, {"mode": 1}, disruption_confirmed=True)
        with self.assertRaisesRegex(BandSteeringChangeError, "site_ref_invalid"):
            self.manager().preview("site-name", {"mode": 1}, disruption_confirmed=True)

    def test_default_read_only_and_required_journal_fail_closed(self):
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(BandSteeringChangeError, "journal_required"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        readonly = self.manager()
        plan = self.preview(readonly)["plan_id"]
        with self.assertRaisesRegex(BandSteeringChangeError, "writes_disabled"):
            readonly.apply(plan)
        self.assertEqual(self.writes, [])

    def test_success_records_intent_before_single_write_and_readback(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager, 2)["plan_id"]
        result = manager.apply(plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [(SITE, {"mode": 2})])
        self.assertEqual(self.journal.events[0][0], "intent")
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "verified_readback"))
        with self.assertRaisesRegex(BandSteeringChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_stale_plan_and_failed_intent_never_write(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state = {"mode": 2}
        with self.assertRaisesRegex(BandSteeringChangeError, "state_changed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        self.state = {"mode": 0}
        self.journal.fail_intent = True
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(BandSteeringChangeError, "journal_unavailable"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_expiry_before_apply_and_during_durable_intent_do_not_write(self):
        now = [0.0]
        manager = BandSteeringChangePlans(self.read, self.write, writes_enabled=True,
                                            clock=lambda: now[0], journal=self.journal,
                                            require_journal=True)
        plan = self.preview(manager)["plan_id"]
        now[0] = 300.0
        with self.assertRaisesRegex(BandSteeringChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        now[0] = 400.0
        plan = self.preview(manager)["plan_id"]
        self.journal.on_intent = lambda: now.__setitem__(0, 700.0)
        with self.assertRaisesRegex(BandSteeringChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_timeout_becomes_in_doubt_never_replays_and_can_be_closed(self):
        def time_out(_site_ref, _change):
            self.writes.append((SITE, {"mode": 1}))
            raise TimeoutError("secret-ish detail")

        manager = BandSteeringChangePlans(self.read, time_out, writes_enabled=True,
                                            journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(BandSteeringChangeError, "change_in_doubt"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)
        with self.assertRaisesRegex(BandSteeringChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

        recovered = BandSteeringChangePlans(self.read, self.write, writes_enabled=True,
                                             journal=self.journal)
        listed = recovered.list_in_doubt()
        self.assertEqual(listed[0]["plan_id"], plan)
        inspected = recovered.inspect_in_doubt(plan)
        self.assertIn("does_not_prove", inspected["observation_note"])
        self.assertEqual(inspected["outcome"], "unknown")
        with self.assertRaisesRegex(BandSteeringChangeError, "operator_confirmation_required"):
            recovered.close_in_doubt(plan, "yes")
        closed = recovered.close_in_doubt(plan, "outcome_unknown_no_retry")
        self.assertEqual(closed["state"], "closed_outcome_unknown")
        self.assertEqual(self.journal.events[-1], ("close", plan, "outcome_unknown_no_retry"))
        self.assertEqual(recovered.list_in_doubt(), [])
        with self.assertRaisesRegex(BandSteeringChangeError, "plan_unknown"):
            recovered.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_recovery_rejects_malformed_or_unallowlisted_rows(self):
        malformed = FakeJournal()
        malformed.rows = [{"operation": "band-steering", "plan_id": "f" * 48,
                           "state": "in_doubt", "target_refs": {"site_ref": SITE},
                           "before": {"mode": True}, "target": {"mode": 1}}]
        with self.assertRaisesRegex(BandSteeringChangeError, "journal_unavailable"):
            self.manager(journal=malformed)
        unknown = FakeJournal()
        unknown.rows = [{"operation": "invented", "plan_id": "f" * 48,
                         "state": "in_doubt", "target_refs": {"site_ref": SITE},
                         "before": {"mode": 0}, "target": {"mode": 1}}]
        with self.assertRaisesRegex(BandSteeringChangeError, "journal_unavailable"):
            self.manager(journal=unknown)

    def test_recovery_reconstructs_only_in_doubt_and_never_write(self):
        plan = "f" * 48
        self.journal.rows = [{"operation": OPERATION, "plan_id": plan,
                              "state": "in_doubt", "target_refs": {"site_ref": SITE},
                              "before": {"mode": 0}, "target": {"mode": 1}}]
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        self.assertEqual(manager.list_in_doubt()[0]["plan_id"], plan)
        with self.assertRaisesRegex(BandSteeringChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
