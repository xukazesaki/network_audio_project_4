@echo off
cd /d "%~dp0"
python -m src.server.server
for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D"
pause
