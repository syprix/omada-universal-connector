import unittest
from unittest.mock import patch

from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_agile_switch_config_summary import (
    AgileSwitchConfigError, summarize_agile_switch_config,
)


class AgileSwitchGeneralConfigSummaryTests(unittest.TestCase):
    def test_projects_only_documented_led_jumbo_and_power_alert_settings(self):
        result = summarize_agile_switch_config({
            "name": "private switch", "tagIds": ["private-tag"],
            "location": {"address": "private address"}, "remember": True,
            "ledSetting": 2, "jumboEnable": True,
            "supportPowerAlert": True, "powerAlertEnable": False,
        })
        self.assertEqual(result["led_setting"], "site_setting")
        self.assertEqual(result["led_setting_code"], 2)
        self.assertTrue(result["jumbo_frames_enabled"])
        self.assertTrue(result["power_alert_supported"])
        self.assertFalse(result["power_alert_enabled"])
        self.assertNotIn("private", repr(result))

    def test_missing_and_unknown_led_values_are_partial(self):
        self.assertTrue(summarize_agile_switch_config({
            "ledSetting": 8, "jumboEnable": False,
            "supportPowerAlert": False, "powerAlertEnable": False,
        })["partial"])
        self.assertTrue(summarize_agile_switch_config({})["partial"])
        with self.assertRaises(AgileSwitchConfigError):
            summarize_agile_switch_config({"jumboEnable": 1})

    def test_selected_switch_is_freshly_bound_and_agile_checked(self):
        client, site_ref, switch_ref = self._client()
        site_id, switch_mac = "site_internal", "AA-BB-CC-DD-EE-FF"
        detail_path = f"/openapi/v1/ctrl/sites/{site_id}/switches/ports/switch-detail"
        config_path = (f"/openapi/v1/ctrl/sites/{site_id}/switches/es/{switch_mac}/"
                       "general-config")

        def refresh(ref):
            client._switch_macs_by_site_ref[ref] = {switch_ref: switch_mac}
            return {"items": []}

        with patch.object(client, "list_devices", side_effect=refresh), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[
                    {"result": [{"mac": "AA:BB:CC:DD:EE:FF", "es": True}]},
                    {"result": {"name": "private", "ledSetting": 1,
                                "jumboEnable": True, "supportPowerAlert": True,
                                "powerAlertEnable": False}},
                ]) as request:
            result = client.read_site_agile_switch_general_config_summary(site_ref, switch_ref)
        self.assertEqual([call.args[1] for call in request.call_args_list],
                         [detail_path, config_path])
        self.assertEqual(result["led_setting"], "on")
        self.assertNotIn("private", repr(result))
        self.assertTrue(client._site_es_general_config_request_valid(config_path))
        self.assertFalse(client._site_es_general_config_request_valid(
            config_path.replace("/ctrl/", "/other/")))

    def test_rejects_non_agile_missing_and_ambiguous_matches_before_config_read(self):
        client, site_ref, switch_ref = self._client()
        for rows, error in [
            ([{"mac": "AA:BB:CC:DD:EE:FF", "es": False}], "switch_family_unsupported"),
            ([{"mac": "00:11:22:33:44:55", "es": True}], "switch_family_unknown"),
            ([{"mac": "AA:BB:CC:DD:EE:FF", "es": True},
              {"mac": "aa-bb-cc-dd-ee-ff", "es": True}], "switch_family_ambiguous"),
        ]:
            client, site_ref, switch_ref = self._client()
            client._switch_macs_by_site_ref[site_ref] = {switch_ref: "AA-BB-CC-DD-EE-FF"}
            with patch.object(client, "list_devices", return_value={"items": []}), \
                    patch.object(client, "_access_token", return_value="token"), \
                    patch.object(client, "_request_json", return_value={"result": rows}) as request:
                with self.assertRaisesRegex(OpenApiError, error):
                    client.read_site_agile_switch_general_config_summary(site_ref, switch_ref)
            request.assert_called_once()

    @staticmethod
    def _client():
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref, switch_ref = "8" * 24, "9" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        client._switch_macs_by_site_ref[site_ref] = {switch_ref: "AA-BB-CC-DD-EE-FF"}
        return client, site_ref, switch_ref


if __name__ == "__main__":
    unittest.main()
