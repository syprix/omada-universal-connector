from __future__ import annotations

import unittest
import os
import tempfile
from unittest.mock import patch

from app.change_journal import ChangePlanJournal
from app.changes import ChangeError, RadioChangePlans
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ChannelChangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        os.chmod(self.tempdir.name, 0o700)
        self.journal = ChangePlanJournal(self.tempdir.name, controller_binding="e" * 64)
        self.state = {"radioSetting2g": {"channel": "1", "freq": 2412, "channelWidth": "RADIO_20"}}
        self.catalog_state = {"radioSetting2g": [
            {"index": 1, "channel": 1, "freq": 2412, "available_widths_mhz": [20]},
            {"index": 2, "channel": 6, "freq": 2437, "available_widths_mhz": [20, 40]}]}
        self.writes: list[dict] = []

        def read(_site, _ap):
            return self.state

        def catalog(_site, _ap):
            return self.catalog_state

        def write(_site, _ap, changes):
            self.writes.append(changes)
            self.state = {"radioSetting2g": {**changes["radioSetting2g"], "channelWidth": "RADIO_80"}}

        self.plans = RadioChangePlans(read, write, catalog=catalog, writes_enabled=True,
                                      journal=self.journal, require_journal=True)

    def tearDown(self) -> None:
        self.journal.close()
        self.tempdir.cleanup()

    def test_channel_must_match_catalog_and_apply_rechecks_and_reads_back(self) -> None:
        with self.assertRaisesRegex(ChangeError, "channel_not_supported"):
            self.plans.preview("a" * 24, "b" * 24, {"radioSetting2g": {"channel": 3}})
        preview = self.plans.preview("a" * 24, "b" * 24, {"radioSetting2g": {"channel": 2}})
        self.assertEqual(preview["changes"], {"radioSetting2g": {"channel": "2", "freq": 2437}})
        self.assertEqual(preview["previous"], {"radioSetting2g": {"channel": 1}})
        result = self.plans.apply(preview["plan_id"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.writes, [{"radioSetting2g": {"channel": "2", "freq": 2437}}])
        with self.assertRaisesRegex(ChangeError, "plan_already_consumed"):
            self.plans.apply(preview["plan_id"])

    def test_catalog_or_state_change_invalidates_channel_plan(self) -> None:
        preview = self.plans.preview("a" * 24, "b" * 24, {"radioSetting2g": {"channel": 2}})
        self.catalog_state["radioSetting2g"][1]["freq"] = 2442
        with self.assertRaisesRegex(ChangeError, "state_changed"):
            self.plans.apply(preview["plan_id"])
        self.assertEqual(self.writes, [])
        self.catalog_state["radioSetting2g"][1]["freq"] = 2437
        preview2 = self.plans.preview("a" * 24, "b" * 24, {"radioSetting2g": {"channel": 2}})
        self.state["radioSetting2g"]["channelWidth"] = "RADIO_40"
        with self.assertRaisesRegex(ChangeError, "state_changed"):
            self.plans.apply(preview2["plan_id"])
        self.assertEqual(self.writes, [])

    def test_channel_change_rejects_target_that_cannot_keep_current_width(self) -> None:
        self.state["radioSetting2g"]["channelWidth"] = "RADIO_80"
        with self.assertRaisesRegex(ChangeError, "channel_width_incompatible"):
            self.plans.preview("a" * 24, "b" * 24, {"radioSetting2g": {"channel": 2}})

    def test_documented_auto_zero_is_supported_and_writes_disabled_by_default(self) -> None:
        plans = RadioChangePlans(lambda *_: self.state, lambda *_: self.fail("write called"),
                                 catalog=lambda *_: self.catalog_state)
        preview = plans.preview("a" * 24, "b" * 24, {"radioSetting2g": {"channel": 0}})
        self.assertEqual(preview["changes"], {"radioSetting2g": {"channel": "0"}})
        with self.assertRaisesRegex(ChangeError, "writes_disabled"):
            plans.apply(preview["plan_id"])

    def test_ambiguous_inputs_are_rejected(self) -> None:
        for value in ({"radioSetting2g": {"channel": "36"}},
                      {"radioSetting2g": {"channel": 2, "freq": 2437}},
                      {"radioSetting2g": {"channelWidth": "RADIO_80"}},
                      {"radioSetting2g": {"channel": -1}}):
            with self.subTest(value=value), self.assertRaisesRegex(ChangeError, "changes_invalid"):
                self.plans.preview("a" * 24, "b" * 24, value)

    def test_available_channel_summary_is_site_bound_and_redacted(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        payload = {"result": [{"radioId": 0, "apChannelDetailList": [
            {"channel": 1, "freq": 2412, "index": 1, "availableChannelWidthList": [20, 40]},
            {"channel": 2, "freq": 2437, "index": 2, "availableChannelWidthList": [20],
             "mac": "must-not-escape"}]}]}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload) as request:
            result = client.read_ap_available_channels_summary(site_ref, ap_ref)
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/sites/site_1/aps/AA-BB-CC-DD-EE-FF/available-channel", token="token")
        self.assertEqual(result["data"]["radios"][0]["channels"], [[1, 2412, 1, [20, 40]], [2, 2437, 2, [20]]])
        self.assertTrue(result["partial"])
        self.assertNotIn("AA-BB-CC-DD-EE-FF", repr(result))
        self.assertNotIn("must-not-escape", repr(result))

    def test_5ghz_channel_write_is_closed_due_to_ambiguous_config_field_mapping(self) -> None:
        with self.assertRaisesRegex(ChangeError, "channel_band_unsupported"):
            self.plans.preview("a" * 24, "b" * 24, {"radioSetting5g": {"channel": 1}})

    def test_documented_channel_catalog_is_sanitized_and_patch_is_fixed(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"result": [{"radioId": 0, "apChannelDetailList": [
            {"index": 2, "channel": 6, "freq": 2437, "availableChannelWidthList": [20, 40],
             "private": "must-not-escape"}]}]}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_available_channels(site_ref, ap_ref)
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/sites/site_1/aps/AA-BB-CC-DD-EE-FF/available-channel", token="token")
        self.assertEqual(result["data"], {
            "radios": [{"radio_id": 0, "band": "2.4GHz", "channels": [
                {"channel_index": 2, "channel": 6, "frequency_mhz": 2437,
                 "available_widths_mhz": [20, 40]}]}]})
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json") as patch_request:
            client.patch_ap_radio_config(site_ref, ap_ref,
                {"radioSetting2g": {"channel": "2", "freq": 2437}})
        args, kwargs = patch_request.call_args
        self.assertEqual(args[:2], ("PATCH", "/openapi/v1/ctrl/sites/site_1/aps/AA-BB-CC-DD-EE-FF/radio-config"))
        self.assertEqual(kwargs["body"], b'{"radioSetting2g":{"channel":"2","freq":2437}}')
        with patch.object(client, "_access_token", return_value="token"), \
                self.assertRaisesRegex(OpenApiError, "changes_invalid"):
            client.patch_ap_radio_config(site_ref, ap_ref,
                {"radioSetting2g": {"channel": "2"}})


if __name__ == "__main__":
    unittest.main()
