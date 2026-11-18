from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app import dpi_changes
from app.dpi_changes import SiteDpiLoggingChangeError, SiteDpiLoggingPlans


SITE_REF = "a" * 24
PLAN_ID = "f" * 48
INITIAL = {"dpi": False, "loggingTraffic": False}


class FakeClock:
    def __init__(self) -> None:
        self.now = 10.0

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
            raise OSError("private path/controller details")
        self.events.append(copy.deepcopy(event))

    def record_outcome(self, plan_id: str, outcome: str) -> None:
        self.outcomes.append((plan_id, outcome))

    def close_unknown(self, plan_id: str, confirmation: str) -> None:
        self.closed.append((plan_id, confirmation))


class SiteDpiLoggingPlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = dict(INITIAL)
        self.write_calls: list[tuple[str, dict[str, bool]]] = []
        self.events: list[str] = []
        self.read_error = False
        self.write_error = False
        self.mismatch_readback = False

    def read(self, site_ref: str):
        self.events.append("read")
        if self.read_error:
            raise OSError("sensitive controller detail")
        if self.mismatch_readback and self.write_calls:
            return {"dpi": False, "loggingTraffic": True}
        return dict(self.state)

    def write(self, site_ref: str, body: dict[str, bool]):
        self.events.append("write")
        self.write_calls.append((site_ref, dict(body)))
        if self.write_error:
            raise TimeoutError("sensitive controller detail")
        self.state = dict(body)

    def manager(self, **kwargs):
        return SiteDpiLoggingPlans(self.read, self.write, **kwargs)

    def preview(self, manager, change=None, *, confirmed=True):
        return manager.preview(SITE_REF, {"dpi": True} if change is None else change,
                               disruption_confirmed=confirmed)

    def test_preview_binds_full_before_and_target_for_exactly_one_field(self) -> None:
        manager = self.manager()
        preview = self.preview(manager, {"loggingTraffic": True})
        self.assertEqual(preview["scope"], "site_dpi_logging")
        self.assertEqual(preview["before"], INITIAL)
        self.assertEqual(preview["target"], {"dpi": False, "loggingTraffic": True})
        self.assertEqual(preview["rollback"], INITIAL)
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertFalse(preview["writes_enabled"])
        self.assertIn("Traffic logging can record usage data.", preview["warnings"])
        self.assertTrue(any("DPI" in warning and "unknown" in warning
                            for warning in preview["warnings"]))

        self.state = {"dpi": True, "loggingTraffic": True}
        preview = self.preview(manager, {"loggingTraffic": False})
        self.assertEqual(preview["before"], {"dpi": True, "loggingTraffic": True})
        self.assertEqual(preview["target"], {"dpi": True, "loggingTraffic": False})
        self.assertFalse(any("Traffic logging" in warning for warning in preview["warnings"]))

    def test_preview_confirmation_body_and_state_are_strict(self) -> None:
        manager = self.manager()
        for confirmed in (False, 1, None):
            with self.subTest(confirmed=confirmed), self.assertRaisesRegex(
                    SiteDpiLoggingChangeError, "disruption_confirmation_required"):
                self.preview(manager, confirmed=confirmed)
        for change in ({}, {"dpi": True, "loggingTraffic": True},
                       {"dpi": 1}, {"loggingTraffic": "true"}, {"unknown": False}):
            with self.subTest(change=change), self.assertRaisesRegex(
                    SiteDpiLoggingChangeError, "change_invalid"):
                self.preview(manager, change)
        for state in (
                {"dpi": False},
                {"dpi": False, "loggingTraffic": False, "extra": True},
                {"dpi": 0, "loggingTraffic": False},
                {"dpi": False, "loggingTraffic": None},
        ):
            self.state = state
            with self.subTest(state=state), self.assertRaisesRegex(
                    SiteDpiLoggingChangeError, "readback_unavailable"):
                self.preview(manager)

    def test_default_off_journal_requirement_stale_and_expiration_block_write(self) -> None:
        manager = self.manager()
        preview = self.preview(manager)
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "writes_disabled"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

        manager = self.manager(writes_enabled=True, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "journal_required"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

        manager = self.manager(writes_enabled=True)
        preview = self.preview(manager)
        self.state["loggingTraffic"] = True
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "state_changed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

        clock = FakeClock()
        manager = self.manager(writes_enabled=True, clock=clock)
        preview = self.preview(manager)
        clock.now += 300
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])

    def test_successful_apply_writes_full_state_once_and_readbacks_both_values(self) -> None:
        journal = FakeJournal()
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        preview = self.preview(manager, {"loggingTraffic": True})
        self.events.clear()
        applied = manager.apply(preview["plan_id"])
        target = {"dpi": False, "loggingTraffic": True}
        self.assertEqual(self.write_calls, [(SITE_REF, target)])
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["before"], INITIAL)
        self.assertEqual(applied["after"], target)
        self.assertEqual(applied["rollback"], INITIAL)
        self.assertEqual(self.events, ["read", "read", "write", "read"])
        self.assertEqual(journal.events[0]["operation"], "site-dpi")
        self.assertEqual(journal.events[0]["before"], INITIAL)
        self.assertEqual(journal.events[0]["target"], target)
        self.assertEqual(journal.outcomes, [(preview["plan_id"], "verified_readback")])
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "plan_already_consumed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(len(self.write_calls), 1)

    def test_intent_failure_or_expiration_after_fsync_blocks_dispatch(self) -> None:
        journal = FakeJournal()
        journal.fail_intent = True
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "journal_unavailable"):
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
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual(self.write_calls, [])
        self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")

    def test_write_timeout_or_readback_mismatch_is_in_doubt_and_no_replay(self) -> None:
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
                    self.mismatch_readback = True
                with self.assertRaisesRegex(SiteDpiLoggingChangeError, "change_in_doubt"):
                    manager.apply(preview["plan_id"])
                self.assertEqual(len(self.write_calls), 1)
                self.assertEqual(journal.outcomes, [(preview["plan_id"], "unknown")])
                with self.assertRaisesRegex(SiteDpiLoggingChangeError, "plan_already_consumed"):
                    manager.apply(preview["plan_id"])
                inspected = manager.inspect_in_doubt(preview["plan_id"])
                self.assertEqual(inspected["outcome"], "unknown")
                self.assertEqual(inspected["observation_note"],
                                 "current_state_does_not_prove_original_write_outcome")
                self.assertEqual(len(self.write_calls), 1)

    def test_recovery_is_in_doubt_and_explicit_close_never_writes(self) -> None:
        before = {"dpi": False, "loggingTraffic": False}
        target = {"dpi": True, "loggingTraffic": False}
        journal = FakeJournal([{
            "operation": "site-dpi", "plan_id": PLAN_ID,
            "target_refs": {"site_ref": SITE_REF}, "before": before,
            "target": target, "state": "in_doubt",
        }])
        with patch.object(dpi_changes, "ALLOWED_JOURNAL_OPERATIONS",
                          set(dpi_changes.ALLOWED_JOURNAL_OPERATIONS) | {"site-dpi"}):
            manager = self.manager(journal=journal)
        self.assertEqual(manager.list_in_doubt(), [{
            "plan_id": PLAN_ID, "state": "in_doubt", "scope": "site_dpi_logging",
            "target_refs": {"site_ref": SITE_REF},
        }])
        self.assertEqual(manager.inspect_in_doubt(PLAN_ID)["before"], before)
        self.assertEqual(self.write_calls, [])
        with self.assertRaisesRegex(SiteDpiLoggingChangeError, "operator_confirmation_required"):
            manager.close_in_doubt(PLAN_ID, "outcome_unknown")
        manager.close_in_doubt(PLAN_ID, "outcome_unknown_no_retry")
        self.assertEqual(journal.closed, [(PLAN_ID, "outcome_unknown_no_retry")])
        self.assertEqual(self.write_calls, [])


if __name__ == "__main__":
    unittest.main()
