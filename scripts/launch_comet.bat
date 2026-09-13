@echo off
set PROFILE_DIR=%~dp0..\browser_profile
echo Starting Browser with Remote Debugging on Port 9222...
echo Profile Directory: %PROFILE_DIR%

start "" "chrome.exe" --remote-debugging-port=9222 --user-data-dir="%PROFILE_DIR%" https://www.perplexity.ai https://chatgpt.com
echo Browser started. Please log into Perplexity and ChatGPT if you haven't already.
