"""
GUI wrapper for the Wohnheim quota monitor.

This file keeps the network/parser logic in quota_monitor.py and provides a
small Windows-friendly front end with a background monitoring thread.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
import urllib.error
import locale
import plistlib
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import quota_monitor as monitor

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pystray = None
    Image = None
    ImageDraw = None


APP_TITLE = "Wohnheim Quota Monitor"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "WohnheimQuotaMonitor"
MACOS_LAUNCH_AGENT = "com.amountnothing.tuklquotamonitor.plist"

LANGUAGE_OPTIONS = {
    "简体中文": "zh",
    "English": "en",
    "Deutsch": "de",
}

LANGUAGE_NAMES = {value: key for key, value in LANGUAGE_OPTIONS.items()}

FIRST_RUN_TEXT = {
    "zh": {
        "title": "选择语言",
        "message": "请选择界面语言。之后也可以在主界面右上角修改。",
        "continue": "继续",
    },
    "en": {
        "title": "Choose Language",
        "message": "Please choose the interface language. You can change it later in the top right corner.",
        "continue": "Continue",
    },
    "de": {
        "title": "Sprache waehlen",
        "message": "Bitte waehle die Sprache der Oberflaeche. Du kannst sie spaeter oben rechts aendern.",
        "continue": "Weiter",
    },
}

UI_TEXT = {
    "zh": {
        "start": "开始检测",
        "stop": "停止检测",
        "idle": "未开始",
        "running": "运行中：正在后台检测",
        "stopped": "已停止",
        "success": "运行中：检测成功",
        "failed": "检测失败",
        "traffic": "当前流量",
        "last_check": "上次检测",
        "remaining": "剩余额度",
        "next_check": "下次检测",
        "telegram_enabled": "启用 Telegram 通知",
        "save": "保存",
        "test_telegram": "测试 Telegram",
        "background": "后台运行",
        "startup": "开机自启并自动开始检测",
        "log": "运行日志",
        "hint": "关闭窗口时可选择最小化到系统托盘，后台检测会继续运行。",
        "language": "语言",
        "seconds_later": "{seconds} 秒后",
        "config_saved": "配置已保存。",
        "started": "监控已启动。",
        "stopped_log": "监控已停止。",
        "network_error": "网络错误：{error}",
        "check_ok": "检测成功：Download {download:.2f} GiB, Upload {upload:.2f} GiB",
        "alert": "提醒：{alert}",
        "telegram_test": "Telegram 通知测试成功。",
        "telegram_sent": "Telegram 测试消息已发送。",
        "telegram_failed": "Telegram 测试失败：{error}",
        "startup_failed": "开机自启设置失败：{error}",
        "close_prompt": "是否最小化到系统托盘？\n\n选择“是”：隐藏窗口，后台继续检测。\n选择“否”：退出程序。",
        "tray_warning": "当前环境无法创建托盘图标，窗口将保持打开。",
        "tray_hidden": "窗口已最小化到系统托盘。",
        "tray_restored": "窗口已从系统托盘恢复。",
        "tray_show": "显示窗口",
        "tray_exit": "退出程序",
    },
    "en": {
        "start": "Start",
        "stop": "Stop",
        "idle": "Not started",
        "running": "Running: checking in background",
        "stopped": "Stopped",
        "success": "Running: last check succeeded",
        "failed": "Check failed",
        "traffic": "Current traffic",
        "last_check": "Last check",
        "remaining": "Remaining quota",
        "next_check": "Next check",
        "telegram_enabled": "Enable Telegram notifications",
        "save": "Save",
        "test_telegram": "Test Telegram",
        "background": "Background",
        "startup": "Start at login and begin checking",
        "log": "Log",
        "hint": "Closing the window can minimize the app to the system tray; checking continues in the background.",
        "language": "Language",
        "seconds_later": "in {seconds} seconds",
        "config_saved": "Settings saved.",
        "started": "Monitoring started.",
        "stopped_log": "Monitoring stopped.",
        "network_error": "Network error: {error}",
        "check_ok": "Check succeeded: Download {download:.2f} GiB, Upload {upload:.2f} GiB",
        "alert": "Alert: {alert}",
        "telegram_test": "Telegram test notification succeeded.",
        "telegram_sent": "Telegram test message sent.",
        "telegram_failed": "Telegram test failed: {error}",
        "startup_failed": "Startup setting failed: {error}",
        "close_prompt": "Minimize to the system tray?\n\nYes: hide the window and keep checking.\nNo: exit the app.",
        "tray_warning": "System tray icon is unavailable in this environment, so the window will stay open.",
        "tray_hidden": "Window minimized to the system tray.",
        "tray_restored": "Window restored from the system tray.",
        "tray_show": "Show window",
        "tray_exit": "Exit",
    },
    "de": {
        "start": "Starten",
        "stop": "Stoppen",
        "idle": "Nicht gestartet",
        "running": "Laeuft: Pruefung im Hintergrund",
        "stopped": "Gestoppt",
        "success": "Laeuft: letzte Pruefung erfolgreich",
        "failed": "Pruefung fehlgeschlagen",
        "traffic": "Aktueller Traffic",
        "last_check": "Letzte Pruefung",
        "remaining": "Restquota",
        "next_check": "Naechste Pruefung",
        "telegram_enabled": "Telegram-Benachrichtigungen aktivieren",
        "save": "Speichern",
        "test_telegram": "Telegram testen",
        "background": "Hintergrund",
        "startup": "Bei der Anmeldung starten und automatisch pruefen",
        "log": "Protokoll",
        "hint": "Beim Schliessen kann die App in den Infobereich minimiert werden; die Pruefung laeuft weiter.",
        "language": "Sprache",
        "seconds_later": "in {seconds} Sekunden",
        "config_saved": "Einstellungen gespeichert.",
        "started": "Ueberwachung gestartet.",
        "stopped_log": "Ueberwachung gestoppt.",
        "network_error": "Netzwerkfehler: {error}",
        "check_ok": "Pruefung erfolgreich: Download {download:.2f} GiB, Upload {upload:.2f} GiB",
        "alert": "Warnung: {alert}",
        "telegram_test": "Telegram-Testbenachrichtigung erfolgreich.",
        "telegram_sent": "Telegram-Testnachricht gesendet.",
        "telegram_failed": "Telegram-Test fehlgeschlagen: {error}",
        "startup_failed": "Autostart-Einstellung fehlgeschlagen: {error}",
        "close_prompt": "In den Infobereich minimieren?\n\nJa: Fenster ausblenden und weiter pruefen.\nNein: App beenden.",
        "tray_warning": "Das Tray-Symbol ist in dieser Umgebung nicht verfuegbar; das Fenster bleibt offen.",
        "tray_hidden": "Fenster in den Infobereich minimiert.",
        "tray_restored": "Fenster aus dem Infobereich wiederhergestellt.",
        "tray_show": "Fenster anzeigen",
        "tray_exit": "Beenden",
    },
}


UI_TEXT["zh"].update({
    "alerts": "提醒设置",
    "server_refresh_alert": "网页数据刷新后通知本次增加量",
    "remaining_alert_gib": "剩余 <= GiB",
    "delta_alert_gib": "单次增加 >= GiB",
    "increment_alert_gib": "每增加 GiB 通知",
})
UI_TEXT["en"].update({
    "alerts": "Alert settings",
    "server_refresh_alert": "Notify increase after server data refresh",
    "remaining_alert_gib": "Remaining <= GiB",
    "delta_alert_gib": "Single increase >= GiB",
    "increment_alert_gib": "Notify every GiB increase",
})
UI_TEXT["de"].update({
    "alerts": "Warn-Einstellungen",
    "server_refresh_alert": "Nach Serverdaten-Update Zuwachs melden",
    "remaining_alert_gib": "Rest <= GiB",
    "delta_alert_gib": "Einmaliger Zuwachs >= GiB",
    "increment_alert_gib": "Warnen alle GiB Zuwachs",
})

def detect_system_language() -> str:
    try:
        language = (locale.getlocale()[0] or "").lower()
    except Exception:
        language = ""
    if not language:
        try:
            language = (locale.getdefaultlocale()[0] or "").lower()
        except Exception:
            language = ""
    if language.startswith("zh"):
        return "zh"
    if language.startswith("de"):
        return "de"
    return "en"


class QuotaMonitorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("620x650")
        self.root.minsize(580, 620)

        self.base_dir = monitor.app_dir()
        self.config_path = self.base_dir / "config.json"
        self.needs_language_choice = self._needs_language_choice()
        self.config = monitor.load_json(self.config_path, monitor.DEFAULT_CONFIG)
        self.state_path = self._state_path()

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.tray_icon: Any | None = None
        self.is_hidden_to_tray = False

        language = self.initial_language()
        if language not in LANGUAGE_NAMES:
            language = "zh"
        self.config["language"] = language
        self.language_var = tk.StringVar(value=LANGUAGE_NAMES[language])
        self.running_var = tk.BooleanVar(value=False)
        self.telegram_enabled_var = tk.BooleanVar(
            value=bool(self.config.get("telegram", {}).get("enabled", False))
        )
        self.bot_token_var = tk.StringVar(
            value=str(self.config.get("telegram", {}).get("bot_token", ""))
        )
        self.chat_id_var = tk.StringVar(
            value=str(self.config.get("telegram", {}).get("chat_id", ""))
        )
        self.status_var = tk.StringVar(value="")
        self.last_check_var = tk.StringVar(value="-")
        self.download_var = tk.StringVar(value="-")
        self.upload_var = tk.StringVar(value="-")
        self.remaining_var = tk.StringVar(value="-")
        self.next_check_var = tk.StringVar(value="-")
        self.startup_enabled_var = tk.BooleanVar(value=self.is_startup_enabled())
        self.server_refresh_alert_var = tk.BooleanVar(
            value=bool(self.config.get("server_refresh_alert_enabled", False))
        )
        self.remaining_alert_var = tk.StringVar(
            value=str(self.config.get("remaining_alert_gib", 2.0))
        )
        self.delta_alert_var = tk.StringVar(
            value=str(self.config.get("delta_alert_gib", 3.0))
        )
        self.increment_alert_var = tk.StringVar(
            value=str(self.config.get("increment_alert_gib", 0.0))
        )
        self.metric_labels: dict[str, ttk.Label] = {}
        self.widgets: dict[str, Any] = {}

        self._build_ui()
        self.apply_language()
        if self.needs_language_choice:
            self.root.after(100, self.show_first_run_language_dialog)
        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _needs_language_choice(self) -> bool:
        if not self.config_path.exists():
            return True
        try:
            loaded = monitor.load_json(self.config_path, monitor.DEFAULT_CONFIG)
            return not bool(loaded.get("language_selected", False))
        except Exception:
            return True

    def initial_language(self) -> str:
        if self.needs_language_choice:
            return detect_system_language()
        return str(self.config.get("language", "zh"))

    def _state_path(self) -> Path:
        state_path = Path(self.config.get("state_file", "quota_state.json"))
        if not state_path.is_absolute():
            state_path = self.base_dir / state_path
        return state_path

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        main = ttk.Frame(self.root, padding=16)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        language_box = ttk.Frame(header)
        language_box.grid(row=0, column=1, sticky="e", padx=(8, 10))
        self.widgets["language_label"] = ttk.Label(language_box)
        self.widgets["language_label"].grid(row=0, column=0, sticky="e", padx=(0, 6))
        language_combo = ttk.Combobox(
            language_box,
            textvariable=self.language_var,
            values=list(LANGUAGE_OPTIONS.keys()),
            width=12,
            state="readonly",
        )
        language_combo.grid(row=0, column=1, sticky="e")
        language_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_language_changed())

        self.toggle_button = ttk.Button(header, command=self.toggle_monitor)
        self.toggle_button.grid(row=0, column=2, sticky="e")

        status = ttk.Label(main, textvariable=self.status_var, foreground="#1f6f43")
        status.grid(row=1, column=0, sticky="w", pady=(6, 14))

        metrics = ttk.LabelFrame(main)
        self.widgets["traffic_frame"] = metrics
        metrics.grid(row=2, column=0, sticky="ew")
        metrics.columnconfigure(1, weight=1)

        self._metric(metrics, 0, "last_check", self.last_check_var)
        self._metric(metrics, 1, "Download", self.download_var, literal=True)
        self._metric(metrics, 2, "Upload", self.upload_var, literal=True)
        self._metric(metrics, 3, "remaining", self.remaining_var)
        self._metric(metrics, 4, "next_check", self.next_check_var)

        telegram = ttk.LabelFrame(main, text="Telegram Bot")
        self.widgets["telegram_frame"] = telegram
        telegram.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        telegram.columnconfigure(1, weight=1)

        enabled = ttk.Checkbutton(
            telegram,
            variable=self.telegram_enabled_var,
            command=self.save_config,
        )
        self.widgets["telegram_enabled"] = enabled
        enabled.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6))

        ttk.Label(telegram, text="Bot Token").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        token_entry = ttk.Entry(telegram, textvariable=self.bot_token_var, show="*")
        token_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=6)

        ttk.Label(telegram, text="Chat ID").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        chat_entry = ttk.Entry(telegram, textvariable=self.chat_id_var)
        chat_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=6)

        buttons = ttk.Frame(telegram)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", padx=10, pady=(6, 10))
        self.widgets["save_button"] = ttk.Button(buttons, command=self.save_config)
        self.widgets["save_button"].grid(row=0, column=0, padx=(0, 8))
        self.widgets["test_button"] = ttk.Button(buttons, command=self.test_telegram)
        self.widgets["test_button"].grid(row=0, column=1)

        alerts = ttk.LabelFrame(main)
        self.widgets["alerts_frame"] = alerts
        alerts.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        alerts.columnconfigure(1, weight=1)
        alerts.columnconfigure(3, weight=1)

        server_refresh = ttk.Checkbutton(
            alerts,
            variable=self.server_refresh_alert_var,
            command=self.save_config,
        )
        self.widgets["server_refresh_alert"] = server_refresh
        server_refresh.grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 6))

        self.widgets["remaining_alert_label"] = ttk.Label(alerts)
        self.widgets["remaining_alert_label"].grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(alerts, textvariable=self.remaining_alert_var, width=10).grid(
            row=1, column=1, sticky="w", padx=10, pady=6
        )

        self.widgets["delta_alert_label"] = ttk.Label(alerts)
        self.widgets["delta_alert_label"].grid(row=1, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(alerts, textvariable=self.delta_alert_var, width=10).grid(
            row=1, column=3, sticky="w", padx=10, pady=6
        )

        self.widgets["increment_alert_label"] = ttk.Label(alerts)
        self.widgets["increment_alert_label"].grid(row=2, column=0, sticky="w", padx=10, pady=(6, 10))
        ttk.Entry(alerts, textvariable=self.increment_alert_var, width=10).grid(
            row=2, column=1, sticky="w", padx=10, pady=(6, 10)
        )

        startup = ttk.LabelFrame(main)
        self.widgets["startup_frame"] = startup
        startup.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        startup.columnconfigure(0, weight=1)

        startup_check = ttk.Checkbutton(
            startup,
            variable=self.startup_enabled_var,
            command=self.save_config,
        )
        self.widgets["startup_check"] = startup_check
        startup_check.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        log_frame = ttk.LabelFrame(main)
        self.widgets["log_frame"] = log_frame
        log_frame.grid(row=6, column=0, sticky="nsew", pady=(14, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main.rowconfigure(6, weight=1)

        self.log_text = tk.Text(log_frame, height=6, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        hint = ttk.Label(
            main,
            foreground="#666666",
        )
        self.widgets["hint"] = hint
        hint.grid(row=7, column=0, sticky="w", pady=(8, 0))

    def _metric(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        var: tk.StringVar,
        literal: bool = False,
    ) -> None:
        label_widget = ttk.Label(parent, text=label if literal else "")
        label_widget.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        if not literal:
            self.metric_labels[label] = label_widget
        ttk.Label(parent, textvariable=var).grid(row=row, column=1, sticky="w", padx=10, pady=5)

    def language_code(self) -> str:
        return LANGUAGE_OPTIONS.get(self.language_var.get(), "zh")

    def t(self, key: str) -> str:
        language = self.language_code()
        return UI_TEXT.get(language, UI_TEXT["zh"]).get(key, UI_TEXT["zh"][key])

    def on_language_changed(self) -> None:
        self.config["language"] = self.language_code()
        self.apply_language()
        self.save_config(show_message=False)

    def show_first_run_language_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(FIRST_RUN_TEXT[self.language_code()]["title"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        message_var = tk.StringVar(value=FIRST_RUN_TEXT[self.language_code()]["message"])
        title_var = tk.StringVar(value=FIRST_RUN_TEXT[self.language_code()]["title"])
        continue_var = tk.StringVar(value=FIRST_RUN_TEXT[self.language_code()]["continue"])
        choice_var = tk.StringVar(value=self.language_var.get())

        ttk.Label(frame, textvariable=title_var, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(frame, textvariable=message_var, wraplength=360).grid(
            row=1, column=0, sticky="w", pady=(8, 14)
        )
        combo = ttk.Combobox(
            frame,
            textvariable=choice_var,
            values=list(LANGUAGE_OPTIONS.keys()),
            width=20,
            state="readonly",
        )
        combo.grid(row=2, column=0, sticky="ew")

        def refresh_dialog_text() -> None:
            code = LANGUAGE_OPTIONS.get(choice_var.get(), "en")
            title_var.set(FIRST_RUN_TEXT[code]["title"])
            message_var.set(FIRST_RUN_TEXT[code]["message"])
            continue_var.set(FIRST_RUN_TEXT[code]["continue"])
            dialog.title(FIRST_RUN_TEXT[code]["title"])

        def confirm() -> None:
            self.language_var.set(choice_var.get())
            self.config["language"] = self.language_code()
            self.config["language_selected"] = True
            self.apply_language()
            self.save_config(show_message=False)
            dialog.grab_release()
            dialog.destroy()

        combo.bind("<<ComboboxSelected>>", lambda _event: refresh_dialog_text())
        ttk.Button(frame, textvariable=continue_var, command=confirm).grid(
            row=3, column=0, sticky="e", pady=(16, 0)
        )
        dialog.protocol("WM_DELETE_WINDOW", confirm)
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def apply_language(self) -> None:
        self.root.title(APP_TITLE)
        self.status_var.set(self.t("running") if self.running_var.get() else self.t("idle"))
        self.toggle_button.configure(text=self.t("stop") if self.running_var.get() else self.t("start"))
        self.widgets["language_label"].configure(text=self.t("language"))
        self.widgets["traffic_frame"].configure(text=self.t("traffic"))
        self.widgets["telegram_enabled"].configure(text=self.t("telegram_enabled"))
        self.widgets["save_button"].configure(text=self.t("save"))
        self.widgets["test_button"].configure(text=self.t("test_telegram"))
        self.widgets["alerts_frame"].configure(text=self.t("alerts"))
        self.widgets["server_refresh_alert"].configure(text=self.t("server_refresh_alert"))
        self.widgets["remaining_alert_label"].configure(text=self.t("remaining_alert_gib"))
        self.widgets["delta_alert_label"].configure(text=self.t("delta_alert_gib"))
        self.widgets["increment_alert_label"].configure(text=self.t("increment_alert_gib"))
        self.widgets["startup_frame"].configure(text=self.t("background"))
        self.widgets["startup_check"].configure(text=self.t("startup"))
        self.widgets["log_frame"].configure(text=self.t("log"))
        self.widgets["hint"].configure(text=self.t("hint"))
        for key, label in self.metric_labels.items():
            label.configure(text=self.t(key))
        if self.tray_icon is not None:
            self.tray_icon.title = APP_TITLE
            self.tray_icon.menu = self._tray_menu()
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    def toggle_monitor(self) -> None:
        if self.running_var.get():
            self.stop_monitor()
        else:
            self.start_monitor()

    def start_monitor(self) -> None:
        self.save_config(show_message=False)
        self.stop_event.clear()
        self.running_var.set(True)
        self.toggle_button.configure(text=self.t("stop"))
        self.status_var.set(self.t("running"))
        self._log(self.t("started"))

        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def stop_monitor(self) -> None:
        self.stop_event.set()
        self.running_var.set(False)
        self.toggle_button.configure(text=self.t("start"))
        self.status_var.set(self.t("stopped"))
        self.next_check_var.set("-")
        self._log(self.t("stopped_log"))

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            start = time.time()
            try:
                result = self._check_once()
                self.events.put(("snapshot", result))
            except (urllib.error.URLError, TimeoutError) as exc:
                self.events.put(("error", self.t("network_error").format(error=exc)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

            interval = int(self.config.get("interval_seconds", 300))
            while not self.stop_event.is_set():
                remaining = interval - int(time.time() - start)
                if remaining <= 0:
                    break
                self.events.put(("next_check", remaining))
                time.sleep(min(1, remaining))

    def _check_once(self) -> dict[str, Any]:
        state = monitor.load_state(self.state_path)
        html = monitor.fetch_page(
            self.config["url"],
            self.config.get("headers", {}),
            verify_ssl=bool(self.config.get("verify_ssl", False)),
        )
        snapshot = monitor.parse_quota(html, self.config)
        previous = state.get("last_snapshot")
        alerts = monitor.build_alerts(snapshot, previous, self.config, state)
        monitor.send_notifications(alerts, self.config)

        state["last_snapshot"] = {
            "day": monitor.today_key(),
            "timestamp": snapshot.timestamp,
            "download_gib": snapshot.download_gib,
            "upload_gib": snapshot.upload_gib,
            "server_updated_at": snapshot.server_updated_at,
        }
        monitor.save_json(self.state_path, state)
        return {"snapshot": snapshot, "alerts": alerts}

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "snapshot":
                    self._show_snapshot(payload["snapshot"], payload["alerts"])
                elif event == "error":
                    self.status_var.set(self.t("failed"))
                    self._log(payload)
                elif event == "next_check":
                    self.next_check_var.set(self.t("seconds_later").format(seconds=int(payload)))
        except queue.Empty:
            pass
        self.root.after(250, self._poll_events)

    def _show_snapshot(self, snapshot: monitor.QuotaSnapshot, alerts: list[str]) -> None:
        limit = float(self.config.get("daily_limit_gib", 20.0))
        download_left = max(0.0, limit - snapshot.download_gib)
        upload_left = max(0.0, limit - snapshot.upload_gib)
        checked_at = datetime.fromtimestamp(snapshot.timestamp).strftime("%Y-%m-%d %H:%M:%S")

        self.last_check_var.set(checked_at)
        self.download_var.set(f"{snapshot.download_gib:.2f} GiB / {limit:.2f} GiB")
        self.upload_var.set(f"{snapshot.upload_gib:.2f} GiB / {limit:.2f} GiB")
        self.remaining_var.set(f"Download {download_left:.2f} GiB, Upload {upload_left:.2f} GiB")
        self.status_var.set(self.t("success"))
        self._log(self.t("check_ok").format(download=snapshot.download_gib, upload=snapshot.upload_gib))
        for alert in alerts:
            self._log(self.t("alert").format(alert=alert))

    def save_config(self, show_message: bool = True) -> None:
        telegram = self.config.setdefault("telegram", {})
        telegram["enabled"] = bool(self.telegram_enabled_var.get())
        telegram["bot_token"] = self.bot_token_var.get().strip()
        telegram["chat_id"] = self.chat_id_var.get().strip()
        self.config["language"] = self.language_code()
        self.config["language_selected"] = True
        self.config["remaining_alert_gib"] = self._float_setting(
            self.remaining_alert_var, self.config.get("remaining_alert_gib", 2.0)
        )
        self.config["delta_alert_gib"] = self._float_setting(
            self.delta_alert_var, self.config.get("delta_alert_gib", 3.0)
        )
        self.config["increment_alert_gib"] = self._float_setting(
            self.increment_alert_var, self.config.get("increment_alert_gib", 0.0)
        )
        self.config["server_refresh_alert_enabled"] = bool(self.server_refresh_alert_var.get())
        self.config["verify_ssl"] = bool(self.config.get("verify_ssl", False))
        self.config["auto_start_monitor"] = bool(self.startup_enabled_var.get())
        self.apply_startup_setting()
        monitor.save_json(self.config_path, self.config)
        self._log(self.t("config_saved"))
        if show_message:
            messagebox.showinfo(APP_TITLE, self.t("config_saved"))

    def _float_setting(self, variable: tk.StringVar, fallback: Any) -> float:
        try:
            return max(0.0, float(variable.get().strip().replace(",", ".")))
        except ValueError:
            value = max(0.0, float(fallback))
            variable.set(str(value))
            return value

    def apply_startup_setting(self) -> None:
        if sys.platform == "darwin":
            self.apply_macos_startup_setting()
            return
        if sys.platform != "win32":
            return
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if self.startup_enabled_var.get():
                    winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, self.startup_command())
                else:
                    try:
                        winreg.DeleteValue(key, RUN_VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except Exception as exc:
            message = self.t("startup_failed").format(error=exc)
            self._log(message)
            messagebox.showerror(APP_TITLE, message)

    def is_startup_enabled(self) -> bool:
        if sys.platform == "darwin":
            return self.is_macos_startup_enabled()
        if sys.platform != "win32":
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _value_type = winreg.QueryValueEx(key, RUN_VALUE_NAME)
                return str(value).strip() == self.startup_command()
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --startup'
        return f'"{sys.executable}" "{Path(__file__).resolve()}" --startup'

    def macos_launch_agent_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / MACOS_LAUNCH_AGENT

    def macos_startup_arguments(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve()), "--startup"]
        return [str(Path(sys.executable).resolve()), str(Path(__file__).resolve()), "--startup"]

    def apply_macos_startup_setting(self) -> None:
        try:
            launch_agent = self.macos_launch_agent_path()
            if self.startup_enabled_var.get():
                launch_agent.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "Label": "com.amountnothing.tuklquotamonitor",
                    "ProgramArguments": self.macos_startup_arguments(),
                    "RunAtLoad": True,
                }
                with launch_agent.open("wb") as file:
                    plistlib.dump(payload, file)
            elif launch_agent.exists():
                launch_agent.unlink()
        except Exception as exc:
            message = self.t("startup_failed").format(error=exc)
            self._log(message)
            messagebox.showerror(APP_TITLE, message)

    def is_macos_startup_enabled(self) -> bool:
        launch_agent = self.macos_launch_agent_path()
        if not launch_agent.exists():
            return False
        try:
            with launch_agent.open("rb") as file:
                payload = plistlib.load(file)
            return payload.get("ProgramArguments") == self.macos_startup_arguments()
        except Exception:
            return False

    def test_telegram(self) -> None:
        self.save_config(show_message=False)
        try:
            monitor.notify_telegram(
                APP_TITLE,
                self.t("telegram_test"),
                self.config.get("telegram", {}),
            )
            self._log(self.t("telegram_sent"))
            messagebox.showinfo(APP_TITLE, self.t("telegram_sent"))
        except Exception as exc:
            message = self.t("telegram_failed").format(error=exc)
            self._log(message)
            messagebox.showerror(APP_TITLE, message)

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        if self._ask_minimize_to_tray():
            self.hide_to_tray()
            return
        self.exit_app()

    def _ask_minimize_to_tray(self) -> bool:
        return messagebox.askyesno(
            APP_TITLE,
            self.t("close_prompt"),
        )

    def hide_to_tray(self) -> None:
        if pystray is None or Image is None or ImageDraw is None:
            messagebox.showwarning(APP_TITLE, self.t("tray_warning"))
            return
        if self.tray_icon is None:
            self.tray_icon = self._create_tray_icon()
            if sys.platform == "darwin":
                self.tray_icon.run_detached()
            else:
                threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.is_hidden_to_tray = True
        self.root.withdraw()
        self._log(self.t("tray_hidden"))

    def show_from_tray(self) -> None:
        self.root.after(0, self._show_from_tray_on_ui_thread)

    def _show_from_tray_on_ui_thread(self) -> None:
        self.is_hidden_to_tray = False
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._log(self.t("tray_restored"))

    def exit_from_tray(self) -> None:
        self.root.after(0, self.exit_app)

    def exit_app(self) -> None:
        self.stop_event.set()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self.root.destroy()

    def _create_tray_icon(self) -> Any:
        image = self._create_tray_image()
        return pystray.Icon(APP_TITLE, image, APP_TITLE, self._tray_menu())

    def _tray_menu(self) -> Any:
        return pystray.Menu(
            pystray.MenuItem(self.t("tray_show"), lambda _icon, _item: self.show_from_tray()),
            pystray.MenuItem(self.t("tray_exit"), lambda _icon, _item: self.exit_from_tray()),
        )

    def _create_tray_image(self) -> Any:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(24, 112, 73, 255))
        draw.rectangle((18, 36, 26, 48), fill=(255, 255, 255, 255))
        draw.rectangle((30, 24, 38, 48), fill=(255, 255, 255, 255))
        draw.rectangle((42, 16, 50, 48), fill=(255, 255, 255, 255))
        return image


def main() -> None:
    if "--smoke-test" in sys.argv:
        return
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    app = QuotaMonitorApp(root)
    if "--startup" in sys.argv:
        root.after(300, app.start_monitor)
        root.after(900, app.hide_to_tray)
    root.mainloop()


if __name__ == "__main__":
    main()
