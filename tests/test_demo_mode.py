from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from tools import demo_mode, wifi_diagnose


class DemoModeTests(unittest.TestCase):
    def test_existing_wlan_text_report_is_reproducible_and_offline(self) -> None:
        with patch.object(wifi_diagnose, "_request",
                          side_effect=AssertionError("network request attempted")):
            first = demo_mode.run_demo()
            second = demo_mode.run_demo()
        self.assertEqual(first, second)
        self.assertTrue(first.startswith(
            "DEMO — alle Werte sind synthetisch; keine Controller- oder Netzwerkanfrage."))
        self.assertIn("Gesamtzustand: ok", first)
        self.assertIn("WLAN-Kanäle: ok; Kapabilität unbekannt", first)

    def test_cli_requires_no_token_and_prints_only_synthetic_report(self) -> None:
        output = io.StringIO()
        with patch.object(wifi_diagnose, "_request",
                          side_effect=AssertionError("network request attempted")), \
                contextlib.redirect_stdout(output):
            status = demo_mode.main(["--workflow", "wifi-site"])
        self.assertEqual(status, 0)
        self.assertIn("DEMO — alle Werte sind synthetisch", output.getvalue())
        self.assertNotIn("Bearer", output.getvalue())
        self.assertNotIn("api_key", output.getvalue())


if __name__ == "__main__":
    unittest.main()
