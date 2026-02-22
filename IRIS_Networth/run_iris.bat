@echo off
title IRIS Networth Calculator
cd /d "%~dp0"
"C:\Users\saech\AppData\Local\Programs\Python\Python313\python.exe" iris_networth.py
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to see the error details.
    pause >nul
    "C:\Users\saech\AppData\Local\Programs\Python\Python313\python.exe" iris_networth.py
    pause
)
