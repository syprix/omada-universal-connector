from __future__ import annotations

import copy
import unittest

from app.changes import RadioChangePlans
from app.dns_cache_changes import DnsCacheChangePlans
from app.gateway_ipv6_changes import GatewayIpv6IpPassthroughPlans
from app.poe_changes import PoeModePlans
from app.ssid_changes import SsidChangePlans


SITE = "a" * 24
DEVICE = "b" * 24
SSID = "c" * 24
GATEWAY = "d" * 24
SWITCH = "e" * 24
PORT = 7


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeJournal:
    def __init__(self, on_intent=None) -> None:
        self.on_intent = on_intent
        self.intents: list[dict[str, object]] = []
        self.outcomes: list[tuple[str, str]] = []

    def in_doubt_plans(self):
        return []

    def record_dispatch_intent(self, **event) -> None:
        self.intents.append(copy.deepcopy(event))
        if self.on_intent is not None:
            self.on_intent()

    def record_outcome(self, plan_id: str, outcome: str) -> None:
        self.outcomes.append((plan_id, outcome))


def make_harness(kind: str, mode: str = "normal"):
    """Create a plan manager with fully local callbacks and a durable-intent fake."""
    clock = FakeClock()
    if kind == "radio":
        state = {"radioSetting2g": {"channel": "1", "channelWidth": "RADIO_20"}}
        catalog_state = {"radioSetting2g": [
            {"index": 2, "freq": 2437, "available_widths_mhz": [20]}]}
    elif kind == "dns":
        state = {"enable": True, "ttl": 600}
        catalog_state = None
    elif kind == "ssid":
        state = {"ssidEnable": False}
        catalog_state = None
    elif kind == "ipv6":
        state = {"enable": False}
        catalog_state = None
    elif kind == "poe":
        state = {"poe": 0, "supportPoe": True, "profileOverrideEnable": True}
        catalog_state = None
    else:
        raise AssertionError(kind)

    read_count = 0
    catalog_count = 0
    fail_read_on: set[int] = set()
    expire_after_read: set[int] = set()
    writes: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def read(*_args):
        nonlocal read_count
        read_count += 1
        if read_count in fail_read_on:
            raise OSError("private fake read failure")
        if read_count in expire_after_read:
            clock.now += 301
        return copy.deepcopy(state)

    def catalog(*_args):
        nonlocal catalog_count
        catalog_count += 1
        return copy.deepcopy(catalog_state)

    def write(*args):
        body = copy.deepcopy(args[-1])
        writes.append((args, body))
        if kind == "radio":
            for band, values in body.items():
                state[band].update(values)
        elif kind in {"dns", "ssid", "ipv6"}:
            state.clear()
            state.update(body)
        else:
            state["poe"] = body["poeMode"]

    def on_intent():
        if mode == "foreign_change":
            if kind == "radio":
                # Keep the state unchanged and alter the original catalog
                # condition; the complete digest must include both.
                catalog_state["radioSetting2g"][0]["freq"] = 2462
            elif kind == "dns":
                state["ttl"] += 1
            elif kind == "ssid":
                state["ssidEnable"] = True
            elif kind == "ipv6":
                state["enable"] = True
            else:
                state["profileOverrideEnable"] = False
        elif mode == "read_failure":
            fail_read_on.add(read_count + 1)
        elif mode == "ttl":
            expire_after_read.add(read_count + 1)

    journal = FakeJournal(on_intent)
    if kind == "radio":
        manager = RadioChangePlans(read, write, catalog=catalog,
                                   writes_enabled=True, ttl=300, clock=clock,
                                   journal=journal, require_journal=True)
        preview = manager.preview(SITE, DEVICE, {"radioSetting2g": {"channel": 2}})
    elif kind == "dns":
        manager = DnsCacheChangePlans(read, write, writes_enabled=True,
                                      ttl_seconds=300, clock=clock,
                                      journal=journal, require_journal=True)
        preview = manager.preview(SITE, {"ttl": 900})
    elif kind == "ssid":
        manager = SsidChangePlans(read, write, writes_enabled=True,
                                  ttl_seconds=300, clock=clock,
                                  journal=journal, require_journal=True)
        preview = manager.preview(SITE, SSID, {"ssidEnable": True})
    elif kind == "ipv6":
        manager = GatewayIpv6IpPassthroughPlans(read, write, writes_enabled=True,
                                                ttl_seconds=300, clock=clock,
                                                journal=journal, require_journal=True)
        preview = manager.preview(SITE, GATEWAY, {"enable": True})
    else:
        manager = PoeModePlans(read, write, writes_enabled=True, ttl_seconds=300,
                               clock=clock, journal=journal, require_journal=True)
        preview = manager.preview(SITE, SWITCH, PORT, {"poeMode": 1})

    return {"manager": manager, "preview": preview, "journal": journal,
            "writes": writes, "clock": clock, "state": state,
            "catalog": catalog_state, "read_count": lambda: read_count,
            "catalog_count": lambda: catalog_count}


