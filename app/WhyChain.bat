@echo off
rem Double-click to open WhyChain in its own window (Edge or Chrome app mode).
rem Close the window to stop the engine. Everything it does is in launch.py.
cd /d "%~dp0\.."
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "app\launch.py"
  exit /b 0
)
rem First run builds the environment, so this window stays open to show progress.
echo Setting up WhyChain for the first time. This takes a few minutes.
where py >nul 2>nul && (py -3 "app\launch.py" & goto :done)
where python >nul 2>nul && (python "app\launch.py" & goto :done)
echo.
echo Python 3.12 or newer is not installed on this computer.
echo Install it from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH", then double-click WhyChain again.
pause
:done
