@echo off
setlocal enabledelayedexpansion

for %%I in ("%~dp0..\browser_profile") do set "PROFILE_DIR=%%~fI"

set "BROWSER_BIN="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_BIN=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_BIN=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_BIN=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Perplexity\Comet\Application\comet.exe" (
    set "BROWSER_BIN=%LOCALAPPDATA%\Perplexity\Comet\Application\comet.exe"
) else (
    set "BROWSER_BIN=chrome.exe"
)

echo ========================================================
echo Khoi chay Google Chrome voi Remote Debugging Port 9222...
echo Trinh duyet: "!BROWSER_BIN!"
echo Thu muc Profile: "!PROFILE_DIR!"
echo ========================================================

start "" "!BROWSER_BIN!" --remote-debugging-port=9222 --user-data-dir="!PROFILE_DIR!" https://www.perplexity.ai https://chatgpt.com

echo Trinh duyet da duoc mo. Vui long dang nhap Perplexity va ChatGPT neu chua dang nhap.
