@echo off
cd /d "%~dp0"
if exist "data\server\stop.signal" del /q "data\server\stop.signal"
title Network Audio Server
python -m src.server.server
for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D"
pause
