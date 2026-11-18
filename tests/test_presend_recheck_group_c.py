from __future__ import annotations

import copy
import unittest

from app.ap_channel_limit_changes import ApChannelLimitPlans, ApChannelLimitChangeError
from app.ap_ofdma_changes import ApOfdmaPlans, ApOfdmaChangeError
from app.ap_afc_changes import ApAfcPlans, ApAfcChangeError
from app.dpi_changes import SiteDpiLoggingPlans, SiteDpiLoggingChangeError
from app.site_lldp_changes import SiteLldpPlans, SiteLldpChangeError


SITE = "a" * 24
DEVICE = "b" * 24


class FakeClock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


class FakeJournal:
    def __init__(self, after_intent=None) -> None:
        self.rows: list[dict[str, object]] = []
        self.events: list[tuple[object, ...]] = []
        self.after_intent = after_intent

    def in_doubt_plans(self) -> list[dict[str, object]]:
        return copy.deepcopy([row for row in self.rows if row["state"] == "in_doubt"])

    def record_dispatch_intent(self, **event: object) -> None:
        row = {**copy.deepcopy(event), "state": "in_doubt"}
        self.rows.append(row)
        self.events.append(("intent", copy.deepcopy(event)))
        if self.after_intent:
            self.after_intent()

    def record_outcome(self, plan_id: str, outcome: str) -> None:
        self.events.append(("outcome", plan_id, outcome))

    def close_unknown(self, plan_id: str, confirmation: str) -> None:
        self.events.append(("close", plan_id, confirmation))


class Harness:
    def __init__(self, kind: str, *, after_intent=None) -> None:
        self.kind = kind
        self.clock = FakeClock()
        self.state = self.initial_state()
        self.read_count = 0
        self.fail_read_count: int | None = None
        self.expire_on_dispatch_read = False
        self.writes: list[dict[str, object]] = []
        self.journal = FakeJournal(after_intent)
        self.manager = self.make_manager()

    def initial_state(self) -> dict[str, object]:
        if self.kind == "site-lldp":
            return {"enable": False}
        if self.kind == "site-dpi":
            return {"dpi": False, "loggingTraffic": False}
        if self.kind == "ap-afc":
            return {"supportAfc": True, "enable": False}
        if self.kind == "ap-channel-limit":
            return {"supportChannelLimit": True, "channelLimitType": 0,
                    "defaultInstType5g": True, "defaultInstType6g": False}
        return {
            "ofdmaEnable2g": True, "ofdmaEnable5g": True,
            "ofdmaEnable5g2": True, "ofdmaEnable6g": True,
            "supportOfdma2g": True, "supportOfdma5g": True,
            "supportOfdma5g2": True, "supportOfdma6g": True,
        }

    @property
    def error_type(self):
        return {
            "site-lldp": SiteLldpChangeError,
            "site-dpi": SiteDpiLoggingChangeError,
            "ap-afc": ApAfcChangeError,
            "ap-channel-limit": ApChannelLimitChangeError,
            "ap-ofdma": ApOfdmaChangeError,
        }[self.kind]

    def read(self, site_ref: str, device_ref: str | None = None):
        self.assert_refs(site_ref, device_ref)
        self.read_count += 1
        if self.read_count == self.fail_read_count:
            raise OSError("private fake controller failure")
        if self.expire_on_dispatch_read and self.read_count == 3:
            self.clock.now = 310.0
        return copy.deepcopy(self.state)

    def assert_refs(self, site_ref: str, device_ref: str | None) -> None:
        if self.kind in {"ap-afc", "ap-channel-limit", "ap-ofdma"}:
            if (site_ref, device_ref) != (SITE, DEVICE):
                raise AssertionError("wrong synthetic reference")
        elif site_ref != SITE or device_ref is not None:
            raise AssertionError("wrong synthetic reference")

    def write(self, site_ref: str, *args):
        device_ref = None
        if self.kind in {"ap-afc", "ap-channel-limit", "ap-ofdma"}:
            device_ref, body = args
        else:
            (body,) = args
        self.assert_refs(site_ref, device_ref)
        self.writes.append(copy.deepcopy(body))
        if self.kind == "ap-afc":
            self.state["enable"] = body["enable"]
        else:
            self.state.update(copy.deepcopy(body))

    def make_manager(self):
        if self.kind == "site-lldp":
            return SiteLldpPlans(self.read, self.write, writes_enabled=True,
                                 clock=self.clock, journal=self.journal,
                                 require_journal=True)
        if self.kind == "site-dpi":
            return SiteDpiLoggingPlans(self.read, self.write, writes_enabled=True,
                                       clock=self.clock, journal=self.journal,
                                       require_journal=True)
        if self.kind == "ap-afc":
            return ApAfcPlans(self.read, self.write, writes_enabled=True,
                              clock=self.clock, journal=self.journal,
                              require_journal=True)
        if self.kind == "ap-channel-limit":
            return ApChannelLimitPlans(self.read, self.write, writes_enabled=True,
                                       clock=self.clock, journal=self.journal,
                                       require_journal=True)
        return ApOfdmaPlans(self.read, self.write, writes_enabled=True,
                            clock=self.clock, journal=self.journal,
                            require_journal=True)

    def preview(self) -> str:
        if self.kind == "site-lldp":
            result = self.manager.preview(SITE, {"enable": True}, disruption_confirmed=True)
        elif self.kind == "site-dpi":
            result = self.manager.preview(SITE, {"dpi": True}, disruption_confirmed=True)
        elif self.kind == "ap-afc":
            result = self.manager.preview(SITE, DEVICE, {"enable": True},
                                          disruption_confirmed=True)
        elif self.kind == "ap-channel-limit":
            result = self.manager.preview(SITE, DEVICE, {"channelLimitType": 1},
                                          disruption_confirmed=True)
        else:
            result = self.manager.preview(SITE, DEVICE, {"ofdmaEnable5g": False},
                                          disruption_confirmed=True)
        return result["plan_id"]

    def change_during_fsync(self) -> None:
        if self.kind == "site-lldp":
            self.state["enable"] = True
        elif self.kind == "site-dpi":
            self.state["loggingTraffic"] = True
        elif self.kind == "ap-afc":
            self.state["enable"] = True
        elif self.kind == "ap-channel-limit":
            self.state["defaultInstType5g"] = False
        else:
            self.state["ofdmaEnable2g"] = False


