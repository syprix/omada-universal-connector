from __future__ import annotations

import copy
import unittest

from app.gateway_tag_qos_changes import (
    OPERATION, GatewayTagQosChangeError, GatewayTagQosPlans,
)


SITE_REF = "a" * 24
PLAN_ID = "f" * 48
INITIAL = {"tagConfigList": [
    {"classType": 0, "enable": False, "dscp": "8"},
    {"classType": 1, "enable": True, "dscp": "10"},
    {"classType": 2, "enable": False, "dscp": "20"},
    {"classType": 3, "enable": True, "dscp": "46"},
]}


class FakeClock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


class FakeJournal:
    def __init__(self, recovered=None) -> None:
        self.recovered = recovered or []
        self.events = []
        self.outcomes = []
        self.closed = []
        self.fail_intent = False

    def in_doubt_plans(self):
        return copy.deepcopy(self.recovered)

    def record_dispatch_intent(self, **event):
        if self.fail_intent:
            raise OSError("private journal detail")
        self.events.append(copy.deepcopy(event))

    def record_outcome(self, plan_id, outcome):
        self.outcomes.append((plan_id, outcome))

    def close_unknown(self, plan_id, confirmation):
        self.closed.append((plan_id, confirmation))


class GatewayTagQosPlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = copy.deepcopy(INITIAL)
        self.calls = []
        self.events = []
        self.read_error = False
        self.write_error = False
        self.mismatch = False

    def read(self, site_ref):
        self.events.append("read")
        if self.read_error:
            raise OSError("private controller detail")
        if self.mismatch and self.calls:
            current = copy.deepcopy(self.state)
            current["tagConfigList"][0]["dscp"] = "16"
            return current
        return copy.deepcopy(self.state)

    def write(self, site_ref, body):
        self.events.append("write")
        self.calls.append((site_ref, copy.deepcopy(body)))
        if self.write_error:
            raise TimeoutError("private controller detail")
        self.state = copy.deepcopy(body)

    def manager(self, **kwargs):
        return GatewayTagQosPlans(self.read, self.write, **kwargs)

    def preview(self, manager, *, class_type=2, enable=True, confirmed=True):
        return manager.preview(SITE_REF, {"classType": class_type, "enable": enable},
                               disruption_confirmed=confirmed)

    def test_preview_changes_only_one_enable_preserves_order_and_dscp(self):
        manager = self.manager()
        preview = self.preview(manager)
        expected = copy.deepcopy(INITIAL)
        expected["tagConfigList"][2]["enable"] = True
        self.assertEqual(preview["before"], INITIAL)
        self.assertEqual(preview["target"], expected)
        self.assertEqual(preview["rollback"], INITIAL)
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertIn("site-wide QoS", preview["warning"])
        self.assertEqual(preview["scope"], "gateway_tag_outbound_traffic")
        with self.assertRaisesRegex(GatewayTagQosChangeError, "no_change"):
            self.preview(manager, class_type=0, enable=False)

    def test_confirmation_change_and_canonical_dscp_are_strict(self):
        manager = self.manager()
        for confirmed in (False, 1, None):
            with self.subTest(confirmed=confirmed), self.assertRaisesRegex(
                    GatewayTagQosChangeError, "disruption_confirmation_required"):
                self.preview(manager, confirmed=confirmed)
        for change in ({}, {"classType": 0}, {"classType": True, "enable": True},
                       {"classType": 4, "enable": True},
                       {"classType": 1, "enable": 1},
                       {"classType": 1, "enable": True, "dscp": "8"}):
            with self.subTest(change=change), self.assertRaisesRegex(
                    GatewayTagQosChangeError, "change_invalid"):
                manager.preview(SITE_REF, change, disruption_confirmed=True)

        for dscp in ("08", "008", "", " 8", "8 ", "07"):
            self.state["tagConfigList"][0]["dscp"] = dscp
            with self.subTest(dscp=dscp), self.assertRaisesRegex(
                    GatewayTagQosChangeError, "readback_unavailable"):
                self.preview(manager)

    def test_incomplete_duplicate_unknown_and_invalid_full_states_fail_closed(self):
        manager = self.manager()
        malformed = [
            {"tagConfigList": INITIAL["tagConfigList"][:3]},
            {"tagConfigList": [*INITIAL["tagConfigList"], INITIAL["tagConfigList"][0]]},
            {"tagConfigList": [{**row, "extra": 1} for row in INITIAL["tagConfigList"]]},
            {"tagConfigList": [{**row, "classType": True} if i == 0 else row
                               for i, row in enumerate(INITIAL["tagConfigList"])]},
            {"tagConfigList": [{**row, "enable": 1} if i == 0 else row
                               for i, row in enumerate(INITIAL["tagConfigList"])]},
            {"tagConfigList": [{**row, "dscp": "999"} if i == 0 else row
                               for i, row in enumerate(INITIAL["tagConfigList"])]},
            {"tagConfigList": INITIAL["tagConfigList"], "extra": True},
        ]
        for state in malformed:
            self.state = copy.deepcopy(state)
            with self.subTest(state=state), self.assertRaisesRegex(
                    GatewayTagQosChangeError, "readback_unavailable"):
                self.preview(manager)

    def test_default_off_required_journal_stale_and_expiration_block_write(self):
        manager = self.manager()
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayTagQosChangeError, "writes_disabled"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.calls, [])

        manager = self.manager(writes_enabled=True, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayTagQosChangeError, "journal_required"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.calls, [])

        manager = self.manager(writes_enabled=True)
        preview = self.preview(manager)
        self.state["tagConfigList"][1]["dscp"] = "12"
        with self.assertRaisesRegex(GatewayTagQosChangeError, "state_changed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.calls, [])

        clock = FakeClock()
        manager = self.manager(writes_enabled=True, clock=clock)
        preview = self.preview(manager)
        clock.now += 300
        with self.assertRaisesRegex(GatewayTagQosChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.calls, [])

    def test_durable_intent_post_intent_recheck_one_full_put_and_readback(self):
        journal = FakeJournal()
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        preview = self.preview(manager)
        expected = copy.deepcopy(preview["target"])
        self.events.clear()
        result = manager.apply(preview["plan_id"])
        self.assertEqual(self.calls, [(SITE_REF, expected)])
        self.assertEqual(self.events, ["read", "read", "write", "read"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["before"], INITIAL)
        self.assertEqual(result["after"], expected)
        self.assertEqual(journal.events, [{
            "operation": OPERATION, "plan_id": preview["plan_id"],
            "target_refs": {"site_ref": SITE_REF}, "before": INITIAL, "target": expected,
        }])
        self.assertEqual(journal.outcomes, [(preview["plan_id"], "verified_readback")])
        with self.assertRaisesRegex(GatewayTagQosChangeError, "plan_already_consumed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(len(self.calls), 1)

    def test_change_during_fsync_read_error_and_expiry_never_put(self):
        for mode in ("foreign_change", "read_error", "expiry"):
            with self.subTest(mode=mode):
                self.setUp()
                clock = FakeClock()

                class Journal(FakeJournal):
                    def record_dispatch_intent(inner, **event):
                        super(Journal, inner).record_dispatch_intent(**event)
                        if mode == "foreign_change":
                            self.state["tagConfigList"][0]["dscp"] = "16"
                        elif mode == "read_error":
                            self.read_error = True
                        else:
                            clock.now += 300

                journal = Journal()
                manager = self.manager(writes_enabled=True, journal=journal,
                                       require_journal=True, clock=clock)
                preview = self.preview(manager)
                with self.assertRaises(GatewayTagQosChangeError):
                    manager.apply(preview["plan_id"])
                self.assertEqual(self.calls, [])
                self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")
                self.assertEqual(journal.outcomes, [(preview["plan_id"], "unknown")])
                with self.assertRaisesRegex(GatewayTagQosChangeError, "plan_already_consumed"):
                    manager.apply(preview["plan_id"])

    def test_timeout_or_full_readback_mismatch_is_in_doubt_without_replay(self):
        for mode in ("timeout", "mismatch"):
            with self.subTest(mode=mode):
                self.setUp()
                journal = FakeJournal()
                manager = self.manager(writes_enabled=True, journal=journal,
                                       require_journal=True)
                preview = self.preview(manager)
                if mode == "timeout":
                    self.write_error = True
                else:
                    self.mismatch = True
                with self.assertRaisesRegex(GatewayTagQosChangeError, "change_in_doubt"):
                    manager.apply(preview["plan_id"])
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(journal.outcomes, [(preview["plan_id"], "unknown")])
                with self.assertRaisesRegex(GatewayTagQosChangeError, "plan_already_consumed"):
                    manager.apply(preview["plan_id"])

    def test_intent_failure_does_not_write_and_in_doubt_plan_can_be_inspected_closed(self):
        journal = FakeJournal()
        journal.fail_intent = True
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayTagQosChangeError, "journal_unavailable"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.calls, [])
        self.assertEqual(manager.list_in_doubt()[0]["plan_id"], preview["plan_id"])
        with self.assertRaisesRegex(GatewayTagQosChangeError, "operator_confirmation_required"):
            manager.close_in_doubt(preview["plan_id"], "wrong")
        inspection = manager.inspect_in_doubt(preview["plan_id"])
        self.assertEqual(inspection["outcome"], "unknown")
        self.assertIn("does_not_prove", inspection["observation_note"])
        closed = manager.close_in_doubt(preview["plan_id"], "outcome_unknown_no_retry")
        self.assertEqual(closed["state"], "closed_outcome_unknown")
        self.assertEqual(manager.list_in_doubt(), [])

    def test_recovered_intent_is_in_doubt_and_never_replayed(self):
        target = copy.deepcopy(INITIAL)
        target["tagConfigList"][2]["enable"] = True
        journal = FakeJournal([{
            "operation": OPERATION, "plan_id": PLAN_ID,
            "target_refs": {"site_ref": SITE_REF}, "before": INITIAL,
            "target": target, "state": "in_doubt",
        }])
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        self.assertEqual(manager.list_in_doubt(), [{
            "plan_id": PLAN_ID, "state": "in_doubt", "scope": "gateway_tag_outbound_traffic",
            "target_refs": {"site_ref": SITE_REF},
        }])
        with self.assertRaisesRegex(GatewayTagQosChangeError, "plan_already_consumed"):
            manager.apply(PLAN_ID)
        self.assertEqual(self.calls, [])
        self.assertEqual(journal.events, [])


if __name__ == "__main__":
    unittest.main()
