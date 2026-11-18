from __future__ import annotations

import copy
import unittest

from app.port_status_changes import PortStatusChangeError, SwitchPortStatusPlans


SITE, SWITCH = "a" * 24, "b" * 24
CONFIRMATION = "outcome_unknown_no_retry"


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class FakeJournal:
    """In-memory durable-contract double for the new journal operation."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self.events: list[tuple[str, str, object]] = []
        self.fail_intent = False
        self.fail_outcome = False
        self.fail_close = False
        self.on_intent = None
        self.clock = clock

    def in_doubt_plans(self):
        return [copy.deepcopy(row) for row in self.rows.values()
                if row["state"] == "in_doubt"]

    def record_dispatch_intent(self, *, operation, plan_id, target_refs, before, target):
        if self.fail_intent:
            raise OSError("intent fsync failed")
        row = {"operation": operation, "plan_id": plan_id, "target_refs": copy.deepcopy(target_refs),
               "before": copy.deepcopy(before), "target": copy.deepcopy(target),
               "state": "in_doubt"}
        self.rows[plan_id] = row
        self.events.append(("dispatch_intent", plan_id, copy.deepcopy(row)))
        if self.on_intent:
            self.on_intent()

    def record_outcome(self, plan_id, outcome):
        if self.fail_outcome:
            raise OSError("outcome fsync failed")
        row = self.rows[plan_id]
        row["outcome"] = outcome
        if outcome == "verified_readback":
            row["state"] = "verified"
        self.events.append(("dispatch_outcome", plan_id, outcome))

    def close_unknown(self, plan_id, confirmation):
        if self.fail_close:
            raise OSError("close fsync failed")
        row = self.rows[plan_id]
        row["state"] = "closed_outcome_unknown"
        self.events.append(("operator_closed_unknown", plan_id, confirmation))


def build_manager(*, journal=None, require_journal=False, writes_enabled=True,
                  clock=None, limit=100, read_hook=None, write_hook=None):
    state = {"status": 0}
    reads = []
    writes = []

    def read(site_ref, switch_ref, port):
        reads.append((site_ref, switch_ref, port))
        if read_hook:
            read_hook(state, reads)
        return dict(state)

    def write(site_ref, switch_ref, port, body):
        writes.append((site_ref, switch_ref, port, dict(body)))
        if write_hook:
            write_hook(state, journal)
        state.update(body)

    options = {"writes_enabled": writes_enabled, "journal": journal,
               "require_journal": require_journal, "limit": limit}
    if clock is not None:
        options.update(clock=clock, ttl_seconds=300)
    manager = SwitchPortStatusPlans(read, write, **options)
    return manager, state, reads, writes


class SwitchPortStatusPlanTests(unittest.TestCase):
    def preview(self, manager, value=1, *, confirmed=True):
        return manager.preview(SITE, SWITCH, 7, {"status": value},
                              disruption_confirmed=confirmed)

    def test_default_off_and_explicit_disruption_confirmation(self) -> None:
        manager, _state, reads, writes = build_manager(writes_enabled=False)
        with self.assertRaisesRegex(PortStatusChangeError, "disruption_confirmation_required"):
            self.preview(manager, confirmed=False)
        self.assertEqual(reads, [])
        self.assertEqual(writes, [])
        preview = self.preview(manager)
        self.assertEqual(preview["expires_in_seconds"], 300)
        self.assertEqual(preview["before"], {"status": 0})
        self.assertEqual(preview["target"], {"status": 1})
        self.assertEqual(preview["rollback"], {"status": 0})
        self.assertIn("may_interrupt_access", preview["warning"])
        with self.assertRaisesRegex(PortStatusChangeError, "writes_disabled"):
            manager.apply(preview["plan_id"])
        self.assertEqual(writes, [])

    def test_exact_status_shape_refs_limit_and_noop(self) -> None:
        manager, _state, _reads, _writes = build_manager(limit=1)
        for args in (("bad", SWITCH, 7), (SITE, "bad", 7), (SITE, SWITCH, True),
                     (SITE, SWITCH, 4097)):
            with self.subTest(args=args), self.assertRaises(PortStatusChangeError):
                manager.preview(*args, {"status": 1}, disruption_confirmed=True)
        for change in ({}, {"status": True}, {"status": 2}, {"status": 1, "extra": 1}):
            with self.subTest(change=change), self.assertRaises(PortStatusChangeError):
                manager.preview(SITE, SWITCH, 7, change, disruption_confirmed=True)
        self.preview(manager)
        with self.assertRaisesRegex(PortStatusChangeError, "plan_capacity_reached"):
            manager.preview(SITE, SWITCH, 8, {"status": 1}, disruption_confirmed=True)
        manager2, _state2, _reads2, _writes2 = build_manager()
        with self.assertRaisesRegex(PortStatusChangeError, "no_change"):
            manager2.preview(SITE, SWITCH, 7, {"status": 0}, disruption_confirmed=True)

    def test_verified_write_records_intent_before_callback_and_outcome_after_readback(self) -> None:
        journal = FakeJournal()
        def assert_intent_on_disk(_state, current_journal):
            self.assertEqual([event[0] for event in current_journal.events], ["dispatch_intent"])
            event = current_journal.events[0][2]
            self.assertEqual(event["operation"], "switch-port-status")
            self.assertEqual(event["target_refs"],
                             {"site_ref": SITE, "switch_ref": SWITCH, "port": 7})
            self.assertEqual(event["before"], {"status": 0})
            self.assertEqual(event["target"], {"status": 1})
        manager, state, _reads, writes = build_manager(journal=journal,
                                                       require_journal=True,
                                                       write_hook=assert_intent_on_disk)
        preview = self.preview(manager)
        result = manager.apply(preview["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(state, {"status": 1})
        self.assertEqual(len(writes), 1)
        self.assertEqual([event[0] for event in journal.events],
                         ["dispatch_intent", "dispatch_outcome"])
        self.assertEqual(journal.events[-1][2], "verified_readback")
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "applied")
        with self.assertRaisesRegex(PortStatusChangeError, "plan_already_consumed"):
            manager.apply(preview["plan_id"])

    def test_required_journal_missing_prevents_write(self) -> None:
        manager, _state, _reads, writes = build_manager(journal=None, require_journal=True)
        preview = self.preview(manager)
        with self.assertRaisesRegex(PortStatusChangeError, "journal_required"):
            manager.apply(preview["plan_id"])
        self.assertEqual(writes, [])
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "pending")

    def test_stale_state_prevents_journal_intent_and_write(self) -> None:
        journal = FakeJournal()
        def change_on_apply(state, reads):
            if len(reads) == 2:
                state["status"] = 1
        manager, _state, _reads, writes = build_manager(
            journal=journal, require_journal=True, read_hook=change_on_apply)
        preview = self.preview(manager)
        with self.assertRaisesRegex(PortStatusChangeError, "state_changed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(journal.events, [])
        self.assertEqual(writes, [])
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "stale")

    def test_expiry_during_read_or_journal_intent_never_writes(self) -> None:
        clock = FakeClock()
        def expire_during_read(_state, reads):
            if len(reads) == 2:
                clock.value = 300
        manager, _state, _reads, writes = build_manager(
            clock=clock, journal=FakeJournal(), require_journal=True,
            read_hook=expire_during_read)
        preview = self.preview(manager)
        with self.assertRaisesRegex(PortStatusChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual(writes, [])

        clock = FakeClock()
        journal = FakeJournal(clock)
        journal.on_intent = lambda: setattr(clock, "value", 300)
        manager, _state, _reads, writes = build_manager(
            journal=journal, require_journal=True, clock=clock)
        preview = self.preview(manager)
        with self.assertRaisesRegex(PortStatusChangeError, "plan_expired"):
            manager.apply(preview["plan_id"])
        self.assertEqual([event[0] for event in journal.events], ["dispatch_intent", "dispatch_outcome"])
        self.assertEqual(journal.events[-1][-1], "unknown")
        self.assertEqual(writes, [])
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "in_doubt")

    def test_timeout_recovers_in_doubt_never_replays_and_close_is_journal_first(self) -> None:
        journal = FakeJournal()
        def timeout_after_mutation(state, _journal):
            state["status"] = 1
            raise TimeoutError("ambiguous write")
        manager, _state, _reads, writes = build_manager(
            journal=journal, require_journal=True, write_hook=timeout_after_mutation)
        preview = self.preview(manager)
        with self.assertRaisesRegex(PortStatusChangeError, "change_in_doubt"):
            manager.apply(preview["plan_id"])
        self.assertEqual(journal.events[-1][2], "unknown")
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "in_doubt")

        recovered, _state2, _reads2, writes2 = build_manager(journal=journal,
                                                             require_journal=True)
        self.assertEqual(recovered.plans[preview["plan_id"]]["state"], "in_doubt")
        self.assertEqual(recovered.list_in_doubt()[0]["target_refs"],
                         {"site_ref": SITE, "switch_ref": SWITCH, "port": 7})
        inspection = recovered.inspect_in_doubt(preview["plan_id"])
        self.assertEqual(inspection["outcome"], "unknown")
        self.assertEqual(inspection["before"], {"status": 0})
        self.assertEqual(inspection["target"], {"status": 1})
        with self.assertRaisesRegex(PortStatusChangeError, "plan_already_consumed"):
            recovered.apply(preview["plan_id"])
        self.assertEqual(writes2, [])

        journal.fail_close = True
        with self.assertRaisesRegex(PortStatusChangeError, "journal_unavailable"):
            recovered.close_in_doubt(preview["plan_id"], CONFIRMATION)
        self.assertIn(preview["plan_id"], recovered.plans)
        journal.fail_close = False
        recovered.close_in_doubt(preview["plan_id"], CONFIRMATION)
        self.assertNotIn(preview["plan_id"], recovered.plans)
        self.assertEqual(journal.rows[preview["plan_id"]]["state"], "closed_outcome_unknown")
        self.assertEqual(len(writes), 1)

    def test_intent_failure_and_readback_failure_are_in_doubt_and_nonreplayable(self) -> None:
        journal = FakeJournal()
        manager, _state, _reads, writes = build_manager(journal=journal,
                                                        require_journal=True)
        preview = self.preview(manager)
        journal.fail_intent = True
        with self.assertRaisesRegex(PortStatusChangeError, "journal_unavailable"):
            manager.apply(preview["plan_id"])
        self.assertEqual(writes, [])
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "in_doubt")
        with self.assertRaisesRegex(PortStatusChangeError, "plan_already_consumed"):
            manager.apply(preview["plan_id"])

        journal = FakeJournal()
        manager, state, reads, writes = build_manager(journal=journal,
                                                      require_journal=True)
        preview = self.preview(manager)
        manager.write = lambda *_args: None
        with self.assertRaisesRegex(PortStatusChangeError, "change_in_doubt"):
            manager.apply(preview["plan_id"])
        self.assertEqual(journal.events[-1][2], "unknown")
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "in_doubt")
        with self.assertRaisesRegex(PortStatusChangeError, "plan_already_consumed"):
            manager.apply(preview["plan_id"])
        self.assertEqual(len(writes), 0)

    def test_journal_failure_on_verified_outcome_never_reports_success(self) -> None:
        journal = FakeJournal()
        manager, _state, _reads, _writes = build_manager(journal=journal,
                                                         require_journal=True)
        preview = self.preview(manager)
        journal.fail_outcome = True
        with self.assertRaisesRegex(PortStatusChangeError, "change_in_doubt"):
            manager.apply(preview["plan_id"])
        self.assertEqual(manager.plans[preview["plan_id"]]["state"], "in_doubt")
        self.assertEqual([event[0] for event in journal.events], ["dispatch_intent"])


if __name__ == "__main__":
    unittest.main()
