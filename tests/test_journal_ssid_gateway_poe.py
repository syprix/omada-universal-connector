from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.change_journal import ChangePlanJournal
from app.changes import ChangeError, RadioChangePlans
from app.dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans
from app.gateway_ipv6_changes import GatewayIpv6ChangeError, GatewayIpv6IpPassthroughPlans
from app.poe_changes import PoeChangeError, PoeModePlans
from app.ssid_changes import SsidChangeError, SsidChangePlans


SITE, TARGET, BINDING = "a" * 24, "b" * 24, "c" * 64


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class ExpiringJournal:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls = []

    def in_doubt_plans(self):
        return []

    def record_dispatch_intent(self, **event) -> None:
        self.calls.append(("intent", event))
        self.clock.value = 5.0

    def record_outcome(self, *args) -> None:
        self.calls.append(("outcome", args))

    def close_unknown(self, *args) -> None:
        self.calls.append(("close", args))


class FakeRecoveryJournal:
    def __init__(self, rows) -> None:
        self.rows = rows

    def in_doubt_plans(self):
        return self.rows

    def record_dispatch_intent(self, **_kwargs) -> None:
        pass

    def close_unknown(self, *_args) -> None:
        pass


def make_case(kind: str, journal=None, *, require_journal: bool = False,
              clock=None, writes_enabled=True, write_hook=None):
    state = {"ssidEnable": False} if kind == "ssid" else (
        {"enable": False} if kind == "gateway-ipv6" else
        {"poe": 0, "supportPoe": True, "profileOverrideEnable": True})
    writes = []

    def read(*_args):
        return dict(state)

    def write(*args):
        writes.append(args)
        if write_hook:
            write_hook()
        body = args[-1]
        if kind == "ssid":
            state.update(body)
        elif kind == "gateway-ipv6":
            state.update(body)
        else:
            state["poe"] = body["poeMode"]

    options = {"writes_enabled": writes_enabled, "journal": journal,
               "require_journal": require_journal}
    if clock is not None:
        options["clock"] = clock
        options["ttl_seconds"] = 5
    if kind == "ssid":
        manager = SsidChangePlans(read, write, **options)
        preview = lambda: manager.preview(SITE, TARGET, {"ssidEnable": True})
    elif kind == "gateway-ipv6":
        manager = GatewayIpv6IpPassthroughPlans(read, write, **options)
        preview = lambda: manager.preview(SITE, TARGET, {"enable": True})
    else:
        manager = PoeModePlans(read, write, **options)
        preview = lambda: manager.preview(SITE, TARGET, 7, {"poeMode": 1})
    return manager, state, writes, preview


class JournalSsidGatewayPoeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def open_journal(self) -> ChangePlanJournal:
        return ChangePlanJournal(self.tmp.name, controller_binding=BINDING)

    def fresh_journal(self):
        directory = tempfile.TemporaryDirectory(dir=self.tmp.name)
        self.addCleanup(directory.cleanup)
        return directory, ChangePlanJournal(directory.name, controller_binding=BINDING)

    def test_required_journal_missing_never_calls_any_write(self) -> None:
        for kind, error in (("ssid", SsidChangeError),
                            ("gateway-ipv6", GatewayIpv6ChangeError),
                            ("poe", PoeChangeError)):
            manager, _state, writes, preview = make_case(kind, require_journal=True)
            plan = preview()
            with self.subTest(kind=kind), self.assertRaisesRegex(error, "journal_required"):
                manager.apply(plan["plan_id"])
            self.assertEqual(writes, [])

    def test_intent_is_durable_before_write_and_verified_outcome_follows_readback(self) -> None:
        for kind in ("ssid", "gateway-ipv6", "poe"):
            with self.subTest(kind=kind):
                directory, journal = self.fresh_journal()
                with journal:
                    observed = []
                    def check_intent_is_on_disk():
                        lines = (Path(directory.name) / "change-plans.jsonl").read_text().splitlines()
                        observed.extend(json.loads(line)["event_type"] for line in lines)
                    manager, _state, writes, preview = make_case(
                        kind, journal, require_journal=True, write_hook=check_intent_is_on_disk)
                    plan = preview()
                    result = manager.apply(plan["plan_id"])
                    self.assertEqual(result["status"], "verified")
                    self.assertEqual(observed[0], "dispatch_intent")
                    events = [json.loads(line)["event_type"] for line in
                              (Path(directory.name) / "change-plans.jsonl").read_text().splitlines()]
                    self.assertEqual(events, ["dispatch_intent", "dispatch_outcome"])
                    self.assertEqual(journal.plan_state(plan["plan_id"]), "verified")
                    self.assertEqual(len(writes), 1)

    def test_timeout_recovers_in_doubt_never_replays_and_closes_journal_first(self) -> None:
        for kind, error in (("ssid", SsidChangeError),
                            ("gateway-ipv6", GatewayIpv6ChangeError),
                            ("poe", PoeChangeError)):
            with self.subTest(kind=kind):
                _directory, journal = self.fresh_journal()
                with journal:
                    manager, _state, writes, preview = make_case(kind, journal,
                                                                require_journal=True)
                    plan = preview()
                    manager.write = lambda *_args: (_ for _ in ()).throw(TimeoutError())
                    with self.assertRaisesRegex(error, "change_in_doubt"):
                        manager.apply(plan["plan_id"])
                    self.assertEqual(journal.plan_state(plan["plan_id"]), "in_doubt")
                    self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")
                    events = [json.loads(line) for line in
                              (Path(_directory.name) / "change-plans.jsonl").read_text().splitlines()]
                    self.assertEqual([event["event_type"] for event in events],
                                     ["dispatch_intent", "dispatch_outcome"])
                    self.assertEqual(events[-1]["outcome"], "unknown")

                    recovered, _state2, writes2, _preview = make_case(
                        kind, journal, require_journal=True)
                    self.assertEqual(recovered.plans[plan["plan_id"]]["state"], "in_doubt")
                    if kind == "poe":
                        inspected = recovered.inspect_in_doubt(plan["plan_id"])
                        self.assertEqual(inspected["before"], {"poeMode": 0})
                        self.assertEqual(inspected["target"], {"poeMode": 1})
                    with self.assertRaisesRegex(error, "plan_already_consumed"):
                        recovered.apply(plan["plan_id"])
                    self.assertEqual(writes2, [])
                    close_unknown = journal.close_unknown
                    with self.assertRaisesRegex(error, "journal_unavailable"):
                        recovered.journal.close_unknown = lambda *_args: (_ for _ in ()).throw(OSError())
                        recovered.close_in_doubt(plan["plan_id"], "outcome_unknown_no_retry")
                    self.assertIn(plan["plan_id"], recovered.plans)
                    recovered.journal.close_unknown = close_unknown
                    recovered.close_in_doubt(plan["plan_id"], "outcome_unknown_no_retry")
                    self.assertNotIn(plan["plan_id"], recovered.plans)
                    self.assertEqual(journal.plan_state(plan["plan_id"]), "closed_outcome_unknown")
                    if kind == "poe":
                        self.assertEqual(recovered.plans, {})

    def test_recovery_only_loads_each_manager_operation(self) -> None:
        with self.open_journal() as journal:
            journal.record_dispatch_intent(
                operation="ssid", plan_id="1" * 48,
                target_refs={"site_ref": SITE, "ssid_ref": TARGET},
                before={"ssidEnable": False}, target={"ssidEnable": True})
            journal.record_dispatch_intent(
                operation="gateway-ipv6", plan_id="2" * 48,
                target_refs={"site_ref": SITE, "gateway_ref": TARGET},
                before={"enable": False}, target={"enable": True})
            journal.record_dispatch_intent(
                operation="poe", plan_id="3" * 48,
                target_refs={"site_ref": SITE, "switch_ref": TARGET, "port": 7},
                before={"poeMode": 0}, target={"poeMode": 1})
            def read_ssid(*_args): return {"ssidEnable": False}
            def write_ssid(*_args): self.fail("recovery must not write")
            def read_gateway(*_args): return {"enable": False}
            def write_gateway(*_args): self.fail("recovery must not write")
            def read_poe(*_args):
                return {"poe": 0, "supportPoe": True, "profileOverrideEnable": True}
            def write_poe(*_args): self.fail("recovery must not write")

            ssid = SsidChangePlans(read_ssid, write_ssid, journal=journal)
            gateway = GatewayIpv6IpPassthroughPlans(read_gateway, write_gateway, journal=journal)
            poe = PoeModePlans(read_poe, write_poe, journal=journal)
            self.assertEqual(set(ssid.plans), {"1" * 48})
            self.assertEqual(set(gateway.plans), {"2" * 48})
            self.assertEqual(set(poe.plans), {"3" * 48})

    def test_malformed_matching_recovery_rows_fail_closed(self) -> None:
        fixtures = {
            "ssid": {
                "plan_id": "1" * 48, "operation": "ssid", "state": "in_doubt",
                "target_refs": {"site_ref": SITE, "ssid_ref": TARGET},
                "before": {"ssidEnable": False}, "target": {"ssidEnable": True},
            },
            "gateway-ipv6": {
                "plan_id": "2" * 48, "operation": "gateway-ipv6", "state": "in_doubt",
                "target_refs": {"site_ref": SITE, "gateway_ref": TARGET},
                "before": {"enable": False}, "target": {"enable": True},
            },
            "poe": {
                "plan_id": "3" * 48, "operation": "poe", "state": "in_doubt",
                "target_refs": {"site_ref": SITE, "switch_ref": TARGET, "port": 7},
                "before": {"poeMode": 0}, "target": {"poeMode": 1},
            },
        }
        creators = {
            "ssid": lambda journal: SsidChangePlans(lambda *_: {"ssidEnable": False},
                                                    lambda *_: None, journal=journal),
            "gateway-ipv6": lambda journal: GatewayIpv6IpPassthroughPlans(
                lambda *_: {"enable": False}, lambda *_: None, journal=journal),
            "poe": lambda journal: PoeModePlans(
                lambda *_: {"poe": 0, "supportPoe": True, "profileOverrideEnable": True},
                lambda *_: None, journal=journal),
        }
        errors = {"ssid": SsidChangeError, "gateway-ipv6": GatewayIpv6ChangeError,
                  "poe": PoeChangeError}
        bad_mutations = (
            lambda row: row.update(target_refs=None),
            lambda row: row.update(target_refs={"site_ref": SITE}),
            lambda row: row["target_refs"].update(site_ref="not-a-ref"),
            lambda row: row["target_refs"].update(extra="x"),
            lambda row: row.update(plan_id="not-a-plan"),
            lambda row: row.update(state="pending"),
            lambda row: row.update(before={"unexpected": True}),
            lambda row: row.update(target={"unexpected": True}),
        )
        invalid_targets = {
            "ssid": {"ssidEnable": 1},
            "gateway-ipv6": {"enable": 1},
            "poe": {"poeMode": True},
        }
        for kind, template in fixtures.items():
            mutations = (*bad_mutations,
                         lambda row, target=invalid_targets[kind]: row.update(target=target))
            for mutate in mutations:
                row = dict(template)
                row["target_refs"] = (dict(template["target_refs"])
                                      if isinstance(template["target_refs"], dict) else None)
                mutate(row)
                with self.subTest(kind=kind, row=row), self.assertRaisesRegex(
                        errors[kind], "journal_unavailable"):
                    creators[kind](FakeRecoveryJournal([row]))

    def test_foreign_known_operations_are_ignored_during_recovery(self) -> None:
        malformed_foreign = {"operation": "radio"}
        ssid = SsidChangePlans(lambda *_: {"ssidEnable": False}, lambda *_: None,
                               journal=FakeRecoveryJournal([malformed_foreign]))
        gateway = GatewayIpv6IpPassthroughPlans(lambda *_: {"enable": False}, lambda *_: None,
                                                journal=FakeRecoveryJournal([malformed_foreign]))
        poe = PoeModePlans(lambda *_: {"poe": 0, "supportPoe": True,
                                       "profileOverrideEnable": True}, lambda *_: None,
                           journal=FakeRecoveryJournal([malformed_foreign]))
        self.assertEqual(ssid.plans, {})
        self.assertEqual(gateway.plans, {})
        self.assertEqual(poe.plans, {})

    def test_switch_port_status_journal_is_ignored_by_all_foreign_managers(self) -> None:
        with self.open_journal() as journal:
            journal.record_dispatch_intent(
                operation="switch-port-status", plan_id="f" * 48,
                target_refs={"site_ref": SITE, "switch_ref": TARGET, "port": 12},
                before={"status": 1}, target={"status": 0})
            managers = (
                RadioChangePlans(lambda *_: {}, lambda *_: None, journal=journal),
                DnsCacheChangePlans(lambda *_: {"enable": False, "ttl": 60},
                                    lambda *_: None, journal=journal),
                SsidChangePlans(lambda *_: {"ssidEnable": False}, lambda *_: None,
                                journal=journal),
                GatewayIpv6IpPassthroughPlans(lambda *_: {"enable": False},
                                               lambda *_: None, journal=journal),
                PoeModePlans(lambda *_: {"poe": 0, "supportPoe": True,
                                         "profileOverrideEnable": True},
                             lambda *_: None, journal=journal),
            )
            self.assertEqual(journal.in_doubt_plans()[0]["operation"], "switch-port-status")
            self.assertTrue(all(manager.plans == {} for manager in managers))

    def test_unknown_journal_operation_remains_fail_closed_for_all_managers(self) -> None:
        errors_and_creators = (
            (ChangeError, lambda journal: RadioChangePlans(
                lambda *_: {}, lambda *_: None, journal=journal)),
            (DnsCacheChangeError, lambda journal: DnsCacheChangePlans(
                lambda *_: {"enable": False, "ttl": 60}, lambda *_: None, journal=journal)),
            (SsidChangeError, lambda journal: SsidChangePlans(
                lambda *_: {"ssidEnable": False}, lambda *_: None, journal=journal)),
            (GatewayIpv6ChangeError, lambda journal: GatewayIpv6IpPassthroughPlans(
                lambda *_: {"enable": False}, lambda *_: None, journal=journal)),
            (PoeChangeError, lambda journal: PoeModePlans(
                lambda *_: {"poe": 0, "supportPoe": True, "profileOverrideEnable": True},
                lambda *_: None, journal=journal)),
        )
        for error, create in errors_and_creators:
            with self.subTest(error=error.__name__), self.assertRaisesRegex(
                    error, "journal_unavailable"):
                create(FakeRecoveryJournal([{"operation": "future-unknown-operation"}]))

    def test_journal_deadline_expiry_after_intent_prevents_write(self) -> None:
        for kind, error in (("ssid", SsidChangeError),
                            ("gateway-ipv6", GatewayIpv6ChangeError),
                            ("poe", PoeChangeError)):
            with self.subTest(kind=kind):
                clock = FakeClock()
                journal = ExpiringJournal(clock)
                manager, _state, writes, preview = make_case(
                    kind, journal, require_journal=True, clock=clock)
                plan = preview()
                with self.assertRaisesRegex(error, "plan_expired"):
                    manager.apply(plan["plan_id"])
                self.assertEqual(len(journal.calls), 2)
                self.assertEqual(journal.calls[0][0], "intent")
                self.assertEqual(journal.calls[1], ("outcome", (plan["plan_id"], "unknown")))
                self.assertEqual(writes, [])
                self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")
                with self.assertRaisesRegex(error, "plan_already_consumed"):
                    manager.apply(plan["plan_id"])
                self.assertEqual(writes, [])
                self.assertEqual(len(journal.calls), 2)

    def test_intent_journal_failure_blocks_write_and_leaves_plan_nonreplayable(self) -> None:
        for kind, error in (("ssid", SsidChangeError),
                            ("gateway-ipv6", GatewayIpv6ChangeError),
                            ("poe", PoeChangeError)):
            with self.subTest(kind=kind):
                _directory, journal = self.fresh_journal()
                with journal:
                    manager, _state, writes, preview = make_case(kind, journal,
                                                                require_journal=True)
                    plan = preview()
                    journal.record_dispatch_intent = lambda **_kwargs: (_ for _ in ()).throw(OSError())
                    with self.assertRaisesRegex(error, "journal_unavailable"):
                        manager.apply(plan["plan_id"])
                    self.assertEqual(writes, [])
                    self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")
                    with self.assertRaisesRegex(error, "plan_already_consumed"):
                        manager.apply(plan["plan_id"])

    def test_journal_fsync_failure_blocks_write_for_all_three_managers(self) -> None:
        for kind, error in (("ssid", SsidChangeError),
                            ("gateway-ipv6", GatewayIpv6ChangeError),
                            ("poe", PoeChangeError)):
            with self.subTest(kind=kind):
                _directory, journal = self.fresh_journal()
                with journal:
                    manager, _state, writes, preview = make_case(
                        kind, journal, require_journal=True)
                    plan = preview()
                    with patch("app.change_journal.os.fsync", side_effect=OSError("disk failure")):
                        with self.assertRaisesRegex(error, "journal_unavailable"):
                            manager.apply(plan["plan_id"])
                    self.assertEqual(writes, [])
                    self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")


if __name__ == "__main__":
    unittest.main()
