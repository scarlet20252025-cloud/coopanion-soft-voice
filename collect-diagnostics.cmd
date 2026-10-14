@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\collect-diagnostics.ps1" %*
pause
