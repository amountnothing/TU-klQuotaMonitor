"""
Windows traffic quota monitor for https://quota.wohnheim.uni-kl.de

功能：
- 每 5 分钟请求一次网页；
- 从网页文本中提取 Download / Upload 流量；
- 每天下载和上传限额默认各 20 GiB；
- 剩余额度 <= 2 GiB，或 5 分钟内新增流量 >= 3 GiB 时通知；
- 支持 Windows 桌面通知（可选 winotify）和 Telegram Bot 通知。

依赖：
- Python 3.9+
- 可选：pip install winotify

如果网页需要登录 Cookie，可以在 config.json 里填 headers.Cookie。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "url": "https://quota.wohnheim.uni-kl.de",
    "interval_seconds": 300,
    "daily_limit_gib": 20.0,
    "max_plausible_usage_gib": 40.0,
    "remaining_alert_gib": 2.0,
    "delta_alert_gib": 3.0,
    "server_refresh_alert_enabled": False,
    "increment_alert_gib": 0.0,
    "notification_cooldown_seconds": 1800,
    "state_file": "quota_state.json",
    "language": "zh",
    "language_selected": False,
    "auto_start_monitor": False,
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        # 如果网页需要认证，把浏览器里的 Cookie 粘贴到这里：
        # "Cookie": "session=..."
    },
    # The quota site may use a certificate chain that Python cannot verify.
    # Browsers often accept it through local/managed trust, so default to False
    # for this campus-only monitor.
    "verify_ssl": False,
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": ""
    },
    "windows_toast": {
        "enabled": True
    },
    "parsing": {
        # 如果自动解析失败，可以改成网页里真实文字附近的正则。
        # 正则必须包含一个数值捕获组，单位可选捕获。
        # 示例：
        # "download_regex": "Download[^0-9]*([0-9]+(?:[.,][0-9]+)?)\\s*(GiB|GB|MiB|MB)",
        # "upload_regex": "Upload[^0-9]*([0-9]+(?:[.,][0-9]+)?)\\s*(GiB|GB|MiB|MB)"
        "download_regex": "",
        "upload_regex": ""
    }
}


I18N = {
    "zh": {
        "minute": "分钟",
        "notify_title": "Wohnheim 流量额度提醒",
        "remaining_alert": "{direction} 剩余额度仅 {left:.2f} GiB (已用 {used:.2f} / {limit:.2f} GiB)",
        "delta_alert": "{direction} 在 {minutes} 内增加 {delta:.2f} GiB，超过阈值 {threshold:.2f} GiB",
        "download": "Download",
        "upload": "Upload",
        "stale_period": "网页仍显示旧配额周期 {period}，等待当天 {today} 的数据刷新。",
        "invalid_usage": "网页返回异常流量值（Download {download:.2f} GiB, Upload {upload:.2f} GiB），本次检测已忽略。",
    },
    "en": {
        "minute": "minutes",
        "notify_title": "Wohnheim quota alert",
        "remaining_alert": "{direction} has only {left:.2f} GiB left (used {used:.2f} / {limit:.2f} GiB)",
        "delta_alert": "{direction} increased by {delta:.2f} GiB in {minutes}, above the {threshold:.2f} GiB threshold",
        "server_refresh_alert": "Server data refreshed: Download +{download_delta:.2f} GiB, Upload +{upload_delta:.2f} GiB (server time {server_time})",
        "increment_alert": "{direction} increased by {delta:.2f} GiB since the last alert, reaching the every {threshold:.2f} GiB alert setting",
        "download": "Download",
        "upload": "Upload",
        "stale_period": "The page still shows quota period {period}; waiting for today's data ({today}).",
        "invalid_usage": "The page returned implausible usage values (Download {download:.2f} GiB, Upload {upload:.2f} GiB); this check was ignored.",
    },
    "de": {
        "minute": "Minuten",
        "notify_title": "Wohnheim Quota-Warnung",
        "remaining_alert": "{direction}: nur noch {left:.2f} GiB frei ({used:.2f} / {limit:.2f} GiB verbraucht)",
        "delta_alert": "{direction}: +{delta:.2f} GiB in {minutes}, über dem Grenzwert von {threshold:.2f} GiB",
        "download": "Download",
        "upload": "Upload",
        "stale_period": "Die Seite zeigt noch den alten Quota-Zeitraum {period}; die heutigen Daten ({today}) sind noch nicht aktualisiert.",
        "invalid_usage": "Die Seite lieferte unplausible Werte (Download {download:.2f} GiB, Upload {upload:.2f} GiB); diese Pruefung wurde ignoriert.",
    },
}


I18N["zh"].update({
    "server_refresh_alert": "网页数据已刷新：Download +{download_delta:.2f} GiB，Upload +{upload_delta:.2f} GiB（网页时间 {server_time}）",
    "increment_alert": "{direction} 自上次提醒后增加 {delta:.2f} GiB，已达到每 {threshold:.2f} GiB 提醒一次的设置",
})
I18N["de"].update({
    "server_refresh_alert": "Serverdaten aktualisiert: Download +{download_delta:.2f} GiB, Upload +{upload_delta:.2f} GiB (Serverzeit {server_time})",
    "increment_alert": "{direction}: +{delta:.2f} GiB seit der letzten Warnung; Einstellung: alle {threshold:.2f} GiB warnen",
})

def text_for(config: dict[str, Any], key: str) -> str:
    language = str(config.get("language", "zh"))
    return I18N.get(language, I18N["zh"]).get(key, I18N["zh"][key])


def app_dir() -> Path:
    """返回脚本或 exe 所在目录，用于保存同目录状态文件。"""
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            data_dir = Path.home() / "Library" / "Application Support" / "TU-klQuotaMonitor"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class TextExtractor(HTMLParser):
    """把 HTML 变成便于正则匹配的纯文本。"""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass
class QuotaSnapshot:
    download_gib: float
    upload_gib: float
    timestamp: float
    period_start: str | None = None
    period_end: str | None = None
    server_updated_at: str | None = None


class StaleQuotaDataError(ValueError):
    """Raised when the quota page has not refreshed to the current day yet."""


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    return deep_merge(copy.deepcopy(default), loaded)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_page(
    url: str,
    headers: dict[str, str],
    timeout: int = 20,
    verify_ssl: bool = True,
) -> str:
    request = urllib.request.Request(url, headers=headers)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        raw = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
        return raw.decode(encoding, errors="replace")


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", parser.text()).strip()


def unit_to_gib(value: float, unit: str | None) -> float:
    """把网页里的 GB/GiB/MB/MiB/TB/TiB 数值统一转换为 GiB。"""
    normalized = (unit or "GiB").strip().lower()
    if normalized in {"g", "gb", "gib"}:
        return value
    if normalized in {"m", "mb", "mib"}:
        return value / 1024
    if normalized in {"t", "tb", "tib"}:
        return value * 1024
    raise ValueError(f"Unknown unit: {unit}")


def number_from_match(match: re.Match[str]) -> float:
    raw_value = match.group(1).replace(",", ".")
    unit = match.group(2) if match.lastindex and match.lastindex >= 2 else None
    return unit_to_gib(float(raw_value), unit)


def parse_with_custom_regex(text: str, pattern: str) -> float | None:
    if not pattern:
        return None
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return number_from_match(match)


def find_value_near_label(text: str, labels: tuple[str, ...]) -> float | None:
    """
    在 Download/Upload 等标签附近找流量值。
    这里不绑定具体 HTML 结构，便于网页轻微改版后仍可工作。
    """
    value_pattern = r"([0-9]+(?:[.,][0-9]+)?)\s*(TiB|TB|GiB|GB|MiB|MB|T|G|M)?"
    label_pattern = "|".join(re.escape(label) for label in labels)

    # 常见格式：Download: 12.3 GiB
    forward = re.search(
        rf"(?:{label_pattern})[^0-9]{{0,80}}{value_pattern}",
        text,
        re.IGNORECASE,
    )
    if forward:
        return number_from_match(forward)

    # 少数表格会是：12.3 GiB Download
    backward = re.search(
        rf"{value_pattern}[^A-Za-z0-9]{{0,80}}(?:{label_pattern})",
        text,
        re.IGNORECASE,
    )
    if backward:
        return number_from_match(backward)

    return None


def parse_quota_period(text: str) -> tuple[str | None, str | None]:
    """Extract the quota period displayed by the site as ISO dates."""
    match = re.search(
        r"(?:Quotierungszeitraum|Quota\s*period)[^0-9]{0,40}"
        r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    try:
        start = datetime.strptime(match.group(1), "%d.%m.%Y").date().isoformat()
        end = datetime.strptime(match.group(2), "%d.%m.%Y").date().isoformat()
        return start, end
    except ValueError:
        return None, None


def parse_server_updated_at(text: str) -> str | None:
    """Extract the quota page's own data timestamp when it is available."""
    match = re.search(
        r"(?:Stand\s+der\s+Datenbank|Database\s+(?:status|updated))[^0-9]{0,40}"
        r"(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    raw_time = match.group(2)
    if raw_time.count(":") == 1:
        raw_time = f"{raw_time}:00"
    try:
        parsed = datetime.strptime(f"{match.group(1)} {raw_time}", "%d.%m.%Y %H:%M:%S")
        return parsed.isoformat(sep=" ")
    except ValueError:
        return None


def validate_snapshot(snapshot: QuotaSnapshot, config: dict[str, Any]) -> None:
    """Ignore stale day-rollover data and impossible parser results."""
    today = date.today().isoformat()
    if snapshot.period_start and snapshot.period_start != today:
        period = snapshot.period_start
        if snapshot.period_end:
            period = f"{snapshot.period_start} - {snapshot.period_end}"
        raise StaleQuotaDataError(
            text_for(config, "stale_period").format(period=period, today=today)
        )

    limit = float(config.get("daily_limit_gib", 20.0))
    configured_max = float(config.get("max_plausible_usage_gib", limit * 2))
    max_usage = max(limit, configured_max)
    values = (snapshot.download_gib, snapshot.upload_gib)
    if any(value < 0 or value > max_usage for value in values):
        raise StaleQuotaDataError(
            text_for(config, "invalid_usage").format(
                download=snapshot.download_gib,
                upload=snapshot.upload_gib,
            )
        )


def parse_quota(html: str, config: dict[str, Any]) -> QuotaSnapshot:
    text = html_to_text(html)
    parsing = config.get("parsing", {})
    period_start, period_end = parse_quota_period(text)
    server_updated_at = parse_server_updated_at(text)

    download = parse_with_custom_regex(text, parsing.get("download_regex", ""))
    upload = parse_with_custom_regex(text, parsing.get("upload_regex", ""))

    if download is None:
        download = find_value_near_label(
            text,
            ("download", "downloads", "downstream", "down", "received", "empfangen"),
        )
    if upload is None:
        upload = find_value_near_label(
            text,
            ("upload", "uploads", "upstream", "up", "sent", "gesendet"),
        )

    if download is None or upload is None:
        debug_path = app_dir() / "last_quota_page_text.txt"
        debug_path.write_text(text, encoding="utf-8")
        raise ValueError(
            "Could not parse download/upload values. "
            f"Plain page text was saved to {debug_path.resolve()} so you can tune config.json."
        )

    snapshot = QuotaSnapshot(
        download_gib=download,
        upload_gib=upload,
        timestamp=time.time(),
        period_start=period_start,
        period_end=period_end,
        server_updated_at=server_updated_at,
    )
    validate_snapshot(snapshot, config)
    return snapshot


def load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {}
    with state_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def should_notify(state: dict[str, Any], reason_key: str, cooldown: int) -> bool:
    now = time.time()
    last_notifications = state.setdefault("last_notifications", {})
    last_sent = float(last_notifications.get(reason_key, 0))
    if now - last_sent < cooldown:
        return False
    last_notifications[reason_key] = now
    return True


def build_alerts(
    snapshot: QuotaSnapshot,
    previous: dict[str, Any] | None,
    config: dict[str, Any],
    state: dict[str, Any],
) -> list[str]:
    validate_snapshot(snapshot, config)
    limit = float(config["daily_limit_gib"])
    remaining_threshold = float(config["remaining_alert_gib"])
    delta_threshold = float(config["delta_alert_gib"])
    increment_threshold = float(config.get("increment_alert_gib", 0.0))
    cooldown = int(config["notification_cooldown_seconds"])
    alerts: list[str] = []

    remaining = {
        "download": max(0.0, limit - snapshot.download_gib),
        "upload": max(0.0, limit - snapshot.upload_gib),
    }

    for direction, left_gib in remaining.items():
        if left_gib <= remaining_threshold:
            key = f"{today_key()}:{direction}:remaining"
            if should_notify(state, key, cooldown):
                used = snapshot.download_gib if direction == "download" else snapshot.upload_gib
                alerts.append(
                    text_for(config, "remaining_alert").format(
                        direction=text_for(config, direction),
                        left=left_gib,
                        used=used,
                        limit=limit,
                    )
                )

    if previous and previous.get("day") == today_key():
        elapsed = max(1.0, snapshot.timestamp - float(previous.get("timestamp", snapshot.timestamp)))
        interval_note = f"{elapsed / 60:.1f} {text_for(config, 'minute')}"
        deltas = {
            "download": snapshot.download_gib - float(previous.get("download_gib", snapshot.download_gib)),
            "upload": snapshot.upload_gib - float(previous.get("upload_gib", snapshot.upload_gib)),
        }
        positive_deltas = {
            "download": max(0.0, deltas["download"]),
            "upload": max(0.0, deltas["upload"]),
        }

        if (
            config.get("server_refresh_alert_enabled", False)
            and snapshot.server_updated_at
            and previous.get("server_updated_at")
            and snapshot.server_updated_at != previous.get("server_updated_at")
            and any(value > 0 for value in positive_deltas.values())
        ):
            key = f"{today_key()}:server-refresh:{snapshot.server_updated_at}"
            if should_notify(state, key, 0):
                alerts.append(
                    text_for(config, "server_refresh_alert").format(
                        download_delta=positive_deltas["download"],
                        upload_delta=positive_deltas["upload"],
                        server_time=snapshot.server_updated_at,
                    )
                )

        for direction, delta_gib in deltas.items():
            if delta_gib >= delta_threshold:
                key = f"{today_key()}:{direction}:delta"
                if should_notify(state, key, cooldown):
                    alerts.append(
                        text_for(config, "delta_alert").format(
                            direction=text_for(config, direction),
                            minutes=interval_note,
                            delta=delta_gib,
                            threshold=delta_threshold,
                        )
                    )

    if increment_threshold > 0:
        baseline = state.setdefault("increment_alert_baseline", {})
        if baseline.get("day") != today_key():
            baseline.clear()
            baseline["day"] = today_key()
            baseline["download_gib"] = snapshot.download_gib
            baseline["upload_gib"] = snapshot.upload_gib
        else:
            for direction in ("download", "upload"):
                field = f"{direction}_gib"
                current_value = getattr(snapshot, field)
                baseline_value = float(baseline.get(field, current_value))
                delta_since_alert = current_value - baseline_value
                if delta_since_alert >= increment_threshold:
                    alerts.append(
                        text_for(config, "increment_alert").format(
                            direction=text_for(config, direction),
                            delta=delta_since_alert,
                            threshold=increment_threshold,
                        )
                    )
                    baseline[field] = current_value

    return alerts


def notify_windows(title: str, message: str) -> None:
    """
    Use the native notification mechanism for Windows or macOS.
    """
    if sys.platform == "darwin":
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display notification "{safe_message}" with title "{safe_title}"'
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            timeout=10,
        )
        return

    try:
        from winotify import Notification  # type: ignore

        toast = Notification(
            app_id="Wohnheim Quota Monitor",
            title=title,
            msg=message,
            duration="long",
        )
        toast.show()
    except Exception:
        print(f"[WINDOWS NOTIFY FALLBACK] {title}: {message}")
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)
            except Exception:
                pass
        if os.name == "nt":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass


