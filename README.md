# TU-kl Quota Monitor

[English](README.md) | [简体中文](README.zh-CN.md)

Downloads: [Windows](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor.exe) | [macOS Apple Silicon](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor-macOS-Apple-Silicon.zip) | [macOS Intel](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor-macOS-Intel.zip)

A small app for monitoring traffic usage from `https://quota.wohnheim.uni-kl.de`.

## Features

- Checks download and upload usage every 5 minutes
- Windows/macOS desktop app with system tray and startup support
- Optional Telegram alerts
- Docker image for headless/server use
- Chinese, English and German interface
- Ignores stale daily rollover data and implausible traffic values
- Adjustable alert thresholds in the UI

## Alerts

The default settings alert when remaining quota is at most 2 GiB, or when download/upload increases by at least 3 GiB between checks.

Additional options:

- Notify how much traffic increased when the quota page's server-side data timestamp changes
- Notify every time download/upload increases by a configured GiB amount
- Adjust the remaining-quota warning threshold

## Desktop Quick Start

1. Download the package for your platform.
2. Choose your language on first launch.
3. Click **Start**.
4. Optionally enter a Telegram Bot Token and Chat ID.

The quota page is only reachable from permitted university/dormitory IP ranges.

On macOS, unzip the app and use **right-click > Open** on first launch. The app is ad-hoc signed and cloud-tested, but not notarized with an Apple Developer certificate.

## Docker

Copy `config.docker.example.json` to `config.json`, edit Telegram settings if needed, then run:

```bash
docker compose up -d --build
```

The sample `docker-compose.yml` mounts the config at `/config/config.json` and stores state in the `quota-monitor-data` volume.

## Run From Source

```powershell
python -m pip install -r requirements.txt
python quota_monitor_gui.py
```

Run tests with:

```powershell
python -m unittest test_quota_monitor.py
```

