import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteActiveDeviceSummaryIntegrationTests(unittest.TestCase):
    def test_both_fixed_routes_share_the_trailing_day_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(client, "_request_json", return_value={"result": [
                    {"status": 0, "name": "private-device", "traffic": 3.25}
                ]}) as req:
            datetime_mock.now.return_value = fixed_now
            ap_result = client.read_site_active_ap_summary(site_ref)
            switch_result = client.read_site_active_switch_summary(site_ref)
        self.assertEqual(req.call_count, 2)
        self.assertEqual(req.call_args_list[0].args[1],
            "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/most-active-eaps?start=1999913600&end=2000000000")
        self.assertEqual(req.call_args_list[1].args[1],
            "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/most-active-switches?start=1999913600&end=2000000000")
        self.assertEqual(ap_result["data"]["total_traffic_value"], 3.25)
        self.assertEqual(switch_result["data"]["total_traffic_value"], 3.25)
        self.assertNotIn("private-device", repr(ap_result) + repr(switch_result))

    def test_route_guards_reject_wrong_controller_and_window(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        for checker, suffix in (
            (client._site_active_ap_request_valid, "most-active-eaps"),
            (client._site_active_switch_request_valid, "most-active-switches"),
        ):
            good = f"/openapi/v1/ctrl/sites/site/dashboard/{suffix}?start=10&end=86410"
            self.assertTrue(checker(good))
            self.assertFalse(checker(good.replace("/ctrl/", "/other/")))
            self.assertFalse(checker(good.replace("end=86410", "end=86411")))


if __name__ == "__main__":
    unittest.main()
