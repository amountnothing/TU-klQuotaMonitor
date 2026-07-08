import copy
import unittest
import urllib.error
from datetime import date, timedelta
from unittest import mock

import quota_monitor as monitor


class QuotaMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = copy.deepcopy(monitor.DEFAULT_CONFIG)

    def test_current_quota_period_is_accepted(self) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        html = (
            f"Quotierungszeitraum: {today:%d.%m.%Y} - {tomorrow:%d.%m.%Y} "
            "Download: 959 MiB 20 GiB Upload: 577 MiB 20 GiB"
        )

        snapshot = monitor.parse_quota(html, self.config)

        self.assertAlmostEqual(snapshot.download_gib, 959 / 1024)
        self.assertAlmostEqual(snapshot.upload_gib, 577 / 1024)
        self.assertEqual(snapshot.period_start, today.isoformat())

    def test_previous_quota_period_is_ignored(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        html = (
            f"Quotierungszeitraum: {yesterday:%d.%m.%Y} - {today:%d.%m.%Y} "
            "Download: 19 GiB 20 GiB Upload: 18 GiB 20 GiB"
        )

        with self.assertRaises(monitor.StaleQuotaDataError):
            monitor.parse_quota(html, self.config)

    def test_implausible_usage_is_ignored(self) -> None:
        html = "Download: 357 GiB 20 GiB Upload: 381 GiB 20 GiB"

        with self.assertRaises(monitor.StaleQuotaDataError):
            monitor.parse_quota(html, self.config)

    def test_invalid_snapshot_cannot_create_negative_remaining_alert(self) -> None:
        snapshot = monitor.QuotaSnapshot(357.0, 381.0, 0)

        with self.assertRaises(monitor.StaleQuotaDataError):
            monitor.build_alerts(snapshot, None, self.config, {})

    def test_remaining_quota_is_never_negative(self) -> None:
        snapshot = monitor.QuotaSnapshot(25.0, 21.0, 0)

        alerts = monitor.build_alerts(snapshot, None, self.config, {})

        self.assertEqual(len(alerts), 2)
        self.assertTrue(all("0.00 GiB" in alert for alert in alerts))
        self.assertTrue(all("-" not in alert for alert in alerts))

    def test_macos_telegram_falls_back_to_system_curl(self) -> None:
        telegram = {
            "bot_token": "test-token",
            "chat_id": "123456",
        }
        certificate_error = urllib.error.URLError("certificate verify failed")

        with (
            mock.patch.object(monitor.sys, "platform", "darwin"),
            mock.patch.object(monitor.urllib.request, "urlopen", side_effect=certificate_error),
            mock.patch.object(monitor, "notify_telegram_with_macos_curl") as curl_fallback,
        ):
            monitor.notify_telegram("Title", "Message", telegram)

        curl_fallback.assert_called_once_with(
            "https://api.telegram.org/bottest-token/sendMessage",
            "Title",
            "Message",
            "123456",
        )

    def test_server_updated_at_is_parsed(self) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        html = (
            f"Quotierungszeitraum: {today:%d.%m.%Y} - {tomorrow:%d.%m.%Y} "
            f"Stand der Datenbank: {today:%d.%m.%Y} 00:50:00 "
            "Download: 1 GiB 20 GiB Upload: 2 GiB 20 GiB"
        )

        snapshot = monitor.parse_quota(html, self.config)

        self.assertEqual(snapshot.server_updated_at, f"{today:%Y-%m-%d} 00:50:00")

    def test_server_refresh_alert_reports_positive_delta(self) -> None:
        self.config["server_refresh_alert_enabled"] = True
        previous = {
            "day": monitor.today_key(),
            "timestamp": 0,
            "download_gib": 1.0,
            "upload_gib": 1.0,
            "server_updated_at": "2026-06-26 00:50:00",
        }
        snapshot = monitor.QuotaSnapshot(1.5, 1.1, 300, server_updated_at="2026-06-26 00:55:00")

        alerts = monitor.build_alerts(snapshot, previous, self.config, {})

        self.assertTrue(any("+0.50 GiB" in alert and "+0.10 GiB" in alert for alert in alerts))

    def test_increment_alert_uses_last_alert_baseline(self) -> None:
        self.config["increment_alert_gib"] = 1.0
        state = {
            "increment_alert_baseline": {
                "day": monitor.today_key(),
                "download_gib": 0.0,
                "upload_gib": 0.0,
            }
        }
        snapshot = monitor.QuotaSnapshot(1.25, 0.5, 300)

        alerts = monitor.build_alerts(snapshot, None, self.config, state)

        self.assertEqual(len(alerts), 1)
        self.assertIn("1.25 GiB", alerts[0])
        self.assertEqual(state["increment_alert_baseline"]["download_gib"], 1.25)
        self.assertEqual(state["increment_alert_baseline"]["upload_gib"], 0.0)


if __name__ == "__main__":
    unittest.main()