class PresendRecheckGroupATests(unittest.TestCase):
    KINDS = ("radio", "dns", "ssid", "ipv6", "poe")

    def _apply(self, kind: str, manager, plan_id: str):
        return manager.apply(plan_id)

    def test_foreign_change_during_intent_fsync_blocks_write_and_replay_for_all(self) -> None:
        for kind in self.KINDS:
            with self.subTest(manager=kind):
                harness = make_harness(kind, "foreign_change")
                manager, plan, journal, writes = (harness[key] for key in
                                                   ("manager", "preview", "journal", "writes"))
                with self.assertRaises(Exception) as raised:
                    self._apply(kind, manager, plan["plan_id"])
                self.assertIn(str(raised.exception), {"change_in_doubt"})
                self.assertEqual(writes, [])
                self.assertEqual(journal.outcomes, [(plan["plan_id"], "unknown")])
                self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")
                with self.assertRaises(Exception):
                    self._apply(kind, manager, plan["plan_id"])
                self.assertEqual(writes, [])
                if kind == "radio":
                    self.assertGreaterEqual(harness["catalog_count"](), 3)

    def test_post_intent_read_failure_blocks_write_and_records_unknown_for_all(self) -> None:
        for kind in self.KINDS:
            with self.subTest(manager=kind):
                harness = make_harness(kind, "read_failure")
                manager, plan, journal, writes = (harness[key] for key in
                                                   ("manager", "preview", "journal", "writes"))
                with self.assertRaises(Exception) as raised:
                    self._apply(kind, manager, plan["plan_id"])
                self.assertEqual(str(raised.exception), "change_in_doubt")
                self.assertEqual(writes, [])
                self.assertEqual(journal.outcomes, [(plan["plan_id"], "unknown")])
                self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")

    def test_ttl_is_checked_after_post_intent_get_for_all(self) -> None:
        for kind in self.KINDS:
            with self.subTest(manager=kind):
                harness = make_harness(kind, "ttl")
                manager, plan, journal, writes = (harness[key] for key in
                                                   ("manager", "preview", "journal", "writes"))
                with self.assertRaises(Exception) as raised:
                    self._apply(kind, manager, plan["plan_id"])
                self.assertEqual(str(raised.exception), "plan_expired")
                self.assertEqual(writes, [])
                self.assertEqual(journal.outcomes, [(plan["plan_id"], "unknown")])
                self.assertEqual(manager.plans[plan["plan_id"]]["state"], "in_doubt")

    def test_normal_dispatch_reads_again_writes_once_and_replay_is_blocked(self) -> None:
        for kind in self.KINDS:
            with self.subTest(manager=kind):
                harness = make_harness(kind)
                manager, plan, journal, writes = (harness[key] for key in
                                                   ("manager", "preview", "journal", "writes"))
                result = self._apply(kind, manager, plan["plan_id"])
                self.assertEqual(result["status"], "verified")
                self.assertEqual(len(writes), 1)
                self.assertEqual(journal.outcomes, [(plan["plan_id"], "verified_readback")])
                if kind == "radio":
                    self.assertEqual(harness["read_count"](), 4)
                    self.assertEqual(harness["catalog_count"](), 3)
                else:
                    self.assertEqual(harness["read_count"](), 4)
                with self.assertRaises(Exception):
                    self._apply(kind, manager, plan["plan_id"])
                self.assertEqual(len(writes), 1)


if __name__ == "__main__":
    unittest.main()
