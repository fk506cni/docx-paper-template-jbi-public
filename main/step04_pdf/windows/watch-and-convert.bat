@echo off
REM === DOCX -> PDF Auto-Converter Launcher ===
REM Double-click this file to start the folder watcher.
REM The PowerShell window will stay open. Press Ctrl+C to stop.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch-and-convert.ps1"
pause
