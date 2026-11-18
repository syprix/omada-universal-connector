from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app import gateway_voip_changes
from app.gateway_voip_changes import GatewayVoipChangeError, GatewayVoipPlans


SITE_REF = "a" * 24
PLAN_ID = "f" * 48
INITIAL = {"enable": False, "sipUdpPort": 5060}


class FakeClock:
    def __init__(self) -> None:
        self.now = 5.0

    def __call__(self) -> float:
        return self.now


class FakeJournal:
    def __init__(self, recovered: list[dict[str, object]] | None = None) -> None:
        self.recovered = recovered or []
        self.events: list[dict[str, object]] = []
        self.outcomes: list[tuple[str, str]] = []
        self.closed: list[tuple[str, str]] = []
        self.fail_intent = False

    def in_doubt_plans(self):
        return copy.deepcopy(self.recovered)

    def record_dispatch_intent(self, **event) -> None:
        if self.fail_intent:
            raise OSError("private journal detail")
        self.events.append(copy.deepcopy(event))

    def record_outcome(self, plan_id: str, outcome: str) -> None:
        self.outcomes.append((plan_id, outcome))

    def close_unknown(self, plan_id: str, confirmation: str) -> None:
        self.closed.append((plan_id, confirmation))


class GatewayVoipPlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = dict(INITIAL)
        self.write_calls: list[tuple[str, dict[str, object]]] = []
        self.events: list[str] = []
        self.read_error = False
        self.write_error = False
        self.mismatch = False

    def read(self, site_ref: str):
        self.events.append("read")
        if self.read_error:
            raise OSError("private controller detail")
        if self.mismatch and self.write_calls:
            return {"enable": True, "sipUdpPort": 5061}
        return dict(self.state)

    def write(self, site_ref: str, body: dict[str, object]):
        self.events.append("write")
        self.write_calls.append((site_ref, dict(body)))
        if self.write_error:
            raise TimeoutError("private controller detail")
        self.state = dict(body)

    def manager(self, **kwargs):
        return GatewayVoipPlans(self.read, self.write, **kwargs)

    def preview(self, manager, change=None, *, confirmed=True):
        return manager.preview(SITE_REF, {"enable": True} if change is None else change,
                               disruption_confirmed=confirmed)

    def test_preview_preserves_port_and_warns_without_success_claim(self) -> None:
        manager = self.manager()
        preview = self.preview(manager)
        self.assertEqual(preview["scope"], "gateway_voip_prioritization")
        self.assertEqual(preview["before"], INITIAL)
        self.assertEqual(preview["target"], {"enable": True, "sipUdpPort": 5060})
        self.assertEqual(preview["rollback"], INITIAL)
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(preview["warning"],
                         "VoIP prioritization settings may affect VoIP traffic; success is not guaranteed.")

    def test_confirmation_change_and_full_read_state_are_strict(self) -> None:
        manager = self.manager()
        for confirmed in (False, 1, None):
            with self.subTest(confirmed=confirmed), self.assertRaisesRegex(
                    GatewayVoipChangeError, "disruption_confirmation_required"):
                self.preview(manager, confirmed=confirmed)
        for change in ({}, {"enable": True, "sipUdpPort": 5061},
                       {"enable": 1}, {"unknown": True}):
            with self.subTest(change=change), self.assertRaisesRegex(
                    GatewayVoipChangeError, "change_invalid"):
                self.preview(manager, change)
        for state in (
                {"enable": False},
                {"enable": False, "sipUdpPort": 5060, "extra": False},
                {"enable": 0, "sipUdpPort": 5060},
                {"enable": False, "sipUdpPort": True},
                {"enable": False, "sipUdpPort": -1},
                {"enable": False, "sipUdpPort": 65536},
        ):
            self.state = state
            with self.subTest(state=state), self.assertRaisesRegex(
                    GatewayVoipChangeError, "readback_unavailable"):
                self.preview(manager)

        self.state = dict(INITIAL)
        with self.assertRaisesRegex(GatewayVoipChangeError, "no_change"):
            self.preview(manager, {"enable": False})

    def test_default_off_journal_required_stale_port_and_expiration_block_write(self) -> None:
        manager = self.manager()
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayVoipChangeError, "writes_disabled"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

        manager = self.manager(writes_enabled=True, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayVoipChangeError, "journal_required"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

        manager = self.manager(writes_enabled=True)
        preview = self.preview(manager)
        self.state["sipUdpPort"] = 5070
        with self.assertRaisesRegex(GatewayVoipChangeError, "state_changed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

        clock = FakeClock()
        manager = self.manager(writes_enabled=True, clock=clock)
        preview = self.preview(manager)
        clock.now += 300
        with self.assertRaisesRegex(GatewayVoipChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

    def test_full_state_intent_precedes_one_write_and_full_readback(self) -> None:
        journal = FakeJournal()
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        preview = self.preview(manager)
        self.events.clear()
        applied = manager.apply(preview["plan_id"])
        target = {"enable": True, "sipUdpPort": 5060}
        self.assertEqual(self.write_calls, [(SITE_REF, target)])
        self.assertEqual(self.events, ["read", "read", "write", "read"])
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["before"], INITIAL)
        self.assertEqual(applied["after"], target)
        self.assertEqual(journal.events[0], {
            "operation": "gateway-voip", "plan_id": preview["plan_id"],
            "target_refs": {"site_ref": SITE_REF}, "before": INITIAL,
            "target": target,
        })
        self.assertEqual(journal.outcomes, [(preview["plan_id"], "verified_readback")])
        with self.assertRaisesRegex(GatewayVoipChangeError, "plan_already_consumed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(len(self.write_calls), 1)

    def test_intent_failure_or_post_fsync_expiry_never_writes(self) -> None:
        journal = FakeJournal()
        journal.fail_intent = True
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayVoipChangeError, "journal_unavailable"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])
        self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")

        clock = FakeClock()

        class AdvancingJournal(FakeJournal):
            def record_dispatch_intent(inner, **event):
                super(AdvancingJournal, inner).record_dispatch_intent(**event)
                clock.now += 300

        journal = AdvancingJournal()
        manager = self.manager(writes_enabled=True, journal=journal,
                               require_journal=True, clock=clock)
        preview = self.preview(manager)
        with self.assertRaisesRegex(GatewayVoipChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])
        self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")
        self.assertEqual(journal.outcomes, [(preview["plan_id"], "unknown")])

    def test_change_during_fsync_or_dispatch_read_failure_blocks_put(self) -> None:
        for mode in ("foreign_change", "read_failure"):
            with self.subTest(mode=mode):
                self.setUp()

                class DuringIntentJournal(FakeJournal):
                    def record_dispatch_intent(inner, **event):
                        super(DuringIntentJournal, inner).record_dispatch_intent(**event)
                        if mode == "foreign_change":
                            self.state["sipUdpPort"] = 5099
                        else:
                            self.read_error = True

                journal = DuringIntentJournal()
                manager = self.manager(writes_enabled=True, journal=journal,
                                       require_journal=True)
                preview = self.preview(manager)
                with self.assertRaisesRegex(GatewayVoipChangeError, "change_in_doubt"):
                    manager.apply(preview["plan_id"])
                self.assertEqual(self.write_calls, [])
                self.assertEqual(journal.outcomes, [(preview["plan_id"], "unknown")])
                self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")
                with self.assertRaisesRegex(GatewayVoipChangeError, "plan_already_consumed"):
                    manager.apply(preview["plan_id"])

    def test_timeout_and_port_readback_mismatch_are_in_doubt_without_replay(self) -> None:
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
                with self.assertRaisesRegex(GatewayVoipChangeError, "change_in_doubt"):
                    manager.apply(preview["plan_id"])
                self.assertEqual(len(self.write_calls), 1)
                self.assertEqual(journal.outcomes, [(preview["plan_id"], "unknown")])
                with self.assertRaisesRegex(GatewayVoipChangeError, "plan_already_consumed"):
                    manager.apply(preview["plan_id"])
                inspection = manager.inspect_in_doubt(preview["plan_id"])
                self.assertEqual(inspection["outcome"], "unknown")
                self.assertEqual(inspection["observation_note"],
                                 "current_state_does_not_prove_original_write_outcome")
                self.assertEqual(len(self.write_calls), 1)

    def test_recovery_requires_full_state_and_close_never_dispatches(self) -> None:
        before = {"enable": False, "sipUdpPort": 5060}
        target = {"enable": True, "sipUdpPort": 5060}
        recovered = [{"operation": "gateway-voip", "plan_id": PLAN_ID,
                      "target_refs": {"site_ref": SITE_REF}, "before": before,
                      "target": target, "state": "in_doubt"}]
        with patch.object(gateway_voip_changes, "ALLOWED_JOURNAL_OPERATIONS",
                          set(gateway_voip_changes.ALLOWED_JOURNAL_OPERATIONS) | {"gateway-voip"}):
            manager = self.manager(journal=FakeJournal(recovered))
        self.assertEqual(manager.list_in_doubt()[0]["plan_id"], PLAN_ID)
        self.assertEqual(manager.inspect_in_doubt(PLAN_ID)["before"], before)
        self.assertEqual(self.write_calls, [])
        with self.assertRaisesRegex(GatewayVoipChangeError, "operator_confirmation_required"):
            manager.close_in_doubt(PLAN_ID, "outcome_unknown")
        manager.close_in_doubt(PLAN_ID, "outcome_unknown_no_retry")
        self.assertEqual(self.write_calls, [])

        bad = [{"operation": "gateway-voip", "plan_id": PLAN_ID,
                "target_refs": {"site_ref": SITE_REF}, "before": before,
                "target": {"enable": True, "sipUdpPort": 5061}, "state": "in_doubt"}]
        with patch.object(gateway_voip_changes, "ALLOWED_JOURNAL_OPERATIONS",
                          set(gateway_voip_changes.ALLOWED_JOURNAL_OPERATIONS) | {"gateway-voip"}):
            with self.assertRaisesRegex(GatewayVoipChangeError, "journal_unavailable"):
                self.manager(journal=FakeJournal(bad))


if __name__ == "__main__":
    unittest.main()
