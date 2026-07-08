from __future__ import annotations

import argparse
import html
import json
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import quota_monitor as monitor


class AppState:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.last_error = ""
        self.last_log: list[str] = []
        self.next_check_at = 0.0

    def log(self, message: str) -> None:
        with self.lock:
            stamp = datetime.now().strftime("%H:%M:%S")
            self.last_log = (self.last_log + [f"[{stamp}] {message}"])[-80:]

    def set_error(self, message: str) -> None:
        with self.lock:
            self.last_error = message
        self.log(message)

    def load_config(self) -> dict[str, Any]:
        return monitor.load_json(self.config_path, monitor.DEFAULT_CONFIG)

    def save_config(self, config: dict[str, Any]) -> None:
        monitor.save_json(self.config_path, config)

    def state_path(self, config: dict[str, Any]) -> Path:
        path = Path(config.get("state_file", "/data/quota_state.json"))
        if not path.is_absolute():
            path = self.config_path.parent / path
        return path


def as_float(value: str, fallback: float) -> float:
    try:
        return max(0.0, float(value.replace(",", ".")))
    except ValueError:
        return fallback


def as_int(value: str, fallback: int) -> int:
    try:
        return max(1, int(value))
    except ValueError:
        return fallback


def run_check(app: AppState) -> None:
    config = app.load_config()
    state_path = app.state_path(config)
    monitor.run_once(config, state_path)
    state = monitor.load_state(state_path)
    snap = state.get("last_snapshot", {})
    app.log(
        "Check OK: Download "
        f"{float(snap.get('download_gib', 0)):.2f} GiB, Upload "
        f"{float(snap.get('upload_gib', 0)):.2f} GiB"
    )
    with app.lock:
        app.last_error = ""


def monitor_loop(app: AppState) -> None:
    while True:
        try:
            config = app.load_config()
            interval = int(config.get("interval_seconds", 300))
            app.next_check_at = time.time() + interval
            run_check(app)
        except Exception as exc:
            app.set_error(f"Check failed: {exc}")
            interval = 60
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    app: AppState

    def do_GET(self) -> None:
        if self.path == "/check":
            try:
                run_check(self.app)
                self.redirect("/")
            except Exception as exc:
                self.app.set_error(f"Manual check failed: {exc}")
                self.redirect("/")
            return
        if self.path != "/":
            self.send_error(404)
            return
        self.respond_html(self.render())

    def do_POST(self) -> None:
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(raw)
        one = lambda key, default="": form.get(key, [default])[0].strip()

        config = self.app.load_config()
        telegram = config.setdefault("telegram", {})
        telegram["enabled"] = one("telegram_enabled") == "on"
        telegram["bot_token"] = one("bot_token")
        telegram["chat_id"] = one("chat_id")
        config["interval_seconds"] = as_int(one("interval_seconds"), int(config.get("interval_seconds", 300)))
        config["remaining_alert_gib"] = as_float(one("remaining_alert_gib"), float(config.get("remaining_alert_gib", 2.0)))
        config["delta_alert_gib"] = as_float(one("delta_alert_gib"), float(config.get("delta_alert_gib", 3.0)))
        config["increment_alert_gib"] = as_float(one("increment_alert_gib"), float(config.get("increment_alert_gib", 0.0)))
        config["server_refresh_alert_enabled"] = one("server_refresh_alert_enabled") == "on"
        self.app.save_config(config)
        self.app.log("Settings saved")
        self.redirect("/")

    def render(self) -> str:
        config = self.app.load_config()
        state = monitor.load_state(self.app.state_path(config))
        snap = state.get("last_snapshot", {})
        telegram = config.get("telegram", {})
        with self.app.lock:
            logs = "\n".join(self.app.last_log)
            last_error = self.app.last_error
            next_check = max(0, int(self.app.next_check_at - time.time()))

        def val(name: str, default: Any = "") -> str:
            return html.escape(str(config.get(name, default)))

        def checked(flag: bool) -> str:
            return " checked" if flag else ""

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TU-kl Quota Monitor</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; max-width: 920px; }}
    label {{ display: block; margin: 12px 0 4px; font-weight: 600; }}
    input {{ width: 100%; box-sizing: border-box; padding: 8px; }}
    input[type=checkbox] {{ width: auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    .error {{ color: #b00020; }}
    pre {{ background: #111; color: #eee; padding: 12px; overflow: auto; }}
    button, a.button {{ display: inline-block; margin-top: 16px; padding: 9px 14px; }}
  </style>
</head>
<body>
  <h1>TU-kl Quota Monitor</h1>
  <div class="card">
    <b>Current traffic</b>
    <p>Download: {html.escape(str(snap.get("download_gib", "-")))} GiB</p>
    <p>Upload: {html.escape(str(snap.get("upload_gib", "-")))} GiB</p>
    <p>Server updated: {html.escape(str(snap.get("server_updated_at", "-")))}</p>
    <p>Next check: {next_check} seconds</p>
    <p class="error">{html.escape(last_error)}</p>
    <a class="button" href="/check">Run check now</a>
  </div>
  <form method="post" action="/save" class="card">
    <h2>Telegram</h2>
    <label><input type="checkbox" name="telegram_enabled"{checked(bool(telegram.get("enabled")))}> Enable Telegram</label>
    <label>Bot Token</label>
    <input name="bot_token" value="{html.escape(str(telegram.get("bot_token", "")))}">
    <label>Chat ID</label>
    <input name="chat_id" value="{html.escape(str(telegram.get("chat_id", "")))}">
    <h2>Alert settings</h2>
    <div class="grid">
      <div><label>Check interval seconds</label><input name="interval_seconds" value="{val("interval_seconds", 300)}"></div>
      <div><label>Remaining alert GiB</label><input name="remaining_alert_gib" value="{val("remaining_alert_gib", 2.0)}"></div>
      <div><label>Single increase alert GiB</label><input name="delta_alert_gib" value="{val("delta_alert_gib", 3.0)}"></div>
      <div><label>Notify every GiB increase</label><input name="increment_alert_gib" value="{val("increment_alert_gib", 0.0)}"></div>
    </div>
    <label><input type="checkbox" name="server_refresh_alert_enabled"{checked(bool(config.get("server_refresh_alert_enabled")))}> Notify after server data refresh</label>
    <button type="submit">Save</button>
  </form>
  <div class="card">
    <h2>Log</h2>
    <pre>{html.escape(logs)}</pre>
  </div>
</body>
</html>"""

    def respond_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, target: str) -> None:
        self.send_response(303)
        self.send_header("Location", target)
        self.end_headers()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/config/config.json")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    app = AppState(Path(args.config))
    Handler.app = app
    threading.Thread(target=monitor_loop, args=(app,), daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Web UI listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
