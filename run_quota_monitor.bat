@echo off
setlocal
cd /d "%~dp0"

if not exist config.json (
  copy config.example.json config.json >nul
  echo Created config.json from config.example.json.
  echo Please edit config.json if you need Cookie, Telegram, or verify_ssl=false.
)

python quota_monitor.py --config config.json
pause
