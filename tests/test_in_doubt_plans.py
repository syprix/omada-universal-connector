from __future__ import annotations

import copy
import unittest

from app.changes import ChangeError, RadioChangePlans
from app.dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans
from app.gateway_ipv6_changes import GatewayIpv6ChangeError, GatewayIpv6IpPassthroughPlans
from app.ssid_changes import SsidChangeError, SsidChangePlans


SITE = "a" * 24
DEVICE = "b" * 24
PLAN_CONFIRMATION = "outcome_unknown_no_retry"
CURRENT_OUTCOME_NOTE = "current_state_does_not_prove_original_write_outcome"


def make_cases():
    cases = []

    for name, manager_type, error_type, initial, preview in (
        ("radio", RadioChangePlans, ChangeError,
         {"radioSetting2g": {"txPowerLevel": 1}},
         lambda manager: manager.preview(SITE, DEVICE, {"radioSetting2g": {"txPowerLevel": 2}})),
        ("dns", DnsCacheChangePlans, DnsCacheChangeError,
         {"enable": False, "ttl": 600},
         lambda manager: manager.preview(SITE, {"ttl": 900})),
        ("ssid", SsidChangePlans, SsidChangeError,
         {"ssidEnable": False},
         lambda manager: manager.preview(SITE, DEVICE, {"ssidEnable": True})),
        ("gateway_ipv6", GatewayIpv6IpPassthroughPlans, GatewayIpv6ChangeError,
         {"enable": False},
         lambda manager: manager.preview(SITE, DEVICE, {"enable": True})),
    ):
        state = {"value": copy.deepcopy(initial), "read_calls": 0,
                 "write_calls": 0, "read_fails": False}

        def read(*_args, _state=state):
            _state["read_calls"] += 1
            if _state["read_fails"]:
                raise OSError("fixture read failure")
            return copy.deepcopy(_state["value"])

        def write(*_args, _state=state):
            _state["write_calls"] += 1
            raise OSError("fixture uncertain write")

        manager = manager_type(read, write, writes_enabled=True)
        cases.append((name, manager, error_type, state, preview))
    return cases


def create_in_doubt(manager, error_type, preview):
    result = preview(manager)
    plan_id = result["plan_id"]
    with unittest.TestCase().assertRaisesRegex(error_type, "change_in_doubt"):
        manager.apply(plan_id)
    return plan_id


class InDoubtPlanTests(unittest.TestCase):
    def test_list_and_inspect_are_targeted_redacted_and_keep_outcome_unknown(self) -> None:
        for name, manager, error_type, counters, preview in make_cases():
            with self.subTest(manager=name):
                plan_id = create_in_doubt(manager, error_type, preview)
                read_before = counters["read_calls"]
                listed = manager.list_in_doubt()
                self.assertEqual(len(listed), 1)
                self.assertEqual(listed[0]["plan_id"], plan_id)
                self.assertEqual(listed[0]["state"], "in_doubt")
                self.assertEqual(counters["read_calls"], read_before)

                inspected = manager.inspect_in_doubt(plan_id)
                self.assertEqual(counters["read_calls"], read_before + 1)
                self.assertEqual(inspected["state"], "in_doubt")
                self.assertEqual(inspected["outcome"], "unknown")
                self.assertEqual(inspected["observation_note"], CURRENT_OUTCOME_NOTE)
                self.assertEqual(inspected["current_observation"]["status"], "observed")
                self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")
                self.assertEqual(counters["write_calls"], 1)
                self.assertTrue(set(inspected["target_refs"].values()).issubset({SITE, DEVICE}))
                self.assertNotIn("before_hash", inspected)
                self.assertNotIn("expires", inspected)

    def test_read_failure_does_not_change_in_doubt_plan(self) -> None:
        for name, manager, error_type, counters, preview in make_cases():
            with self.subTest(manager=name):
                plan_id = create_in_doubt(manager, error_type, preview)
                saved = copy.deepcopy(manager.plans[plan_id])
                counters["read_fails"] = True
                before_reads, before_writes = counters["read_calls"], counters["write_calls"]

                result = manager.inspect_in_doubt(plan_id)

                self.assertEqual(counters["read_calls"], before_reads + 1)
                self.assertEqual(counters["write_calls"], before_writes)
                self.assertEqual(result["current_observation"], {"status": "unavailable"})
                self.assertEqual(result["outcome"], "unknown")
                self.assertEqual(manager.plans[plan_id], saved)

    def test_wrong_state_confirmation_and_unknown_target_are_rejected(self) -> None:
        for name, manager, error_type, _counters, preview in make_cases():
            with self.subTest(manager=name):
                pending_id = preview(manager)["plan_id"]
                with self.assertRaisesRegex(error_type, "plan_not_in_doubt"):
                    manager.inspect_in_doubt(pending_id)
                with self.assertRaisesRegex(error_type, "plan_not_in_doubt"):
                    manager.close_in_doubt(pending_id, PLAN_CONFIRMATION)
                with self.assertRaisesRegex(error_type, "operator_confirmation_required"):
                    manager.close_in_doubt(pending_id, "yes")
                with self.assertRaisesRegex(error_type, "plan_unknown"):
                    manager.inspect_in_doubt("f" * 48)
                with self.assertRaisesRegex(error_type, "plan_unknown"):
                    manager.close_in_doubt("f" * 48, PLAN_CONFIRMATION)

    def test_close_requires_confirmation_releases_capacity_and_blocks_replay_without_write(self) -> None:
        for name, manager, error_type, counters, preview in make_cases():
            with self.subTest(manager=name):
                plan_id = create_in_doubt(manager, error_type, preview)
                before_writes = counters["write_calls"]
                before_reads = counters["read_calls"]
                with self.assertRaisesRegex(error_type, "operator_confirmation_required"):
                    manager.close_in_doubt(plan_id, "")
                self.assertIn(plan_id, manager.plans)

                closed = manager.close_in_doubt(plan_id, PLAN_CONFIRMATION)
                self.assertEqual(closed["plan_id"], plan_id)
                self.assertEqual(closed["state"], "closed_outcome_unknown")
                self.assertEqual(closed["target_refs"]["site_ref"], SITE)
                self.assertNotIn(plan_id, manager.plans)
                self.assertEqual(counters["read_calls"], before_reads)
                self.assertEqual(counters["write_calls"], before_writes)
                with self.assertRaisesRegex(error_type, "plan_unknown"):
                    manager.apply(plan_id)
                self.assertEqual(counters["write_calls"], before_writes)
                self.assertEqual(manager.list_in_doubt(), [])


if __name__ == "__main__":
    unittest.main()
