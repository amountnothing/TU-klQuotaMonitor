# TU-kl 流量额度监控器

[English](README.md) | [简体中文](README.zh-CN.md)

下载：[Windows](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor.exe) | [macOS Apple Silicon](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor-macOS-Apple-Silicon.zip) | [macOS Intel](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest/download/WohnheimQuotaMonitor-macOS-Intel.zip)

这是一个用于监控 `https://quota.wohnheim.uni-kl.de` 流量额度的 Windows 小工具。

## 功能

- 每 5 分钟检查一次下载和上传流量
- 支持 Windows 通知和可选的 Telegram 通知
- 跨日时自动忽略尚未刷新的旧配额数据
- 拒绝明显异常的流量值，避免错误提醒
- 支持简体中文、English 和 Deutsch
- 支持最小化到系统托盘
- 支持开机自启并自动开始检测
- Windows 和 macOS 打包版都不需要安装 Python

## 快速开始

1. 从 [Releases](https://github.com/amountnothing/TU-klQuotaMonitor/releases/latest) 下载 `WohnheimQuotaMonitor.exe`。
2. 第一次打开时选择语言。
3. 点击 **开始检测**。
4. 如需 Telegram 通知，填写 Bot Token 和 Chat ID。

配额网站只能从允许访问的大学或宿舍网络 IP 范围打开。

macOS 用户解压后，首次启动请右键点击应用并选择 **打开**。应用经过临时签名和 GitHub 云端启动测试，但没有使用 Apple Developer 证书公证。

## 默认提醒条件

- 下载或上传剩余额度不超过 2 GiB；或
- 两次检测之间，下载或上传增加至少 3 GiB。

## 从源码运行

```powershell
python -m pip install -r requirements.txt
python quota_monitor_gui.py
```

运行测试：

```powershell
python -m unittest test_quota_monitor.py
```
