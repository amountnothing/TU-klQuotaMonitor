# Wohnheim Quota Monitor

这是一个 Windows 下运行的 Python 流量额度监控脚本，用来监控：

`https://quota.wohnheim.uni-kl.de`

默认每 5 分钟刷新一次，读取网页中的 Download / Upload 流量。每天下载和上传限额默认各 `20 GiB`。当剩余额度小于等于 `2 GiB`，或一次 5 分钟检查周期内新增流量大于等于 `3 GiB` 时，会发送 Windows 通知，也可以发送 Telegram Bot 通知。

## 直接运行 GUI exe

已经打包好的单文件程序：

```text
WohnheimQuotaMonitor.exe
```

双击即可运行，不需要安装 Python，也不需要额外安装依赖。新版是无控制台窗口的 Windows GUI 程序。

首次启动时，程序会根据系统语言自动预选界面语言，并弹出语言选择窗口。确认后会保存选择，之后启动会直接进入主界面。

界面功能：

- `开始检测` / `停止检测`：控制后台检测线程；
- `语言 / Language / Sprache`：支持简体中文、English、Deutsch；
- 当前 Download / Upload 使用量；
- 剩余额度和下次检测倒计时；
- Telegram Bot Token / Chat ID 输入框；
- 保存配置和测试 Telegram 通知；
- 开机自启并自动开始检测；
- 关闭窗口时可选择最小化到系统托盘。

程序默认每 5 分钟检测一次，并把配置文件 `config.json` 和状态文件 `quota_state.json` 自动保存在 exe 同目录。关闭窗口时选择“是”会隐藏到系统托盘并继续后台检测；托盘菜单可以重新显示窗口或退出程序。

语言选择会自动保存到 `config.json`。界面、弹窗、托盘菜单、Windows 通知和 Telegram 提醒都会跟随当前语言。删除 `config.json` 后再次启动，会重新进入首次语言选择流程。

勾选 `开机自启并自动开始检测` 后，程序会写入当前 Windows 用户的启动项。下次登录 Windows 时会自动启动、开始检测，并缩到系统托盘。不需要管理员权限。

## Python 源码运行方式

1. 安装 Python 3.9 或更新版本。
2. 可选安装 Windows 桌面通知库：

```powershell
pip install winotify
```

3. 复制配置文件：

```powershell
Copy-Item .\config.example.json .\config.json
```

4. 运行一次测试：

```powershell
python .\quota_monitor.py --config .\config.json --once
```

5. 长期运行：

```powershell
python .\quota_monitor.py --config .\config.json
```

正常使用 exe 时，上面的 Python 步骤都不需要。

## Telegram 通知

在 `config.json` 里打开：

```json
"telegram": {
  "enabled": true,
  "bot_token": "你的 Bot Token",
  "chat_id": "你的 Chat ID"
}
```

创建 Bot 可以找 Telegram 里的 `@BotFather`。获取 `chat_id` 的常见方式是先给 Bot 发一条消息，然后访问：

```text
https://api.telegram.org/bot<你的 Bot Token>/getUpdates
```

## 如果网页需要登录

exe 默认不需要手动创建配置文件。你在界面里保存 Telegram 信息后，程序会自动生成 `config.json`。

如果网页需要 Cookie，可以把 `config.example.json` 复制为 exe 同目录下的 `config.json` 再编辑。

这个站点的证书链可能无法被 Python/exe 校验，所以新版默认已经设置为：

```json
"verify_ssl": false
```

如果你想强制校验证书，可以改成 `true`，但遇到 `CERTIFICATE_VERIFY_FAILED` 时请改回 `false`。

如果 `--once` 提示解析失败，或者返回的是登录页，可以把浏览器中访问该网页时的 Cookie 复制到 `config.json`：

```json
"headers": {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
  "Cookie": "这里粘贴浏览器里的 Cookie"
}
```

## 如果自动解析失败

脚本会把网页纯文本保存成 `last_quota_page_text.txt`。打开它，看 Download 和 Upload 附近的真实文字，然后在 `config.json` 的 `parsing` 里填自定义正则。

例子：

```json
"parsing": {
  "download_regex": "Download[^0-9]*([0-9]+(?:[.,][0-9]+)?)\\s*(GiB|GB|MiB|MB)",
  "upload_regex": "Upload[^0-9]*([0-9]+(?:[.,][0-9]+)?)\\s*(GiB|GB|MiB|MB)"
}
```

正则要求第一个捕获组是数值，第二个捕获组可以是单位。

## 开机自启建议

可以用 Windows 任务计划程序创建任务：

- 触发器：登录时
- 操作：启动程序
- 程序：`python`
- 参数：`C:\完整路径\quota_monitor.py --config C:\完整路径\config.json`
