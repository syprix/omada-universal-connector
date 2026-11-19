from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.change_journal import (
    ChangeJournalError,
    ChangePlanJournal,
    derive_controller_binding,
)


SITE = "a" * 24
DEVICE = "b" * 24
SSID = "c" * 24
GATEWAY = "d" * 24
SWITCH = "e" * 24
BINDING = "f" * 64
TAG_ROWS = [{"classType": i, "enable": i != 2, "dscp": str((i + 1) * 8)} for i in range(4)]


def plan(operation: str, plan_id: str) -> dict[str, object]:
    plans: dict[str, dict[str, object]] = {
        "radio": {
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"radioSetting2g": {"txPowerLevel": 1}},
            "target": {"radioSetting2g": {"txPowerLevel": 2}},
        },
        "dns-cache": {
            "target_refs": {"site_ref": SITE},
            "before": {"enable": False, "ttl": 600},
            "target": {"enable": False, "ttl": 900},
        },
        "ssid": {
            "target_refs": {"site_ref": SITE, "ssid_ref": SSID},
            "before": {"ssidEnable": False},
            "target": {"ssidEnable": True},
        },
        "gateway-ipv6": {
            "target_refs": {"site_ref": SITE, "gateway_ref": GATEWAY},
            "before": {"enable": False},
            "target": {"enable": True},
        },
        "poe": {
            "target_refs": {"site_ref": SITE, "switch_ref": SWITCH, "port": 7},
            "before": {"poeMode": 0},
            "target": {"poeMode": 1},
        },
        "switch-port-status": {
            "target_refs": {"site_ref": SITE, "switch_ref": SWITCH, "port": 7},
            "before": {"status": 1},
            "target": {"status": 0},
        },
        "switch-port-name": {
            "target_refs": {"site_ref": SITE, "switch_ref": SWITCH, "port": 7},
            "before": {"name_redacted": True},
            "target": {"name_redacted": True},
        },
        "site-dpi": {
            "target_refs": {"site_ref": SITE},
            "before": {"dpi": False, "loggingTraffic": False},
            "target": {"dpi": True, "loggingTraffic": False},
        },
        "gateway-voip": {
            "target_refs": {"site_ref": SITE},
            "before": {"enable": False, "sipUdpPort": 5060},
            "target": {"enable": True, "sipUdpPort": 5060},
        },
        "gateway-tag-qos": {
            "target_refs": {"site_ref": SITE},
            "before": {"tagConfigList": [dict(row) for row in TAG_ROWS]},
            "target": {"tagConfigList": [dict(row, enable=(True if row["classType"] == 2 else row["enable"])) for row in TAG_ROWS]},
        },
        "band-steering": {
            "target_refs": {"site_ref": SITE},
            "before": {"mode": 1},
            "target": {"mode": 2},
        },
        "rrm-mode": {
            "target_refs": {"site_ref": SITE},
            "before": {"mode": 0, "timeRangeEnable": False, "resource": 1,
                       "timeRangeId": "", "timeRangeAction": 0},
            "target": {"mode": 1, "timeRangeEnable": False, "resource": 1,
                       "timeRangeId": "", "timeRangeAction": 0},
        },
        "site-led": {
            "target_refs": {"site_ref": SITE},
            "before": {"enable": False},
            "target": {"enable": True},
        },
        "ap-afc": {
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"enable": False},
            "target": {"enable": True},
        },
        "site-lldp": {
            "target_refs": {"site_ref": SITE},
            "before": {"enable": False},
            "target": {"enable": True},
        },
        "ap-channel-limit": {
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"channelLimitType": 1},
            "target": {"channelLimitType": 2},
        },
        "ap-ofdma": {
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"ofdmaEnable5g": False},
            "target": {"ofdmaEnable5g": True},
        },
        "ap-qos": {
            "target_refs": {"site_ref": SITE, "device_ref": DEVICE},
            "before": {"support2g": True, "support5g": True, "support5g2": False,
                       "support6g": False, "deliveryEnable2g": True,
                       "deliveryEnable5g": True},
            "target": {"support2g": True, "support5g": True, "support5g2": False,
                       "support6g": False, "deliveryEnable2g": False,
                       "deliveryEnable5g": True},
        },
    }
    result = {"operation": operation, "plan_id": plan_id, **plans[operation]}
    return result


