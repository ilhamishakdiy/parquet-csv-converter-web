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
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3.10 or newer was not found.
    echo Install Python from the company software portal or https://www.python.org/downloads/windows/
    echo and tick "Add python.exe to PATH" during setup. Then double-click Start.bat again.
    pause
    exit /b 1
)

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

rem --- 3. Install pinned dependencies only when requirements.txt changed ---
set "REQHASH="
for /f "usebackq delims=" %%H in (`"%VPY%" -c "import hashlib;print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"`) do set "REQHASH=%%H"
set "OLDHASH="
if exist ".venv\requirements.sha256" set /p OLDHASH=<".venv\requirements.sha256"
if not "%REQHASH%"=="%OLDHASH%" (
    echo Installing dependencies...
    "%VPY%" -m pip install --disable-pip-version-check --no-input -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Installing dependencies failed. Check the network or proxy settings,
        echo or ask IT whether the Python package repository ^(PyPI^) is blocked.
        pause
        exit /b 1
    )
    > ".venv\requirements.sha256" echo %REQHASH%
)

rem --- 4. Start the converter and open the website ----------------------------
"%VPY%" app.py %*
if errorlevel 1 (
    echo.
    echo The converter stopped with an error. See the messages above.
    pause
    exit /b 1
)
endlocal
