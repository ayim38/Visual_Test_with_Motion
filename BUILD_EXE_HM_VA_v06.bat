@echo off
setlocal
cd /d "%~dp0"

echo Building HM_VA_v06.exe...
python -m PyInstaller HM_VA_v06.spec --clean --noconfirm
if errorlevel 1 goto build_error

echo.
echo Build completed.
echo EXE path: dist\HM_VA_v06.exe
pause
exit /b 0

:build_error
echo.
echo Build failed.
echo Make sure PyInstaller is installed:
echo python -m pip install pyinstaller
pause
exit /b 1
