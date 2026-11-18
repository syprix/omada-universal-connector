from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from app.change_journal import ChangePlanJournal
from app.changes import ChangeError, RadioChangePlans
from app.dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans


SITE, DEVICE = "a" * 24, "b" * 24
BINDING = "c" * 64
CONFIRM = "outcome_unknown_no_retry"


class RadioDnsJournalIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        os.chmod(self.temp.name, 0o700)
        self.journal = ChangePlanJournal(self.temp.name, controller_binding=BINDING)

    def tearDown(self) -> None:
        self.journal.close()
        self.temp.cleanup()

    def radio(self, *, write=None, require_journal=True):
        state = {"radioSetting2g": {"txPowerLevel": 1}}
        writes = []

        def read(*_refs):
            return {key: dict(value) for key, value in state.items()}

        def do_write(*args):
            writes.append(args)
            if write:
                return write(state, *args)
            state.update(args[-1])

        manager = RadioChangePlans(read, do_write, writes_enabled=True,
                                   journal=self.journal, require_journal=require_journal)
        preview = manager.preview(SITE, DEVICE, {"radioSetting2g": {"txPowerLevel": 2}})
        return manager, preview["plan_id"], writes, state

    def dns(self, *, write=None, require_journal=True):
        state = {"enable": True, "ttl": 600}
        writes = []

        def read(_site):
            return dict(state)

        def do_write(_site, target):
            writes.append(dict(target))
            if write:
                return write(state, target)
            state.update(target)

        manager = DnsCacheChangePlans(read, do_write, writes_enabled=True,
                                     journal=self.journal, require_journal=require_journal)
        preview = manager.preview(SITE, {"ttl": 700})
        return manager, preview["plan_id"], writes, state

    def test_intent_is_durable_before_each_write_and_verified_outcome_follows_readback(self):
        for kind, factory in (("radio", self.radio), ("dns", self.dns)):
            with self.subTest(kind=kind):
                observed = []
                if kind == "radio":
                    manager, plan_id, writes, state = factory(
                        write=lambda current, *args: (observed.append(self.journal.plan_state(plan_id)),
                                                     current.update(args[-1])))
                else:
                    manager, plan_id, writes, state = factory(
                        write=lambda current, target: (observed.append(self.journal.plan_state(plan_id)),
                                                      current.update(target)))
                result = manager.apply(plan_id)
                self.assertEqual(observed, ["in_doubt"])
                self.assertEqual(len(writes), 1)
                self.assertEqual(self.journal.plan_state(plan_id), "verified")
                self.assertEqual(result["status"], "verified")
                with self.assertRaisesRegex((ChangeError if kind == "radio" else DnsCacheChangeError), "consumed"):
                    manager.apply(plan_id)

    def test_required_journal_missing_blocks_write(self):
        for kind in ("radio", "dns"):
            with self.subTest(kind=kind):
                if kind == "radio":
                    state = {"radioSetting2g": {"txPowerLevel": 1}}
                    manager = RadioChangePlans(lambda *_: {k: dict(v) for k, v in state.items()},
                                               lambda *_: self.fail("write without journal"),
                                               writes_enabled=True, require_journal=True)
                    plan = manager.preview(SITE, DEVICE, {"radioSetting2g": {"txPowerLevel": 2}})["plan_id"]
                    error = ChangeError
                else:
                    manager = DnsCacheChangePlans(lambda _: {"enable": True, "ttl": 600},
                                                  lambda *_: self.fail("write without journal"),
                                                  writes_enabled=True, require_journal=True)
                    plan = manager.preview(SITE, {"ttl": 700})["plan_id"]
                    error = DnsCacheChangeError
                with self.assertRaisesRegex(error, "journal_required"):
                    manager.apply(plan)

    def test_intent_sync_crossing_deadline_prevents_write_for_both_managers(self):
        for kind in ("radio", "dns"):
            with self.subTest(kind=kind):
                now = [0.0]

                class AdvancingJournal:
                    def in_doubt_plans(inner):
                        return self.journal.in_doubt_plans()

                    def record_dispatch_intent(inner, **kwargs):
                        self.journal.record_dispatch_intent(**kwargs)
                        now[0] = 5.0

                    def record_outcome(inner, *args):
                        return self.journal.record_outcome(*args)

                    def close_unknown(inner, *args):
                        return self.journal.close_unknown(*args)

                journal = AdvancingJournal()
                writes = []
                if kind == "radio":
                    state = {"radioSetting2g": {"txPowerLevel": 1}}
                    manager = RadioChangePlans(
                        lambda *_: {k: dict(v) for k, v in state.items()},
                        lambda *args: writes.append(args), writes_enabled=True,
                        ttl=5, clock=lambda: now[0], journal=journal, require_journal=True)
                    plan = manager.preview(SITE, DEVICE,
                                           {"radioSetting2g": {"txPowerLevel": 2}})["plan_id"]
                    error = ChangeError
                else:
                    manager = DnsCacheChangePlans(
                        lambda _: {"enable": True, "ttl": 600},
                        lambda *args: writes.append(args), writes_enabled=True,
                        ttl_seconds=5, clock=lambda: now[0], journal=journal,
                        require_journal=True)
                    plan = manager.preview(SITE, {"ttl": 700})["plan_id"]
                    error = DnsCacheChangeError
                now[0] = 1.0
                with self.assertRaisesRegex(error, "plan_expired"):
                    manager.apply(plan)
                self.assertEqual(writes, [])
                self.assertEqual(manager.plans[plan]["state"], "in_doubt")
                self.assertEqual(self.journal.plan_state(plan), "in_doubt")

    def test_timeout_records_unknown_and_restart_recovers_in_doubt_without_replay(self):
        for kind, factory, error in (("radio", self.radio, ChangeError),
                                     ("dns", self.dns, DnsCacheChangeError)):
            with self.subTest(kind=kind):
                def timeout(*_args):
                    raise TimeoutError
                manager, plan_id, writes, _state = factory(write=timeout)
                with self.assertRaisesRegex(error, "in_doubt"):
                    manager.apply(plan_id)
                self.assertEqual(self.journal.plan_state(plan_id), "in_doubt")
                self.journal.close()
                self.journal = ChangePlanJournal(self.temp.name, controller_binding=BINDING)
                if kind == "radio":
                    recovered = RadioChangePlans(lambda *_: {}, lambda *_: self.fail("replay"),
                                                 writes_enabled=True, journal=self.journal,
                                                 require_journal=True)
                else:
                    recovered = DnsCacheChangePlans(lambda _: {}, lambda *_: self.fail("replay"),
                                                    writes_enabled=True, journal=self.journal,
                                                    require_journal=True)
                self.assertEqual(recovered.list_in_doubt()[0]["plan_id"], plan_id)
                with self.assertRaisesRegex(error, "consumed"):
                    recovered.apply(plan_id)
                recovered.close_in_doubt(plan_id, CONFIRM)
                self.assertEqual(self.journal.plan_state(plan_id), "closed_outcome_unknown")

    def test_close_failure_keeps_local_plan_and_intent_sync_failure_blocks_write(self):
        manager, plan_id, writes, _state = self.radio(write=lambda *_: (_ for _ in ()).throw(TimeoutError()))
        with self.assertRaisesRegex(ChangeError, "in_doubt"):
            manager.apply(plan_id)
        with patch.object(self.journal, "close_unknown", side_effect=RuntimeError):
            with self.assertRaisesRegex(ChangeError, "journal_unavailable"):
                manager.close_in_doubt(plan_id, CONFIRM)
        self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")

        manager, plan_id, writes, _state = self.dns()
        with patch("app.change_journal.os.fsync", side_effect=OSError):
            with self.assertRaisesRegex(DnsCacheChangeError, "journal_unavailable"):
                manager.apply(plan_id)
        self.assertEqual(writes, [])
        self.assertEqual(manager.plans[plan_id]["state"], "in_doubt")

    def test_recovery_rejects_malformed_matching_operation_records(self):
        radio_base = {
            "plan_id": "d" * 48, "operation": "radio",
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"radioSetting2g": {"txPowerLevel": 1}},
            "target": {"radioSetting2g": {"txPowerLevel": 2}}, "state": "in_doubt",
        }
        dns_base = {
            "plan_id": "e" * 48, "operation": "dns-cache",
            "target_refs": {"site_ref": SITE},
            "before": {"enable": True, "ttl": 600},
            "target": {"enable": True, "ttl": 700}, "state": "in_doubt",
        }

        for kind, base in (("radio", radio_base), ("dns", dns_base)):
            variants = []
            for key, value in (("target_refs", None), ("state", "pending"),
                               ("plan_id", "bad")):
                broken = dict(base)
                broken[key] = value
                variants.append(broken)
            broken_refs = dict(base)
            broken_refs["target_refs"] = {"site_ref": SITE, "unexpected": "x"}
            variants.append(broken_refs)
            broken_snapshot = dict(base)
            broken_snapshot["before"] = {"secret": "must-not-be-accepted"}
            variants.append(broken_snapshot)

            for record in variants:
                with self.subTest(kind=kind, record=record):
                    class FakeJournal:
                        def in_doubt_plans(self):
                            return [record]
                    if kind == "radio":
                        with self.assertRaisesRegex(ChangeError, "journal_unavailable"):
                            RadioChangePlans(lambda *_: {}, lambda *_: None,
                                             journal=FakeJournal(), require_journal=True)
                    else:
                        with self.assertRaisesRegex(DnsCacheChangeError, "journal_unavailable"):
                            DnsCacheChangePlans(lambda *_: {}, lambda *_: None,
                                                journal=FakeJournal(), require_journal=True)


if __name__ == "__main__":
    unittest.main()
