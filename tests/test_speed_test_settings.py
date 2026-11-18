from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.speed_test_settings import SpeedTestSettingsError, project_speed_test_settings


SITE_REF = "a" * 24


class SpeedTestSettingsProjectionTests(unittest.TestCase):
    def test_projects_schedule_values_and_omits_controller_descriptions(self) -> None:
        result = project_speed_test_settings({
            "autoSpeedTest": True, "timingType": 2, "hour": 4, "minute": 30,
            "dayOfWeek": [1, 3, 5], "resource": 2,
            "featureDescription": [{"name": "private controller label"}],
        })
        self.assertEqual(result["data"], {
            "auto_speed_test": True, "timing_type": 2, "hour": 4,
            "minute": 30, "days_of_week": [1, 3, 5], "resource": 2,
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_fields"], ["featureDescription"])
        self.assertNotIn("private controller label", repr(result))

    def test_projects_daily_and_monthly_schedules(self) -> None:
        daily = project_speed_test_settings({"autoSpeedTest": False, "timingType": 1})
        self.assertFalse(daily["partial"])
        monthly = project_speed_test_settings({
            "autoSpeedTest": True, "timingType": 3, "dayOfMonth": [1, 15, 31]})
        self.assertEqual(monthly["data"]["days_of_month"], [1, 15, 31])
        self.assertFalse(monthly["partial"])

    def test_rejects_invalid_required_conditional_and_bounded_values(self) -> None:
        invalid = (
            None, [],
        )
        malformed = (
            {"autoSpeedTest": 1}, {"autoSpeedTest": True, "timingType": True},
            {"autoSpeedTest": True, "timingType": 4},
            {"autoSpeedTest": True, "hour": 24},
            {"autoSpeedTest": True, "minute": -1},
            {"autoSpeedTest": True, "dayOfWeek": [False]},
            {"autoSpeedTest": True, "dayOfWeek": [7]},
            {"autoSpeedTest": True, "dayOfMonth": [32]},
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(SpeedTestSettingsError):
                project_speed_test_settings(raw)

        for raw in malformed:
            with self.subTest(raw=raw):
                result = project_speed_test_settings(raw)
                self.assertTrue(result["partial"])
                self.assertTrue(result["invalid_fields"])

    def test_variant_missing_required_boolean_is_reported_as_partial(self) -> None:
        result = project_speed_test_settings({})
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_fields"], ["autoSpeedTest"])

    def test_missing_conditionally_required_schedule_fields_are_partial(self) -> None:
        weekly = project_speed_test_settings({"autoSpeedTest": True, "timingType": 2})
        monthly = project_speed_test_settings({"autoSpeedTest": True, "timingType": 3})
        self.assertEqual(weekly["missing_fields"], ["dayOfWeek"])
        self.assertEqual(monthly["missing_fields"], ["dayOfMonth"])
        self.assertTrue(weekly["partial"])
        self.assertTrue(monthly["partial"])

    def test_unknown_fields_are_omitted_and_marked_partial(self) -> None:
        result = project_speed_test_settings({"autoSpeedTest": False, "internal": "secret"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 1)
        self.assertEqual(result["omitted_fields"], ["unknown_fields"])
        self.assertNotIn("secret", repr(result))


class SpeedTestSettingsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_reads_only_the_fixed_site_setting_route(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"autoSpeedTest": False, "timingType": 1}}) as request:
            result = self.client.read_site_speed_test_settings(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/setting/speedTest", token="token")
        self.assertEqual(result["resource"], "speed_test_settings")
        self.assertEqual(result["site_ref"], SITE_REF)

    def test_unknown_site_is_rejected_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_speed_test_settings("b" * 24)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
