@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Telegram Excel Filter Bot Setup

echo === Telegram Excel Filter Bot Setup ===

set "PY="
where py >nul 2>nul
if !errorlevel! equ 0 set "PY=py"
if not defined PY (
  where python >nul 2>nul
  if !errorlevel! equ 0 set "PY=python"
)
if not defined PY (
  echo Python পাওয়া যায়নি। python.org থেকে Python ইনস্টল করে আবার চালান।
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" !PY! -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if not exist ".env" (
  echo.
  set "BOT_TOKEN="
  set /p "BOT_TOKEN=BotFather-এর নতুন Bot Token paste করুন: "
  if "!BOT_TOKEN!"=="" (
    echo Token খালি রাখা যাবে না।
    pause
    exit /b 1
  )
  set "ADMIN_IDS="
  set /p "ADMIN_IDS=আপনার Telegram user ID (কমা দিয়ে একাধিক): "
  >.env echo BOT_TOKEN=!BOT_TOKEN!
  >>.env echo ADMIN_IDS=!ADMIN_IDS!
  >>.env echo MAX_FILE_SIZE_MB=20
)

echo.
echo Bot চালু হচ্ছে। বন্ধ করতে Ctrl+C চাপুন।
python bot.py
pause
