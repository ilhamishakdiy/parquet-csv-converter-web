@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Parquet to CSV Converter

rem --- 0. Must run from the extracted folder, not from inside the ZIP ---------
if not exist "app.py" (
    echo ERROR: Start.bat cannot find the rest of the converter.
    echo It looks like it was opened from inside the ZIP file. Right-click the ZIP,
    echo choose "Extract All...", extract to e.g. %USERPROFILE%\ParquetConverter,
    echo then double-click Start.bat in the extracted folder.
    pause
    exit /b 1
)
echo "%CD%" | findstr /i "OneDrive" >nul && (
    echo NOTE: This folder is synced by OneDrive. The converter works, but OneDrive will
    echo upload its Python files. A folder such as %USERPROFILE%\ParquetConverter is better.
    echo.
)

rem --- 1. Find Python 3.10+ -------------------------------------------------
set "PY="
set "PYCHECK=import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
rem Python Install Manager (python-manager-*.msix): the first "py" call may download Python
rem and ask questions, so run it visibly instead of hiding its output.
where pymanager >nul 2>&1 || goto classic_python
echo Checking Python. The first time, the Python Install Manager may download Python
echo ^(a few minutes^) and ask a question - answer it in this window.
py -3 -c "%PYCHECK%" && set "PY=py -3"
if defined PY goto python_found
echo Installing Python with the Python Install Manager...
py install default
py -3 -c "%PYCHECK%" && set "PY=py -3"
if defined PY goto python_found

:classic_python
py -3 -c "%PYCHECK%" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "%PYCHECK%" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3.10 or newer was not found.
    echo Download it from the official site https://www.python.org/downloads/
    echo ^(or the company software portal^)
    echo and tick "Add python.exe to PATH" during setup. Then double-click Start.bat again.
    pause
    exit /b 1
)
:python_found

rem --- 2. Create the virtual environment on first launch --------------------
if not exist ".venv\Scripts\python.exe" (
    echo First launch: creating the Python environment. This takes a minute...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create the Python environment in "%CD%\.venv".
        echo Make sure this folder is writable, e.g. extract the ZIP to %USERPROFILE%\ParquetConverter.
        pause
        exit /b 1
    )
)
set "VPY=.venv\Scripts\python.exe"

rem --- 3. Install pinned dependencies when requirements.txt changed or packages are missing ---
"%VPY%" -m backend.envcheck check
if not errorlevel 1 goto start
echo Installing dependencies. The first time this takes a minute or two...
"%VPY%" -m pip install --disable-pip-version-check --no-input -r requirements.txt
if errorlevel 1 goto install_failed
"%VPY%" -m backend.envcheck stamp
"%VPY%" -m backend.envcheck check
if errorlevel 1 goto install_failed
goto start

:install_failed
echo.
echo ERROR: Installing dependencies failed. See the messages above.
echo Check the network or proxy settings, or ask IT whether the Python package
echo repository ^(PyPI^) is blocked. Then double-click Start.bat again.
pause
exit /b 1

:start

rem --- 4. Start the converter and open the website ----------------------------
"%VPY%" app.py %*
if errorlevel 1 (
    echo.
    echo The converter stopped with an error. See the messages above.
    pause
    exit /b 1
)
endlocal