class PreSendRecheckGroupCTests(unittest.TestCase):
    KINDS = ("site-lldp", "site-dpi", "ap-afc", "ap-channel-limit", "ap-ofdma")

    def test_change_during_fsync_blocks_write_records_unknown_and_cannot_replay(self):
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                harness = Harness(kind)
                harness.journal.after_intent = harness.change_during_fsync
                plan_id = harness.preview()
                with self.assertRaisesRegex(harness.error_type, "change_in_doubt"):
                    harness.manager.apply(plan_id)
                self.assertEqual(harness.writes, [])
                self.assertEqual(harness.journal.events[-1],
                                 ("outcome", plan_id, "unknown"))
                with self.assertRaisesRegex(harness.error_type, "plan_already_consumed"):
                    harness.manager.apply(plan_id)
                recovered = harness.make_manager()
                with self.assertRaisesRegex(harness.error_type, "plan_already_consumed"):
                    recovered.apply(plan_id)
                self.assertEqual(harness.writes, [])

    def test_dispatch_reread_failure_blocks_write_records_unknown_and_cannot_replay(self):
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                harness = Harness(kind)
                plan_id = harness.preview()
                harness.fail_read_count = 3
                with self.assertRaisesRegex(harness.error_type, "change_in_doubt"):
                    harness.manager.apply(plan_id)
                self.assertEqual(harness.writes, [])
                self.assertEqual(harness.journal.events[-1],
                                 ("outcome", plan_id, "unknown"))
                with self.assertRaisesRegex(harness.error_type, "plan_already_consumed"):
                    harness.make_manager().apply(plan_id)

    def test_expiry_during_dispatch_reread_records_unknown_and_blocks_write(self):
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                harness = Harness(kind)
                plan_id = harness.preview()
                harness.expire_on_dispatch_read = True
                with self.assertRaisesRegex(harness.error_type, "plan_expired"):
                    harness.manager.apply(plan_id)
                self.assertEqual(harness.writes, [])
                self.assertEqual(harness.journal.events[-1],
                                 ("outcome", plan_id, "unknown"))
                with self.assertRaisesRegex(harness.error_type, "plan_already_consumed"):
                    harness.make_manager().apply(plan_id)

    def test_unchanged_state_sends_once_then_verifies_full_readback(self):
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                harness = Harness(kind)
                plan_id = harness.preview()
                result = harness.manager.apply(plan_id)
                self.assertEqual(result["status"], "verified")
                self.assertEqual(len(harness.writes), 1)
                self.assertEqual(harness.journal.events[-1],
                                 ("outcome", plan_id, "verified_readback"))
                with self.assertRaisesRegex(harness.error_type, "plan_already_consumed"):
                    harness.manager.apply(plan_id)
                self.assertEqual(len(harness.writes), 1)


if __name__ == "__main__":
    unittest.main()
