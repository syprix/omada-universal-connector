import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_port_schedule_summary import (
    SitePortScheduleError, project_site_port_schedule_summary,
)


class SitePortScheduleSummaryTests(unittest.TestCase):
    def test_redacts_rows_and_counts_schedule_and_supported_port_memberships(self):
        schedules = {"totalRows": 2, "currentPage": 1, "currentSize": 2, "data": [
            {"id": "private-id", "name": "private-name", "status": True,
             "turnOnTime": "private-time-range", "nextExecute": 123456,
             "notInDst": True, "portsMap": {"aa:bb": [1, 3], "cc:dd": [4]}},
            {"id": "private-id-2", "name": "private-name-2", "status": False,
             "turnOnTime": "private-time-range-2", "portsMap": {}},
        ]}
        ports = [
            {"type": "switch", "mac": "aa:bb", "name": "private-device",
             "ports": {"portNum": 5, "portIds": [1, 2]}},
            {"type": "gateway", "mac": "cc:dd", "ports": {"portNum": 4, "portIds": [4]}},
        ]
        result = project_site_port_schedule_summary(schedules, ports, 0, 10)
        self.assertEqual(result["enabled_schedule_count"], 1)
        self.assertEqual(result["disabled_schedule_count"], 1)
        self.assertEqual(result["schedule_port_membership_count"], 3)
        self.assertEqual(result["membership_on_documented_supported_ports"], 2)
        self.assertEqual(result["membership_not_listed_as_supported"], 1)
        self.assertTrue(result["partial"])
        for private in ("private-id", "private-name", "private-time-range", "aa:bb", "private-device"):
            self.assertNotIn(private, repr(result))

    def test_marks_missing_or_duplicate_device_bindings_partial(self):
        schedules = {"totalRows": 1, "currentPage": 1, "currentSize": 1, "data": [{
            "status": True, "turnOnTime": "range", "portsMap": {"aa:bb": [1]}}]}
        ports = [{"mac": "aa:bb", "ports": {"portNum": 2, "portIds": [1]}},
                 {"mac": "aa:bb", "ports": {"portNum": 2, "portIds": [1]}}]
        result = project_site_port_schedule_summary(schedules, ports, 0, 1)
        self.assertEqual(result["ambiguous_device_reference_count"], 1)
        self.assertTrue(result["partial"])

    def test_rejects_wrong_page_shapes(self):
        with self.assertRaises(SitePortScheduleError):
            project_site_port_schedule_summary(
                {"totalRows": 1, "currentPage": 2, "currentSize": 1, "data": [{}]},
                [], 0, 100)

    def test_client_requests_one_page_and_the_same_site_supported_port_list(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        schedule = {"totalRows": 0, "currentPage": 2, "currentSize": 0, "data": []}
        with patch.object(client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[
                    {"result": schedule}, {"result": []}]) as request:
            result = client.read_site_port_schedule_summary("a" * 24, 1, 10)
        self.assertEqual(result["reported_schedule_count"], 0)
        self.assertEqual(request.call_count, 2)
        self.assertIn("/port-schedules?page=2&pageSize=10", request.call_args_list[0].args[1])
        self.assertTrue(client._site_port_schedule_ports_request_valid(
            request.call_args_list[1].args[1]))


if __name__ == "__main__":
    unittest.main()
