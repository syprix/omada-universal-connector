from __future__ import annotations

import unittest

from app.switch_cable_test_changes import SwitchCableTestError, SwitchCableTestPlans


SITE, SWITCH = "a" * 24, "b" * 24
PORT = 7


class Journal:
    def __init__(self):
        self.intents = []
        self.outcomes = []

    def record_dispatch_intent(self, **kwargs):
        self.intents.append(kwargs)

    def record_outcome(self, plan_id, outcome):
        self.outcomes.append((plan_id, outcome))

    def in_doubt_plans(self):
        return []


class SwitchCableTestPlansTests(unittest.TestCase):
    def setUp(self):
        self.now = [10.0]
        self.ports = [{"port": PORT, "editEnable": True, "copper": True,
                       "upper_port": False, "stack_port": False, "disabled": False}]
        self.logs = []
        self.results = {"status": "ok", "resource": "switch_cable_test_full_results",
                        "partial": False, "data": {"ports": []}}
        self.calls = []
        self.fail_start = False
        self.journal = Journal()

        def start(site, switch, ports):
            self.calls.append(("start", site, switch, ports))
            if self.fail_start:
                raise TimeoutError()

        def cancel(site, switch):
            self.calls.append(("cancel", site, switch))

        self.plans = SwitchCableTestPlans(
            read_ports=lambda *_: {"status": "ok", "resource": "switch_cable_test_ports",
                                   "partial": True, "data": {"ports": self.ports}},
            read_logs=lambda *_: {"status": "ok", "resource": "switch_cable_test_logs",
                                  "partial": False, "data": {"logs": self.logs}},
            read_results=lambda *_: self.results,
            start=start, cancel=cancel, writes_enabled=True,
            clock=lambda: self.now[0], journal=self.journal)

    def preview(self):
        return self.plans.preview(SITE, SWITCH, PORT, True)

    def test_preview_requires_confirmation_and_eligible_single_port(self):
        with self.assertRaisesRegex(SwitchCableTestError, "disruption_confirmation_required"):
            self.plans.preview(SITE, SWITCH, PORT, False)
        for invalid in (True, 0, 4097, "7"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    SwitchCableTestError, "cable_test_port_invalid"):
                self.plans.preview(SITE, SWITCH, invalid, True)
        self.ports[0]["copper"] = False
        with self.assertRaisesRegex(SwitchCableTestError, "cable_test_port_unsupported"):
            self.preview()

    def test_apply_is_one_shot_journaled_and_never_retries(self):
        plan = self.preview()
        result = self.plans.apply(plan["plan_id"])
        self.assertEqual(result["status"], "started")
        self.assertEqual(self.calls, [("start", SITE, SWITCH, [PORT])])
        self.assertEqual(len(self.journal.intents), 1)
        self.assertEqual(self.journal.intents[0]["operation"], "switch-cable-test")
        with self.assertRaisesRegex(SwitchCableTestError, "plan_already_consumed"):
            self.plans.apply(plan["plan_id"])
        self.assertEqual(len(self.calls), 1)

    def test_stale_state_and_expired_preview_do_not_dispatch(self):
        plan = self.preview()
        self.logs.append({"timestamp_value": 2, "test_ports": [], "complete_ports": [],
                          "cancelled_ports": [], "timed_out_ports": []})
        with self.assertRaisesRegex(SwitchCableTestError, "state_changed"):
            self.plans.apply(plan["plan_id"])
        self.assertEqual(self.calls, [])
        expired = self.preview()
        self.now[0] += 301
        with self.assertRaisesRegex(SwitchCableTestError, "plan_expired"):
            self.plans.apply(expired["plan_id"])
        self.assertEqual(self.calls, [])

    def test_correlated_completion_returns_only_redacted_port_result(self):
        plan = self.preview()
        self.plans.apply(plan["plan_id"])
        timestamp = 999
        self.logs.append({"timestamp_value": timestamp, "test_ports": [PORT],
                          "complete_ports": [PORT], "cancelled_ports": [],
                          "timed_out_ports": []})
        self.results = {"status": "ok", "resource": "switch_cable_test_full_results",
                        "partial": False, "data": {"ports": [
                            {"port": PORT, "timestamp_value": timestamp,
                             "state_codes": [1, 2], "length_values": [12, 13],
                             "privateMac": "AA-BB-CC-DD-EE-FF"}]}}
        result = self.plans.status(plan["plan_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"], {"state_codes": [1, 2], "length_values": [12, 13]})
        self.assertNotIn("timestamp", str(result))
        self.assertNotIn("privateMac", str(result))
        self.assertEqual(self.journal.outcomes, [(plan["plan_id"], "verified_readback")])

    def test_missing_result_or_runtime_timeout_stays_unknown_and_can_be_cancelled_once(self):
        plan = self.preview()
        self.plans.apply(plan["plan_id"])
        self.logs.append({"timestamp_value": 999, "test_ports": [PORT],
                          "complete_ports": [PORT], "cancelled_ports": [],
                          "timed_out_ports": []})
        result = self.plans.status(plan["plan_id"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "result_not_correlated")
        self.now[0] += 61
        result = self.plans.status(plan["plan_id"])
        self.assertEqual(result["status"], "unknown")
        cancel_plan = self.plans.preview_cancel(plan["plan_id"], True)
        self.plans.apply_cancel(cancel_plan["plan_id"])
        self.assertEqual(self.calls[-1], ("cancel", SITE, SWITCH))
        with self.assertRaisesRegex(SwitchCableTestError, "plan_already_consumed"):
            self.plans.apply_cancel(cancel_plan["plan_id"])

    def test_start_timeout_is_unknown_journaled_and_not_retried(self):
        self.fail_start = True
        plan = self.preview()
        with self.assertRaisesRegex(SwitchCableTestError, "cable_test_outcome_unknown"):
            self.plans.apply(plan["plan_id"])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaisesRegex(SwitchCableTestError, "plan_already_consumed"):
            self.plans.apply(plan["plan_id"])
        self.assertEqual(self.journal.outcomes, [(plan["plan_id"], "unknown")])


if __name__ == "__main__":
    unittest.main()
