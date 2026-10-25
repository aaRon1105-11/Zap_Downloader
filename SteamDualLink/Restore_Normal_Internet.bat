@echo off
title Restore Normal Internet
echo Disabling system proxy...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
echo Done! Normal direct Internet restored.
pause
