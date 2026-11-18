import unittest
from unittest.mock import patch

from app import ap_channel_limit_changes as channel_limit


SITE = "a" * 24
DEVICE = "b" * 24
BASE = {"supportChannelLimit": True, "channelLimitType": 0,
        "defaultInstType5g": True, "defaultInstType6g": False}


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


class ApChannelLimitPlanTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(BASE)
        self.writes = []
        self.journal = FakeJournal()

    def read(self, site_ref, device_ref):
        self.assertEqual((site_ref, device_ref), (SITE, DEVICE))
        return dict(self.state)

    def write(self, site_ref, device_ref, change):
        self.writes.append((site_ref, device_ref, dict(change)))
        self.state["channelLimitType"] = change["channelLimitType"]

    def manager(self, **kwargs):
        return channel_limit.ApChannelLimitPlans(self.read, self.write, **kwargs)

    def preview(self, manager, value=1):
        return manager.preview(SITE, DEVICE, {"channelLimitType": value},
                               disruption_confirmed=True)

    def test_preview_requires_confirmation_and_binds_full_before_state(self):
        manager = self.manager()
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError,
                                    "disruption_confirmation_required"):
            manager.preview(SITE, DEVICE, {"channelLimitType": 1})
        preview = self.preview(manager)
        self.assertEqual(preview["before"], BASE)
        self.assertEqual(preview["target"], {"channelLimitType": 1})
        self.assertEqual(preview["rollback"], {"channelLimitType": 0})
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(preview["effect_note"], "ap_channel_limit_effect_depends_on_controller")
        plan = manager.plans[preview["plan_id"]]
        self.assertEqual(plan["before_hash"], channel_limit._digest(BASE))
        self.assertEqual(self.writes, [])

    def test_invalid_support_full_read_schema_and_change_are_rejected(self):
        invalid_states = [
            {**BASE, "supportChannelLimit": False},
            {key: value for key, value in BASE.items() if key != "supportChannelLimit"},
            {**BASE, "supportChannelLimit": 1},
            {**BASE, "channelLimitType": True},
            {**BASE, "defaultInstType5g": 1},
            {**BASE, "extra": False},
        ]
        for state in invalid_states:
            with self.subTest(state=state):
                bad = channel_limit.ApChannelLimitPlans(
                    lambda _site, _device, value=state: value, self.write)
                with self.assertRaises(channel_limit.ApChannelLimitChangeError):
                    bad.preview(SITE, DEVICE, {"channelLimitType": 1},
                                disruption_confirmed=True)
        manager = self.manager()
        for change in ({"channelLimitType": True}, {"channelLimitType": 3},
                       {"channelLimitType": -1}, {"channelLimitType": 1, "extra": 2}, {}):
            with self.subTest(change=change), self.assertRaises(channel_limit.ApChannelLimitChangeError):
                manager.preview(SITE, DEVICE, change, disruption_confirmed=True)
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "no_change"):
            manager.preview(SITE, DEVICE, {"channelLimitType": 0}, disruption_confirmed=True)

    def test_default_off_and_journal_required_fail_closed(self):
        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "journal_required"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        readonly = self.manager()
        plan = self.preview(readonly)["plan_id"]
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "writes_disabled"):
            readonly.apply(plan)
        self.assertEqual(self.writes, [])

    def test_success_journals_and_writes_only_channel_type(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager, 2)["plan_id"]
        result = manager.apply(plan)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [(SITE, DEVICE, {"channelLimitType": 2})])
        intent = self.journal.events[0][1]
        self.assertEqual(intent["operation"], "ap-channel-limit")
        self.assertEqual(intent["target_refs"], {"site_ref": SITE, "device_ref": DEVICE})
        self.assertEqual(intent["before"], {"channelLimitType": 0})
        self.assertEqual(intent["target"], {"channelLimitType": 2})
        self.assertNotIn("supportChannelLimit", str(intent))
        self.assertNotIn("defaultInstType", str(intent))
        self.assertEqual(self.state, {**BASE, "channelLimitType": 2})
        self.assertEqual(result["rollback"], {"channelLimitType": 0})
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "verified_readback"))
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_stale_defaults_or_support_prevent_dispatch(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        self.state["defaultInstType5g"] = False
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "state_changed"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        self.state = dict(BASE)
        plan = self.preview(manager)["plan_id"]
        self.state["supportChannelLimit"] = False
        with self.assertRaises(channel_limit.ApChannelLimitChangeError):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

    def test_dispatch_recheck_requires_exact_support_defaults_and_target(self):
        manager = self.manager(writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        reads = [0]

        def altered_postread(_site, _device):
            reads[0] += 1
            if reads[0] == 1:
                return dict(BASE)
            return {**BASE, "channelLimitType": 1, "defaultInstType6g": True}

        manager.read = altered_postread
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "change_in_doubt"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")
        self.assertEqual(self.journal.events[-1], ("outcome", plan, "unknown"))

    def test_ttl_checked_before_write_and_after_intent_fsync(self):
        now = [0.0]
        manager = channel_limit.ApChannelLimitPlans(
            self.read, self.write, writes_enabled=True, clock=lambda: now[0],
            journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        now[0] = 300
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])

        now[0] = 400
        plan = self.preview(manager)["plan_id"]
        self.journal.after_intent = lambda: now.__setitem__(0, 700)
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "plan_expired"):
            manager.apply(plan)
        self.assertEqual(self.writes, [])
        self.assertEqual(manager.plans[plan]["state"], "in_doubt")

    def test_timeout_recovery_close_and_no_replay_or_invented_fields(self):
        def timeout(site_ref, device_ref, change):
            self.writes.append((site_ref, device_ref, dict(change)))
            raise TimeoutError("sensitive response text")

        manager = channel_limit.ApChannelLimitPlans(
            self.read, timeout, writes_enabled=True, journal=self.journal, require_journal=True)
        plan = self.preview(manager)["plan_id"]
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "change_in_doubt"):
            manager.apply(plan)
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "plan_already_consumed"):
            manager.apply(plan)
        self.assertEqual(len(self.writes), 1)

        with patch.object(channel_limit, "ALLOWED_JOURNAL_OPERATIONS",
                          channel_limit.ALLOWED_JOURNAL_OPERATIONS | {"ap-channel-limit"}):
            recovered = channel_limit.ApChannelLimitPlans(
                self.read, self.write, writes_enabled=True, journal=self.journal)
        recovered_plan = recovered.plans[plan]
        self.assertEqual(recovered_plan["before"], {"channelLimitType": 0})
        self.assertEqual(recovered_plan["target"], {"channelLimitType": 1})
        for field in ("supportChannelLimit", "defaultInstType5g", "defaultInstType6g"):
            self.assertNotIn(field, recovered_plan["before"])
            self.assertNotIn(field, recovered_plan["target"])
        inspected = recovered.inspect_in_doubt(plan)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertIn("does_not_prove", inspected["observation_note"])
        self.assertEqual(inspected["current_observation"]["data"], BASE)
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError,
                                    "operator_confirmation_required"):
            recovered.close_in_doubt(plan, "retry")
        self.assertEqual(recovered.close_in_doubt(plan, "outcome_unknown_no_retry")["state"],
                         "closed_outcome_unknown")
        with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError, "plan_unknown"):
            recovered.apply(plan)
        self.assertEqual(len(self.writes), 1)

    def test_recovery_rejects_invalid_journal_schema(self):
        row = {"operation": "ap-channel-limit", "plan_id": "f" * 48,
               "state": "in_doubt", "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
               "before": {"channelLimitType": 0}, "target": {"channelLimitType": 1}}
        self.journal.rows = [row]
        with patch.object(channel_limit, "ALLOWED_JOURNAL_OPERATIONS",
                          channel_limit.ALLOWED_JOURNAL_OPERATIONS | {"ap-channel-limit"}):
            recovered = self.manager(journal=self.journal)
            self.assertEqual(recovered.list_in_doubt()[0]["plan_id"], "f" * 48)
        self.journal.rows = [{**row, "target": {"channelLimitType": True}}]
        with patch.object(channel_limit, "ALLOWED_JOURNAL_OPERATIONS",
                          channel_limit.ALLOWED_JOURNAL_OPERATIONS | {"ap-channel-limit"}):
            with self.assertRaisesRegex(channel_limit.ApChannelLimitChangeError,
                                        "journal_unavailable"):
                self.manager(journal=self.journal)


if __name__ == "__main__":
    unittest.main()
