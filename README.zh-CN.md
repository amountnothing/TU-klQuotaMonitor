# TU-kl 流量额度监控器

[English](README.md) | [简体中文](README.zh-CN.md)

下载：[Windows](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor.exe) | [macOS Apple Silicon](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor-macOS-Apple-Silicon.zip) | [macOS Intel](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor-macOS-Intel.zip)

用于监控 `https://quota.wohnheim.uni-kl.de` 下载/上传流量额度的小工具。

## 功能

- 默认每 5 分钟检查一次下载和上传流量
- Windows/macOS 桌面程序，支持托盘和开机自启
- 可选 Telegram 通知
- 提供 Docker 镜像，适合服务器或 NAS 后台运行
- 支持简体中文、English、Deutsch
- 自动忽略跨日未刷新的旧数据和明显异常的流量值
- 界面中可调节提醒阈值

## 提醒条件

默认情况下：

- 下载或上传剩余额度不超过 2 GiB 时提醒
- 两次检测之间下载或上传增加至少 3 GiB 时提醒

新增可选提醒：

- 网页服务器端数据时间刷新后，通知本次下载/上传分别增加多少
- 下载或上传每累计增加指定 GiB 后提醒一次
- 可调节“剩余多少 GiB 才提醒”的阈值

## 桌面版使用

1. 从 Releases 下载对应系统的程序。
2. 第一次打开时选择语言。
3. 点击 **开始检测**。
4. 如需 Telegram 通知，填写 Bot Token 和 Chat ID。

额度网站只能从允许访问的大学/宿舍网络 IP 范围打开。

macOS 用户解压后，首次启动请右键点击应用并选择 **打开**。应用经过临时签名和 GitHub 云端启动测试，但没有 Apple Developer 公证。

## Docker 使用

复制 `config.docker.example.json` 为 `config.json`，按需填写 Telegram 信息，然后运行：

```bash
docker compose up -d --build
```

示例 `docker-compose.yml` 会把配置挂载到 `/config/config.json`，状态文件保存到 `quota-monitor-data` 数据卷。

## 从源码运行

```powershell
python -m pip install -r requirements.txt
python quota_monitor_gui.py
```

运行测试：

```powershell
python -m unittest test_quota_monitor.py
```

