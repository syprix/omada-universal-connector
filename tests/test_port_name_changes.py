from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

import app.port_name_changes as port_names
from app.port_name_changes import PortNameChangeError, SwitchPortNamePlans


SITE_REF = "a" * 24
SWITCH_REF = "b" * 24
PLAN_ID = "c" * 48
NAME = "private uplink Café"
TARGET = "Core uplink 2"
MARKER = {"name_redacted": True}


class FakeClock:
    def __init__(self, now: float = 10.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeJournal:
    def __init__(self, rows=None) -> None:
        self.rows = list(rows or [])
        self.events: list[dict[str, object]] = []
        self.closed: list[tuple[str, str]] = []
        self.intent_error = False
        self.outcome_error = False

    def in_doubt_plans(self):
        return self.rows

    def record_dispatch_intent(self, **event):
        if self.intent_error:
            raise OSError("private journal path")
        self.events.append(event)

    def record_outcome(self, plan_id, outcome):
        if self.outcome_error:
            raise OSError("private journal path")
        self.events.append({"plan_id": plan_id, "outcome": outcome})

    def close_unknown(self, plan_id, confirmation):
        self.closed.append((plan_id, confirmation))


class SwitchPortNamePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current = {"name": NAME}
        self.read_calls: list[tuple[str, str, int]] = []
        self.write_calls: list[tuple[str, str, int, dict[str, str]]] = []
        self.raise_write = False

    def read(self, site_ref, switch_ref, port):
        self.read_calls.append((site_ref, switch_ref, port))
        return dict(self.current)

    def write(self, site_ref, switch_ref, port, body):
        self.write_calls.append((site_ref, switch_ref, port, dict(body)))
        if self.raise_write:
            raise OSError("private controller detail")
        self.current = dict(body)

    def manager(self, **kwargs):
        return SwitchPortNamePlans(self.read, self.write, **kwargs)

    def preview(self, manager, name: str = TARGET):
        return manager.preview(SITE_REF, SWITCH_REF, 7, {"name": name})

    def test_preview_shows_exact_before_and_target_and_keeps_scope_bound(self) -> None:
        result = self.preview(self.manager())
        self.assertEqual(result["scope"], "switch_port_name")
        self.assertEqual(result["before"], {"name": NAME})
        self.assertEqual(result["target"], {"name": TARGET})
        self.assertEqual(result["rollback"], {"name": NAME})
        self.assertEqual(result["site_ref"], SITE_REF)
        self.assertEqual(result["switch_ref"], SWITCH_REF)
        self.assertEqual(result["port"], 7)
        self.assertEqual(result["expires_in_seconds"], 300)
        self.assertFalse(result["writes_enabled"])

    def test_strict_shared_name_rules_and_unicode_are_applied_without_normalizing(self) -> None:
        for name in ("A", "Café", "port Café", "管理-port", "🙂 port"):
            result = self.preview(self.manager(), name)
            self.assertEqual(result["target"], {"name": name})
        invalid = (
            "", "x" * 129, " leading", "trailing ", "\u00a0edge",
            "question?mark", 'double"quote', "line\nbreak", "tab\tchar",
            "e\u0301", "\u202eRTL", "\ue000private", "\ud800surrogate",
        )
        for name in invalid:
            with self.subTest(name=repr(name)):
                with self.assertRaises(PortNameChangeError) as raised:
                    self.preview(self.manager(), name)
                self.assertEqual(str(raised.exception), "name_invalid")
                if name:
                    self.assertNotIn(name, str(raised.exception))

    def test_name_body_is_exact_and_extra_fields_are_rejected(self) -> None:
        manager = self.manager()
        for body in ({"name": TARGET, "other": "secret"}, {"name": ""},
                     {"name": "x" * 129}, {"name": True}, None):
            with self.subTest(body=type(body).__name__), self.assertRaises(PortNameChangeError):
                manager.preview(SITE_REF, SWITCH_REF, 7, body)

    def test_old_empty_or_pattern_legacy_name_can_be_compared_but_never_rewritten_silently(self) -> None:
        self.current = {"name": ""}
        manager = self.manager()
        result = self.preview(manager, "new valid label")
        self.assertEqual(result["before"], {"name": ""})
        self.assertEqual(result["target"], {"name": "new valid label"})
        self.current = {"name": 'old?"label'}
        result = self.preview(manager, "new label")
        self.assertEqual(result["before"], {"name": 'old?"label'})

    def test_missing_unsafe_or_unbounded_old_state_fails_closed(self) -> None:
        for state in ({}, {"name": None}, {"name": "x" * 129},
                      {"name": "bad\nname"}, {"name": "e\u0301"},
                      {"name": "\ud800"}, {"name": " old"},
                      {"name": NAME, "extra": "private"}):
            with self.subTest(state=type(state).__name__):
                self.current = state
                with self.assertRaises(PortNameChangeError) as raised:
                    self.preview(self.manager())
                self.assertEqual(str(raised.exception), "read_state_unsupported")
                self.assertNotIn("private", str(raised.exception))

    def test_no_change_and_invalid_refs_or_port_fail(self) -> None:
        manager = self.manager()
        with self.assertRaisesRegex(PortNameChangeError, "no_change"):
            self.preview(manager, NAME)
        for args in (("A" * 24, SWITCH_REF, 7),
                     (SITE_REF, "not-a-ref", 7), (SITE_REF, SWITCH_REF, True),
                     (SITE_REF, SWITCH_REF, 4097)):
            with self.subTest(args=args), self.assertRaises(PortNameChangeError):
                manager.preview(*args, {"name": TARGET})

    def test_default_off_and_no_required_journal_never_reach_write(self) -> None:
        manager = self.manager()
        plan = self.preview(manager)
        with self.assertRaisesRegex(PortNameChangeError, "writes_disabled"):
            manager.apply(plan["plan_id"])
        self.assertEqual(self.write_calls, [])

        manager = self.manager(writes_enabled=True, require_journal=True)
        plan = self.preview(manager)
        with self.assertRaisesRegex(PortNameChangeError, "journal_required"):
            manager.apply(plan["plan_id"])
        self.assertEqual(self.write_calls, [])

    def test_stale_state_expires_before_dispatch_and_never_writes(self) -> None:
        clock = FakeClock()
        manager = self.manager(writes_enabled=True, clock=clock)
        plan = self.preview(manager)
        self.current = {"name": "changed by someone else"}
        with self.assertRaisesRegex(PortNameChangeError, "state_changed"):
            manager.apply(plan["plan_id"])
        self.assertEqual(self.write_calls, [])

        expired_manager = self.manager(writes_enabled=True, clock=clock)
        expired = self.preview(expired_manager)
        clock.now += 300
        with self.assertRaisesRegex(PortNameChangeError, "plan_expired"):
            expired_manager.apply(expired["plan_id"])
        self.assertEqual(self.write_calls, [])

    def test_successful_apply_writes_once_reads_back_and_hides_names_from_result(self) -> None:
        manager = self.manager(writes_enabled=True)
        plan = self.preview(manager)
        result = manager.apply(plan["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.write_calls, [(SITE_REF, SWITCH_REF, 7, {"name": TARGET})])
        self.assertNotIn(NAME, repr(result))
        self.assertNotIn(TARGET, repr(result))
        self.assertEqual(self.current, {"name": TARGET})
        with self.assertRaisesRegex(PortNameChangeError, "plan_already_consumed"):
            manager.apply(plan["plan_id"])
        self.assertEqual(len(self.write_calls), 1)

    def test_journal_intent_contains_only_fixed_redaction_markers_and_no_name_hashes(self) -> None:
        journal = FakeJournal()
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        plan = self.preview(manager)
        manager.apply(plan["plan_id"])
        rendered = repr(journal.events)
        self.assertIn("switch-port-name", rendered)
        self.assertIn(MARKER["name_redacted"].__str__(), rendered)
        self.assertNotIn(NAME, rendered)
        self.assertNotIn(TARGET, rendered)
        simple_hashes = (hashlib.sha256(NAME.encode("utf-8")).hexdigest(),
                         hashlib.sha256(TARGET.encode("utf-8")).hexdigest())
        for digest in simple_hashes:
            self.assertNotIn(digest, rendered)
        intent = journal.events[0]
        self.assertEqual(intent["before"], MARKER)
        self.assertEqual(intent["target"], MARKER)
        self.assertEqual(intent["target_refs"], {
            "site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": 7})

    def test_journal_failure_or_timeout_is_in_doubt_and_never_replayed(self) -> None:
        journal = FakeJournal()
        journal.intent_error = True
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        plan = self.preview(manager)
        with self.assertRaisesRegex(PortNameChangeError, "journal_unavailable"):
            manager.apply(plan["plan_id"])
        self.assertEqual(self.write_calls, [])
        self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")

        journal = FakeJournal()
        manager = self.manager(writes_enabled=True, journal=journal, require_journal=True)
        plan = self.preview(manager)
        self.raise_write = True
        with self.assertRaisesRegex(PortNameChangeError, "change_in_doubt"):
            manager.apply(plan["plan_id"])
        first_call_count = len(self.write_calls)
        with self.assertRaisesRegex(PortNameChangeError, "plan_already_consumed"):
            manager.apply(plan["plan_id"])
        self.assertEqual(len(self.write_calls), first_call_count)
        inspected = manager.inspect_in_doubt(plan["plan_id"])
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertEqual(inspected["current_observation"]["name_redacted"], True)
        self.assertNotIn(NAME, repr(inspected))
        self.assertNotIn(TARGET, repr(inspected))
        with self.assertRaisesRegex(PortNameChangeError, "operator_confirmation_required"):
            manager.close_in_doubt(plan["plan_id"], "outcome_unknown")
        manager.close_in_doubt(plan["plan_id"], "outcome_unknown_no_retry")
        self.assertEqual(journal.closed, [(plan["plan_id"], "outcome_unknown_no_retry")])

    def test_expiry_after_durable_intent_blocks_write(self) -> None:
        clock = FakeClock()

        class AdvancingJournal(FakeJournal):
            def record_dispatch_intent(inner_self, **event):
                super(AdvancingJournal, inner_self).record_dispatch_intent(**event)
                clock.now += 300

        journal = AdvancingJournal()
        manager = self.manager(writes_enabled=True, journal=journal,
                               require_journal=True, clock=clock)
        plan = self.preview(manager)
        with self.assertRaisesRegex(PortNameChangeError, "plan_expired"):
            manager.apply(plan["plan_id"])
        self.assertEqual(self.write_calls, [])
        self.assertEqual(manager.list_in_doubt()[0]["state"], "in_doubt")

    def test_restart_recovers_only_redacted_in_doubt_state_never_pending(self) -> None:
        row = {
            "operation": port_names.OPERATION,
            "plan_id": PLAN_ID,
            "target_refs": {"site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": 7},
            "before": MARKER,
            "target": MARKER,
            "state": "in_doubt",
        }
        journal = FakeJournal([row])
        allowed = set(port_names.ALLOWED_JOURNAL_OPERATIONS) | {port_names.OPERATION}
        with patch.object(port_names, "ALLOWED_JOURNAL_OPERATIONS", allowed):
            recovered = self.manager(writes_enabled=True, journal=journal,
                                     require_journal=True)
        self.assertEqual(recovered.list_in_doubt(), [{
            "plan_id": PLAN_ID, "state": "in_doubt", "scope": "switch_port_name",
            "target_refs": {"site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": 7},
        }])
        before_reads = len(self.read_calls)
        inspected = recovered.inspect_in_doubt(PLAN_ID)
        self.assertEqual(len(self.read_calls), before_reads + 1)
        self.assertEqual(inspected["before"], MARKER)
        self.assertEqual(inspected["target"], MARKER)
        self.assertNotIn(NAME, repr(inspected))
        self.assertNotIn(TARGET, repr(inspected))
        with self.assertRaisesRegex(PortNameChangeError, "plan_already_consumed"):
            recovered.apply(PLAN_ID)
        self.assertEqual(self.write_calls, [])


if __name__ == "__main__":
    unittest.main()
