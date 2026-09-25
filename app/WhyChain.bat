@echo off
rem Double-click to open WhyChain in its own window (Edge or Chrome app mode).
rem Close the window to stop the engine. Everything it does is in launch.py.
setlocal
cd /d "%~dp0\.."

rem Installed and verified: open with no console window at all.
if not defined WHYCHAIN_APP_CHECK if exist ".venv\whychain-ready.json" if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "app\launch.py"
  exit /b 0
)

rem Not yet, or not completely: this window stays open so the install can be
rem watched, and so a failure is readable instead of a window that vanishes.
echo WhyChain: setting up on this computer. The first time takes a few minutes.
echo Keep this window open. It opens WhyChain by itself when it is ready.
echo.

rem Any working Python runs the launcher, which then finds 3.12 to 3.14 itself.
rem Each candidate is run, not just found: "python" on a fresh Windows is often
rem the Microsoft Store placeholder, which exists and runs nothing.
set "PY="
rem The Python inside a machine-specific package comes first: nothing to install.
if exist "runtime\python\python.exe" set "PY=runtime\python\python.exe"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY python3 -c "import sys" >nul 2>nul && set "PY=python3"
if not defined PY goto :nopython

%PY% "app\launch.py"
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo WhyChain did not start. The reason is above, and the full log is in
echo   %CD%\data\app\install.log
echo Fix the cause, then double-click WhyChain again. Nothing is left half-installed.
if not defined WHYCHAIN_APP_QUIET pause
exit /b 1

:nopython
echo Python 3.12, 3.13 or 3.14 is needed and none was found on this computer.
echo.
echo 1. Install Python 3.12 from https://www.python.org/downloads/
echo 2. On the first screen of the installer, tick "Add python.exe to PATH".
echo 3. Double-click WhyChain again.
echo.
if not defined WHYCHAIN_APP_QUIET start "" "https://www.python.org/downloads/windows/"
if not defined WHYCHAIN_APP_QUIET pause
exit /b 1
