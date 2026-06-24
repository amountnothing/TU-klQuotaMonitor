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


if __name__ == "__main__":
    unittest.main()
