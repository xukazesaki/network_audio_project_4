@echo off
cd /d "%~dp0"
python -m src.apps.client_stream_gui
for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D"
pause