def dispatch(journal: ChangePlanJournal, operation: str, plan_id: str) -> None:
    item = plan(operation, plan_id)
    journal.record_dispatch_intent(**item)


class ChangePlanJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def open_journal(self) -> ChangePlanJournal:
        return ChangePlanJournal(self.tempdir.name, controller_binding=BINDING)

    def test_summary_reports_only_bounded_status_counts(self) -> None:
        with self.open_journal() as journal:
            dispatch(journal, "radio", "1" * 48)
            dispatch(journal, "dns-cache", "2" * 48)
            journal.record_outcome("2" * 48, "verified_readback")
            dispatch(journal, "ssid", "3" * 48)
            journal.close_unknown("3" * 48, "outcome_unknown_no_retry")
            summary = journal.summary()

        self.assertEqual(summary, {
            "status": "ok", "resource": "change_journal_summary",
            "integrity": "validated_at_open", "total_plans": 3,
            "counts_by_state": {"in_doubt": 1, "verified": 1,
                                "closed_outcome_unknown": 1},
            "record_details_included": False,
        })
        self.assertNotIn("plan_id", json.dumps(summary))
        self.assertNotIn("target_refs", json.dumps(summary))

    def test_all_schemas_recover_as_unresolved_without_execution(self) -> None:
        with self.open_journal() as journal:
            for index, operation in enumerate(
                    ("radio", "dns-cache", "ssid", "gateway-ipv6", "poe",
                     "switch-port-status", "band-steering", "rrm-mode", "site-led", "ap-afc",
                     "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "switch-port-name",
                     "site-dpi", "gateway-voip", "gateway-tag-qos"), start=1):
                dispatch(journal, operation, f"{index:048x}")
            recovered = journal.in_doubt_plans()

        self.assertEqual(len(recovered), 18)
        self.assertEqual({item["operation"] for item in recovered},
                         {"radio", "dns-cache", "ssid", "gateway-ipv6", "poe",
                          "switch-port-status", "band-steering", "rrm-mode", "site-led", "ap-afc",
                          "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "switch-port-name",
                          "site-dpi", "gateway-voip", "gateway-tag-qos"})
        self.assertTrue(all(item["state"] == "in_doubt" for item in recovered))
        self.assertNotIn("write", ChangePlanJournal.__dict__)
        with self.open_journal() as reopened:
            self.assertEqual(len(reopened.in_doubt_plans()), 18)

    def test_switch_port_name_journal_persists_only_redaction_markers(self) -> None:
        plan_id = "8" * 48
        with self.open_journal() as journal:
            dispatch(journal, "switch-port-name", plan_id)
            rows = journal.in_doubt_plans()
            self.assertEqual(rows[0]["before"], {"name_redacted": True})
            self.assertEqual(rows[0]["target"], {"name_redacted": True})

        data = (Path(self.tempdir.name) / "change-plans.jsonl").read_bytes()
        self.assertIn(b"name_redacted", data)
        self.assertNotIn(b"Old-Uplink", data)
        self.assertNotIn(b"New-Uplink", data)
        self.assertNotIn(b"name_sha256", data)
        self.assertNotIn(b"name_hmac", data)

        for unsafe in ({"name": "Old-Uplink"},
                       {"name_sha256": "a" * 64},
                       {"name_hmac": "a" * 64},
                       {"name_redacted": 1}, {}):
            with self.subTest(state=unsafe), self.open_journal() as journal:
                bad = plan("switch-port-name", "9" * 48)
                bad["before"] = unsafe
                with self.assertRaisesRegex(ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(**bad)

    def test_site_dpi_journal_accepts_only_full_two_bool_state_and_one_delta(self) -> None:
        plan_id = "7" * 48
        valid = plan("site-dpi", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            invalid_states = (
                ({"dpi": False}, {"dpi": True}),
                ({"dpi": False, "loggingTraffic": False, "extra": False},
                 {"dpi": True, "loggingTraffic": False}),
                ({"dpi": False, "loggingTraffic": False},
                 {"dpi": 1, "loggingTraffic": False}),
                ({"dpi": False, "loggingTraffic": False},
                 {"dpi": True, "loggingTraffic": True}),
                ({"dpi": False, "loggingTraffic": False},
                 {"dpi": False, "loggingTraffic": False}),
            )
            for index, (before, target) in enumerate(invalid_states, start=1):
                bad = plan("site-dpi", f"{index:048x}")
                bad["before"], bad["target"] = before, target
                with self.subTest(before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(**bad)

        with self.open_journal() as reopened:
            rows = reopened.in_doubt_plans()
        self.assertEqual(rows[0]["operation"], "site-dpi")
        self.assertEqual(rows[0]["target_refs"], {"site_ref": SITE})
        self.assertEqual(rows[0]["before"], {"dpi": False, "loggingTraffic": False})
        self.assertEqual(rows[0]["target"], {"dpi": True, "loggingTraffic": False})

    def test_gateway_voip_journal_binds_full_bool_port_and_site(self) -> None:
        valid = plan("gateway-voip", "6" * 48)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            invalid_states = (
                ({"enable": False}, {"enable": True, "sipUdpPort": 5060}),
                ({"enable": False, "sipUdpPort": 5060},
                 {"enable": True, "sipUdpPort": 5061}),
                ({"enable": False, "sipUdpPort": 5060},
                 {"enable": False, "sipUdpPort": 5060}),
                ({"enable": False, "sipUdpPort": True},
                 {"enable": True, "sipUdpPort": True}),
                ({"enable": False, "sipUdpPort": 0},
                 {"enable": True, "sipUdpPort": 65536}),
                ({"enable": False, "sipUdpPort": 5060, "extra": 1},
                 {"enable": True, "sipUdpPort": 5060}),
            )
            for index, (before, target) in enumerate(invalid_states, start=1):
                bad = plan("gateway-voip", f"{index:048x}")
                bad["before"], bad["target"] = before, target
                with self.subTest(before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(**bad)
            bad = plan("gateway-voip", "f" * 48)
            bad["target_refs"] = {"site_ref": SITE, "gateway_ref": GATEWAY}
            with self.assertRaisesRegex(ChangeJournalError, "journal_schema_invalid"):
                journal.record_dispatch_intent(**bad)

        with self.open_journal() as reopened:
            row = reopened.in_doubt_plans()[0]
        self.assertEqual(row["operation"], "gateway-voip")
        self.assertEqual(row["target_refs"], {"site_ref": SITE})
        self.assertEqual(row["before"], {"enable": False, "sipUdpPort": 5060})
        self.assertEqual(row["target"], {"enable": True, "sipUdpPort": 5060})

    def test_gateway_tag_qos_journal_binds_full_ordered_scalars(self) -> None:
        valid = plan("gateway-tag-qos", "7" * 48)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            invalid = []
            reordered = plan("gateway-tag-qos", "8" * 48)
            reordered["target"]["tagConfigList"].reverse()
            invalid.append(reordered)
            changed_dscp = plan("gateway-tag-qos", "9" * 48)
            changed_dscp["target"]["tagConfigList"][0]["dscp"] = "08"
            invalid.append(changed_dscp)
            changed_class = plan("gateway-tag-qos", "a" * 48)
            changed_class["target"]["tagConfigList"][0]["classType"] = 1
            invalid.append(changed_class)
            extra = plan("gateway-tag-qos", "b" * 48)
            extra["target"]["tagConfigList"][0]["secret"] = "private"
            invalid.append(extra)
            for bad in invalid:
                with self.subTest(plan_id=bad["plan_id"]), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(**bad)
        with self.open_journal() as reopened:
            row = reopened.in_doubt_plans()[0]
        self.assertEqual(row["operation"], "gateway-tag-qos")
        self.assertEqual(row["target_refs"], {"site_ref": SITE})
        self.assertEqual(row["before"]["tagConfigList"], TAG_ROWS)

    def test_verified_unknown_and_closed_transitions_reopen_conservatively(self) -> None:
        with self.open_journal() as journal:
            dispatch(journal, "poe", "1" * 48)
            journal.record_outcome("1" * 48, "verified_readback")
            dispatch(journal, "ssid", "2" * 48)
            journal.record_outcome("2" * 48, "unknown")
            dispatch(journal, "gateway-ipv6", "3" * 48)
            journal.close_unknown("3" * 48, "outcome_unknown_no_retry")
            self.assertEqual(journal.plan_state("1" * 48), "verified")
            self.assertEqual(journal.plan_state("2" * 48), "in_doubt")
            self.assertEqual(journal.plan_state("3" * 48), "closed_outcome_unknown")

        with self.open_journal() as reopened:
            open_plans = reopened.in_doubt_plans()
            self.assertEqual([item["plan_id"] for item in open_plans], ["2" * 48])
            self.assertEqual(reopened.plan_state("1" * 48), "verified")
            self.assertEqual(reopened.plan_state("3" * 48), "closed_outcome_unknown")
            with self.assertRaisesRegex(ChangeJournalError, "plan_transition_invalid"):
                reopened.record_outcome("2" * 48, "verified_readback")
            with self.assertRaisesRegex(ChangeJournalError, "plan_transition_invalid"):
                reopened.record_outcome("1" * 48, "unknown")

    def test_unknown_outcome_can_only_be_closed_with_exact_confirmation(self) -> None:
        plan_id = "4" * 48
        with self.open_journal() as journal:
            dispatch(journal, "dns-cache", plan_id)
            journal.record_outcome(plan_id, "unknown")
            with self.assertRaisesRegex(ChangeJournalError, "operator_confirmation_required"):
                journal.close_unknown(plan_id, "close")
            self.assertEqual(journal.plan_state(plan_id), "in_doubt")
            journal.close_unknown(plan_id, "outcome_unknown_no_retry")
            self.assertEqual(journal.plan_state(plan_id), "closed_outcome_unknown")

    def test_invalid_schema_and_secrets_are_rejected_before_append(self) -> None:
        plan_id = "5" * 48
        with self.open_journal() as journal:
            for operation, changes in (
                ("poe", {"token": "private-secret"}),
                ("poe", {"url": "https://controller.example"}),
                ("poe", {"mac": "AA-BB-CC-DD-EE-FF"}),
            ):
                invalid = plan(operation, plan_id)
                invalid["target_refs"] = {**invalid["target_refs"], **changes}
                with self.subTest(field=next(iter(changes))), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(**invalid)
            bad_radio = plan("radio", plan_id)
            bad_radio["target"] = {"radioSetting2g": {"txPowerLevel": 2, "secret": "x"}}
            with self.assertRaisesRegex(ChangeJournalError, "journal_schema_invalid"):
                journal.record_dispatch_intent(**bad_radio)

        data = (Path(self.tempdir.name) / "change-plans.jsonl").read_bytes()
        self.assertEqual(data, b"")
        self.assertNotIn(b"private-secret", data)
        self.assertNotIn(b"controller.example", data)

    def test_radio_channel_schema_accepts_only_canonical_supported_shapes(self) -> None:
        plan_id = "6" * 48
        valid_targets = (
            {"radioSetting2g": {"channel": "0"}},
            {"radioSetting6g": {"channel": "5", "freq": 5975}},
        )
        valid_before = (
            {"radioSetting2g": {"channel": 6}},
            {"radioSetting6g": {"channel": 1}},
        )
        with self.open_journal() as journal:
            for index, (before, target) in enumerate(zip(valid_before, valid_targets)):
                actual_id = f"{index + 7:048x}"
                journal.record_dispatch_intent(
                    operation="radio", plan_id=actual_id,
                    target_refs={"site_ref": SITE, "device_ref": DEVICE},
                    before=before, target=target)
            for bad_target in (
                {"radioSetting2g": {"channel": "00"}},
                {"radioSetting2g": {"channel": "05", "freq": 5975}},
                {"radioSetting2g": {"channel": "\u0665", "freq": 5975}},
                {"radioSetting2g": {"channel": "5", "freq": 5975.5}},
                {"radioSetting2g": {"channel": "5", "freq": 5975, "url": "x"}},
            ):
                with self.subTest(target=bad_target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(
                        operation="radio", plan_id=plan_id,
                        target_refs={"site_ref": SITE, "device_ref": DEVICE},
                        before={"radioSetting2g": {"channel": 6}}, target=bad_target)

    def test_switch_port_status_requires_exact_refs_and_binary_integer_states(self) -> None:
        plan_id = "9" * 48
        valid = plan("switch-port-status", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            invalid_cases = []
            invalid = plan("switch-port-status", plan_id)
            invalid["target_refs"] = {"site_ref": SITE, "switch_ref": SWITCH,
                                       "port": 7, "device_ref": DEVICE}
            invalid_cases.append(invalid)
            for bad_port in (True, -1, 4097, "7"):
                invalid = plan("switch-port-status", plan_id)
                invalid["target_refs"] = {"site_ref": SITE, "switch_ref": SWITCH,
                                           "port": bad_port}
                invalid_cases.append(invalid)
            for field_state in (
                    {"status": True}, {"status": 2}, {"status": 0.0},
                    {"status": 0, "extra": 1}, {},
            ):
                invalid = plan("switch-port-status", plan_id)
                invalid["before"] = field_state
                invalid_cases.append(invalid)
                invalid = plan("switch-port-status", plan_id)
                invalid["target"] = field_state
                invalid_cases.append(invalid)
            for invalid in invalid_cases:
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(**invalid)

            unknown = plan("switch-port-status", plan_id)
            unknown["operation"] = "switch-port-status-extra"
            with self.assertRaisesRegex(ChangeJournalError, "journal_schema_invalid"):
                journal.record_dispatch_intent(**unknown)

        with self.open_journal() as reopened:
            rows = reopened.in_doubt_plans()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["operation"], "switch-port-status")
            self.assertEqual(rows[0]["target_refs"], {"site_ref": SITE,
                                                        "switch_ref": SWITCH, "port": 7})

    def test_band_steering_requires_site_ref_and_mode_0_1_or_2(self) -> None:
        plan_id = "a" * 48
        valid = plan("band-steering", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            for refs, before, target in (
                ({"site_ref": SITE, "ssid_ref": SSID}, {"mode": 1}, {"mode": 2}),
                ({"site_ref": "bad"}, {"mode": 1}, {"mode": 2}),
                ({"site_ref": SITE}, {"mode": True}, {"mode": 2}),
                ({"site_ref": SITE}, {"mode": 1}, {"mode": False}),
                ({"site_ref": SITE}, {"mode": 3}, {"mode": 2}),
                ({"site_ref": SITE}, {"mode": 1, "extra": 0}, {"mode": 2}),
            ):
                with self.subTest(refs=refs, before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="band-steering", plan_id=plan_id,
                                                   target_refs=refs, before=before, target=target)

    def test_rrm_mode_requires_exact_values_and_only_mode_may_change(self) -> None:
        plan_id = "c" * 48
        valid = plan("rrm-mode", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            for field, bad in (("mode", True), ("mode", 2), ("timeRangeEnable", 0),
                               ("resource", True), ("resource", 3),
                               ("timeRangeId", "1"), ("timeRangeAction", False),
                               ("timeRangeAction", 2)):
                before = dict(valid["before"])
                target = dict(valid["target"])
                target[field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="rrm-mode", plan_id=plan_id,
                                                   target_refs={"site_ref": SITE},
                                                   before=before, target=target)
                before[field] = bad
                with self.subTest(before_field=field, bad=bad), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="rrm-mode", plan_id=plan_id,
                                                   target_refs={"site_ref": SITE},
                                                   before=before, target=valid["target"])
            extra = dict(valid["target"])
            extra["extra"] = 1
            with self.assertRaisesRegex(ChangeJournalError, "journal_schema_invalid"):
                journal.record_dispatch_intent(operation="rrm-mode", plan_id=plan_id,
                                               target_refs=valid["target_refs"],
                                               before=valid["before"], target=extra)
            for refs in ({"site_ref": SITE, "extra": "x"}, {"site_ref": "bad"}):
                with self.subTest(refs=refs), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="rrm-mode", plan_id=plan_id,
                                                   target_refs=refs, before=valid["before"],
                                                   target=valid["target"])
            target = dict(valid["target"])
            target["resource"] = 2
            with self.assertRaisesRegex(ChangeJournalError, "journal_schema_invalid"):
                journal.record_dispatch_intent(operation="rrm-mode", plan_id=plan_id,
                                               target_refs=valid["target_refs"],
                                               before=valid["before"], target=target)

    def test_site_led_requires_exact_site_and_boolean_states(self) -> None:
        plan_id = "d" * 48
        valid = plan("site-led", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            for refs, before, target in (
                ({"site_ref": SITE, "device_ref": DEVICE}, {"enable": False}, {"enable": True}),
                ({"site_ref": "invalid"}, {"enable": False}, {"enable": True}),
                ({"site_ref": SITE}, {"enable": 0}, {"enable": True}),
                ({"site_ref": SITE}, {"enable": False}, {"enable": 1}),
                ({"site_ref": SITE}, {"enable": False, "extra": 1}, {"enable": True}),
                ({"site_ref": SITE}, {"enable": False}, {"enable": True, "extra": 1}),
            ):
                with self.subTest(refs=refs, before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="site-led", plan_id=plan_id,
                                                   target_refs=refs, before=before, target=target)

    def test_ap_afc_journal_requires_exact_site_device_and_boolean_states(self) -> None:
        plan_id = "e" * 48
        valid = plan("ap-afc", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            cases = (
                ({"site_ref": SITE}, {"enable": False}, {"enable": True}),
                ({"site_ref": SITE, "device_ref": "bad"}, {"enable": False}, {"enable": True}),
                ({"site_ref": SITE, "device_ref": DEVICE, "extra": "x"}, {"enable": False}, {"enable": True}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"enable": 0}, {"enable": True}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"enable": False}, {"enable": 1}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"enable": False, "extra": True}, {"enable": True}),
            )
            for refs, before, target in cases:
                with self.subTest(refs=refs, before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="ap-afc", plan_id=plan_id,
                                                   target_refs=refs, before=before, target=target)

    def test_site_lldp_journal_requires_exact_site_and_boolean_states(self) -> None:
        plan_id = "f" * 48
        valid = plan("site-lldp", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            for refs, before, target in (
                ({"site_ref": SITE, "switch_ref": SWITCH}, {"enable": False}, {"enable": True}),
                ({"site_ref": "invalid"}, {"enable": False}, {"enable": True}),
                ({"site_ref": SITE}, {"enable": 0}, {"enable": True}),
                ({"site_ref": SITE}, {"enable": False}, {"enable": 1}),
                ({"site_ref": SITE}, {"enable": False, "extra": True}, {"enable": True}),
                ({"site_ref": SITE}, {"enable": False}, {"enable": True, "extra": True}),
            ):
                with self.subTest(refs=refs, before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="site-lldp", plan_id=plan_id,
                                                   target_refs=refs, before=before, target=target)

    def test_ap_channel_limit_journal_requires_exact_refs_and_integer_range(self) -> None:
        plan_id = "0" * 48
        valid = plan("ap-channel-limit", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            for refs, before, target in (
                ({"site_ref": SITE}, {"channelLimitType": 1}, {"channelLimitType": 2}),
                ({"site_ref": SITE, "device_ref": "bad"}, {"channelLimitType": 1}, {"channelLimitType": 2}),
                ({"site_ref": SITE, "device_ref": DEVICE, "extra": True}, {"channelLimitType": 1}, {"channelLimitType": 2}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"channelLimitType": True}, {"channelLimitType": 2}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"channelLimitType": 1}, {"channelLimitType": False}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"channelLimitType": 3}, {"channelLimitType": 2}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"channelLimitType": 1}, {"channelLimitType": -1}),
            ):
                with self.subTest(refs=refs, before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="ap-channel-limit", plan_id=plan_id,
                                                   target_refs=refs, before=before, target=target)

    def test_ap_ofdma_journal_records_only_one_matching_boolean_field(self) -> None:
        plan_id = "9" * 48
        valid = plan("ap-ofdma", plan_id)
        with self.open_journal() as journal:
            journal.record_dispatch_intent(**valid)
            recovered = journal.in_doubt_plans()
            self.assertEqual(recovered[-1]["before"], {"ofdmaEnable5g": False})
            self.assertEqual(recovered[-1]["target"], {"ofdmaEnable5g": True})
            cases = (
                ({"site_ref": SITE}, {"ofdmaEnable5g": False}, {"ofdmaEnable5g": True}),
                ({"site_ref": SITE, "device_ref": "bad"}, {"ofdmaEnable5g": False}, {"ofdmaEnable5g": True}),
                ({"site_ref": SITE, "device_ref": DEVICE, "mac": "aa"}, {"ofdmaEnable5g": False}, {"ofdmaEnable5g": True}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"ofdmaEnable5g": 0}, {"ofdmaEnable5g": True}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"ofdmaEnable5g": False}, {"ofdmaEnable5g": 1}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"ofdmaEnable5g": False, "extra": False}, {"ofdmaEnable5g": True, "extra": True}),
                ({"site_ref": SITE, "device_ref": DEVICE}, {"ofdmaEnable5g": False}, {"ofdmaEnable2g": True}),
            )
            for refs, before, target in cases:
                with self.subTest(refs=refs, before=before, target=target), self.assertRaisesRegex(
                        ChangeJournalError, "journal_schema_invalid"):
                    journal.record_dispatch_intent(operation="ap-ofdma", plan_id=plan_id,
                                                   target_refs=refs, before=before, target=target)

    def test_truncated_or_hash_tampered_journal_fails_closed(self) -> None:
        with self.open_journal() as journal:
            dispatch(journal, "poe", "7" * 48)
        path = Path(self.tempdir.name) / "change-plans.jsonl"
        data = path.read_bytes()
        path.write_bytes(data[:-1])
        with self.assertRaisesRegex(ChangeJournalError, "journal_corrupt"):
            self.open_journal()
        path.write_bytes(data)
        event = json.loads(data)
        event["previous_hash"] = "1" * 64
        path.write_bytes(json.dumps(event, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        with self.assertRaisesRegex(ChangeJournalError, "journal_corrupt"):
            self.open_journal()

    def test_controller_binding_is_required_and_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ChangeJournalError, "journal_binding_invalid"):
            ChangePlanJournal(self.tempdir.name, controller_binding="not-a-digest")
        with self.open_journal() as journal:
            dispatch(journal, "poe", "a" * 48)
        with self.assertRaisesRegex(ChangeJournalError, "journal_binding_mismatch"):
            ChangePlanJournal(self.tempdir.name, controller_binding="0" * 64)

    def test_controller_binding_is_an_hmac_of_stable_reference_key_and_target(self) -> None:
        key = b"k" * 32
        first = derive_controller_binding(key, "https://controller.example", "ctrl")
        same = derive_controller_binding(key, "https://CONTROLLER.EXAMPLE:443/", "ctrl")
        different_key = derive_controller_binding(b"z" * 32, "https://controller.example", "ctrl")
        different_target = derive_controller_binding(key, "https://other.example", "ctrl")
        self.assertEqual(first, same)
        self.assertNotEqual(first, different_key)
        self.assertNotEqual(first, different_target)
        self.assertNotIn("controller.example", first)
        for bad_key, bad_url in ((b"short", "https://controller.example"),
                                  (key, "http://controller.example"),
                                  (key, "https://controller.example:0")):
            with self.subTest(url=bad_url), self.assertRaisesRegex(
                    ChangeJournalError, "journal_binding_invalid"):
                derive_controller_binding(bad_key, bad_url, "ctrl")

    def test_hmac_binding_does_not_persist_key_or_controller_url(self) -> None:
        key = b"r" * 32
        controller_url = "https://private-controller.example:8443"
        binding = derive_controller_binding(key, controller_url, "private-controller-id")
        with ChangePlanJournal(self.tempdir.name, controller_binding=binding) as journal:
            dispatch(journal, "poe", "d" * 48)
        data = (Path(self.tempdir.name) / "change-plans.jsonl").read_bytes()
        self.assertNotIn(key, data)
        self.assertNotIn(key.hex().encode(), data)
        self.assertNotIn(controller_url.encode(), data)
        self.assertNotIn(b"private-controller-id", data)

    def test_directory_fsync_failure_prevents_usable_journal(self) -> None:
        with patch("app.change_journal.os.fsync", side_effect=OSError("directory sync failure")):
            with self.assertRaisesRegex(ChangeJournalError, "journal_directory_sync_failed"):
                self.open_journal()
        # A later open re-syncs the directory before it can accept dispatches.
        with self.open_journal() as journal:
            self.assertEqual(journal.in_doubt_plans(), [])

    def test_fsync_and_write_errors_poison_instance_and_do_not_return_success(self) -> None:
        with self.open_journal() as journal:
            with patch("app.change_journal.os.fsync", side_effect=OSError("disk failure")):
                with self.assertRaisesRegex(ChangeJournalError, "journal_write_failed"):
                    dispatch(journal, "ssid", "8" * 48)
            with self.assertRaisesRegex(ChangeJournalError, "journal_unavailable"):
                journal.in_doubt_plans()

        with self.open_journal() as journal:
            with patch("app.change_journal.os.write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(ChangeJournalError, "journal_write_failed"):
                    dispatch(journal, "ssid", "9" * 48)
            with self.assertRaisesRegex(ChangeJournalError, "journal_unavailable"):
                journal.in_doubt_plans()

    def test_partial_write_failure_leaves_truncated_journal_that_cannot_reopen(self) -> None:
        with self.open_journal() as journal:
            real_write = os.write
            calls = {"count": 0}

            def partial_then_fail(fd: int, data: bytes | memoryview) -> int:
                calls["count"] += 1
                if calls["count"] == 1:
                    return real_write(fd, data[:16])
                raise OSError("injected partial record failure")

            with patch("app.change_journal.os.write", side_effect=partial_then_fail):
                with self.assertRaisesRegex(ChangeJournalError, "journal_write_failed"):
                    dispatch(journal, "poe", "a" * 48)
        data = (Path(self.tempdir.name) / "change-plans.jsonl").read_bytes()
        self.assertGreater(len(data), 0)
        self.assertFalse(data.endswith(b"\n"))
        with self.assertRaisesRegex(ChangeJournalError, "journal_corrupt"):
            self.open_journal()

    def test_file_and_record_size_limits_fail_closed(self) -> None:
        with patch("app.change_journal._MAX_RECORD_BYTES", 10):
            with self.open_journal() as journal:
                with self.assertRaisesRegex(ChangeJournalError, "journal_record_too_large"):
                    dispatch(journal, "poe", "a" * 48)
        with patch("app.change_journal._MAX_FILE_BYTES", 1):
            with self.open_journal() as journal:
                with self.assertRaisesRegex(ChangeJournalError, "journal_full"):
                    dispatch(journal, "poe", "b" * 48)

    def test_private_modes_and_no_follow_are_required(self) -> None:
        data_path = Path(self.tempdir.name) / "change-plans.jsonl"
        data_path.write_text("", encoding="ascii")
        data_path.chmod(0o644)
        with self.assertRaisesRegex(ChangeJournalError, "journal_permissions_invalid"):
            self.open_journal()
        data_path.unlink()

        os.chmod(self.tempdir.name, 0o755)
        try:
            with self.assertRaisesRegex(ChangeJournalError, "journal_permissions_invalid"):
                self.open_journal()
        finally:
            os.chmod(self.tempdir.name, 0o700)

        outside = Path(self.tempdir.name).parent / (Path(self.tempdir.name).name + "-target")
        outside.write_text("", encoding="ascii")
        try:
            data_path.symlink_to(outside)
            with self.assertRaises(ChangeJournalError):
                self.open_journal()
        finally:
            data_path.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_fifo_and_hardlinked_journal_files_are_rejected(self) -> None:
        data_path = Path(self.tempdir.name) / "change-plans.jsonl"
        os.mkfifo(data_path, 0o600)
        with self.assertRaisesRegex(ChangeJournalError, "journal_permissions_invalid"):
            self.open_journal()
        data_path.unlink()

        source_path = Path(self.tempdir.name) / "source-records"
        source_path.write_bytes(b"")
        source_path.chmod(0o600)
        os.link(source_path, data_path)
        with self.assertRaisesRegex(ChangeJournalError, "journal_permissions_invalid"):
            self.open_journal()

    def test_second_process_cannot_open_exclusively_locked_journal(self) -> None:
        with self.open_journal():
            code = """\
import sys
from app.change_journal import ChangePlanJournal, ChangeJournalError
try:
    ChangePlanJournal(sys.argv[1], controller_binding=sys.argv[2])
except ChangeJournalError as exc:
    print(exc.code)
    sys.exit(0 if exc.code == 'journal_locked' else 2)
sys.exit(3)
"""
            result = subprocess.run(
                [sys.executable, "-c", code, self.tempdir.name, BINDING],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "journal_locked")

    def test_sequence_hash_chain_and_full_jsonl_records(self) -> None:
        with self.open_journal() as journal:
            dispatch(journal, "gateway-ipv6", "c" * 48)
            journal.record_outcome("c" * 48, "verified_readback")
        events = [json.loads(line) for line in
                  (Path(self.tempdir.name) / "change-plans.jsonl").read_text().splitlines()]
        self.assertEqual([event["sequence"] for event in events], [1, 2])
        self.assertEqual(events[0]["previous_hash"], "0" * 64)
        self.assertEqual(events[1]["previous_hash"], events[0]["record_hash"])
        self.assertTrue(all(event["schema_version"] == 1 for event in events))
        self.assertTrue(all(event["record_hash"] for event in events))


if __name__ == "__main__":
    unittest.main()