def notify_telegram(title: str, message: str, telegram_config: dict[str, Any]) -> None:
    token = telegram_config.get("bot_token", "")
    chat_id = telegram_config.get("chat_id", "")
    if not token or not chat_id:
        print("[TELEGRAM] bot_token/chat_id not configured; skipped.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": f"{title}\n{message}",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        try:
            import certifi

            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            response.read()
    except urllib.error.URLError:
        if sys.platform != "darwin":
            raise
        notify_telegram_with_macos_curl(url, title, message, chat_id)


def notify_telegram_with_macos_curl(
    url: str,
    title: str,
    message: str,
    chat_id: str,
) -> None:
    """Use macOS curl so Telegram requests honor Keychain trust and proxy settings."""
    result = subprocess.run(
        [
            "/usr/bin/curl",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "20",
            "--request",
            "POST",
            "--data-urlencode",
            f"chat_id={chat_id}",
            "--data-urlencode",
            f"text={title}\n{message}",
            "--data-urlencode",
            "disable_web_page_preview=true",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or f"curl exited with code {result.returncode}"
        raise RuntimeError(f"Telegram request failed: {error}")


def send_notifications(alerts: list[str], config: dict[str, Any]) -> None:
    if not alerts:
        return

    title = text_for(config, "notify_title")
    message = "\n".join(alerts)

    if config.get("windows_toast", {}).get("enabled", True):
        notify_windows(title, message)

    telegram_config = config.get("telegram", {})
    if telegram_config.get("enabled", False):
        notify_telegram(title, message, telegram_config)


def run_once(config: dict[str, Any], state_path: Path) -> None:
    state = load_state(state_path)
    html = fetch_page(
        config["url"],
        config.get("headers", {}),
        verify_ssl=bool(config.get("verify_ssl", True)),
    )
    snapshot = parse_quota(html, config)

    previous = state.get("last_snapshot")
    alerts = build_alerts(snapshot, previous, config, state)
    send_notifications(alerts, config)

    state["last_snapshot"] = {
        "day": today_key(),
        "timestamp": snapshot.timestamp,
        "download_gib": snapshot.download_gib,
        "upload_gib": snapshot.upload_gib,
        "server_updated_at": snapshot.server_updated_at,
    }
    save_json(state_path, state)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[{stamp}] Download {snapshot.download_gib:.2f} GiB, "
        f"Upload {snapshot.upload_gib:.2f} GiB"
    )
    if alerts:
        print("Alert:", " | ".join(alerts))


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Wohnheim traffic quota.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON.")
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    args = parser.parse_args()

    base_dir = app_dir()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = base_dir / config_path

    config = load_json(config_path, DEFAULT_CONFIG)
    state_path = Path(config["state_file"])
    if not state_path.is_absolute():
        state_path = base_dir / state_path
    interval = int(config["interval_seconds"])

    print(f"Using config: {config_path.resolve()}")
    print(f"Checking {config['url']} every {interval} seconds.")

    while True:
        try:
            run_once(config, state_path)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[ERROR] Network error: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)

        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
