@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    py -3.10 -m venv .venv
    if errorlevel 1 goto python_error
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto install_error

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_error

echo Starting HM_VA_v06...
".venv\Scripts\python.exe" HM_VA_v06.py
goto end

:python_error
echo.
echo Python 3.10 was not found.
echo Install Python 3.10, then run this file again.
pause
exit /b 1

:install_error
echo.
echo Package installation failed.
echo Check the internet connection, then run this file again.
pause
exit /b 1

:end
pause
