# TU-kl Quota Monitor

[English](README.md) | [简体中文](README.zh-CN.md)

[Download the latest Windows release](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest)

A small Windows app for monitoring traffic usage from
`https://quota.wohnheim.uni-kl.de`.

## Features

- Checks download and upload usage every 5 minutes
- Windows and optional Telegram alerts
- Ignores stale quota data during the daily rollover
- Rejects implausible traffic values instead of sending false alerts
- Chinese, English and German interface
- System tray mode and optional Windows auto-start
- No Python installation required for the packaged `.exe`

## Quick start

1. Download and open `WohnheimQuotaMonitor.exe`.
2. Choose your language on first launch.
3. Click **Start**.
4. Optionally enter a Telegram Bot Token and Chat ID.

The quota page is only reachable from permitted university/dormitory IP ranges.

## Alerts

With the default settings, the app sends an alert when:

- Download or upload quota remaining is at most 2 GiB, or
- Download or upload increases by at least 3 GiB between checks.

## Run from source

```powershell
python -m pip install -r requirements.txt
python quota_monitor_gui.py
```

Run tests with:

```powershell
python -m unittest test_quota_monitor.py
```
