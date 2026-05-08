@echo off
cd /d "%~dp0"
if not exist "data\server" mkdir "data\server"
echo stop>"data\server\stop.signal"
echo Stop signal written to data\server\stop.signal
echo The running server will shut down shortly.
pause
