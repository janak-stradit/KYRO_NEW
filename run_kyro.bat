@echo off
REM ============================================================
REM  KYRO AML - local launcher (no Docker)
REM
REM  Runs the API + frontend as ONE process on http://localhost:8010
REM  using a Python venv (.venv) and your locally installed PostgreSQL.
REM
REM  Usage:
REM    run_kyro.bat            start KYRO (first run installs everything)
REM    run_kyro.bat seed       load synthetic sample customers, transactions
REM                            and periodic review schedules
REM    run_kyro.bat install    re-install Python dependencies
REM
REM  Database connection: put it in local.env (git-ignored), e.g.
REM    KYRO_DATABASE_URL=postgresql+psycopg://postgres:yourpass@localhost:5432/kyro_aml
REM  The database is created automatically if it doesn't exist.
REM  Optional in local.env:  KYRO_PORT=8010
REM ============================================================
setlocal
cd /d "%~dp0"

if exist "local.env" (
    for /f "usebackq eol=# tokens=1* delims==" %%a in ("local.env") do set "%%a=%%b"
)
if not defined KYRO_PORT set "KYRO_PORT=8010"
if not defined KYRO_DATABASE_URL (
    echo [!] No database configured. Create local.env next to this file containing:
    echo     KYRO_DATABASE_URL=postgresql+psycopg://postgres:yourpass@localhost:5432/kyro_aml
    goto :fail
)

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "DEPS_MARKER=%~dp0.venv\.kyro_deps_installed"

REM Settings for a local run. Real environment variables take priority over
REM .env, so these override the Docker-oriented values in .env.
REM The app uses psycopg v3, so accept psycopg2-style URLs too.
set "DATABASE_URL=%KYRO_DATABASE_URL:+psycopg2=+psycopg%"
set "SERVE_FRONTEND_DIR=%~dp0frontend\phase3"
set "ML_OPTIONAL=true"
set "CORS_ALLOWED_ORIGINS=http://localhost:%KYRO_PORT%,http://127.0.0.1:%KYRO_PORT%"
REM The API also serves the frontend locally, so page assets count toward
REM the per-IP limit - raise it for local use.
set "RATE_LIMIT_DEFAULT=3000/minute"
set "RATE_LIMIT_STORAGE_URI="
set "PYTHONPATH=%~dp0"

REM Windows Smart App Control blocks some unsigned compiled modules from PyPI
REM wheels (psycopg-binary, SQLAlchemy speedups, scikit-learn, pandas). Use
REM psycopg's pure-Python mode on top of the signed libpq.dll shipped with
REM PostgreSQL; SQLAlchemy is installed without C extensions (see :ensure_venv).
set "PG_BIN="
for /d %%d in ("%ProgramFiles%\PostgreSQL\*") do if exist "%%d\bin\psql.exe" if exist "%%d\bin\libpq.dll" set "PG_BIN=%%d\bin"
if defined PG_BIN (
    set "PATH=%PG_BIN%;%PATH%"
    set "PSYCOPG_IMPL=python"
)

if /i "%~1"=="install" (
    if exist "%DEPS_MARKER%" del "%DEPS_MARKER%"
    call :ensure_venv || goto :fail
    echo Dependencies re-installed.
    exit /b 0
)
if /i "%~1"=="seed" goto :seed
if not "%~1"=="" (
    echo Unknown option "%~1". Use: seed ^| install
    exit /b 1
)

REM ---------------------------------------------------------------
:start
echo.
echo [1/4] Checking Python environment...
call :ensure_venv || goto :fail

echo.
echo [2/4] Checking PostgreSQL...
call :ensure_db || goto :fail

echo.
echo [3/4] Applying database migrations...
"%VENV_PY%" -m alembic -c app\alembic.ini upgrade head || goto :fail

echo.
echo [4/4] Starting KYRO...
echo ============================================================
echo  KYRO (local)
echo    App      : http://localhost:%KYRO_PORT%
echo    API docs : http://localhost:%KYRO_PORT%/docs
echo.
echo  Logins: admin/admin123  analyst/kyro123  compliance/kyro123
echo  No data yet? In another window run:  run_kyro.bat seed
echo.
echo  Not running locally: Celery background jobs (ML retraining,
echo  watchlist refresh, nightly re-screen) - they need Redis.
echo  Press Ctrl+C to stop.
echo ============================================================
start "" cmd /c "ping -n 6 127.0.0.1 >nul & start http://localhost:%KYRO_PORT%/login.html"
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %KYRO_PORT% --reload --reload-dir app --timeout-graceful-shutdown 3
exit /b %errorlevel%

REM ---------------------------------------------------------------
:seed
call :ensure_venv || goto :fail
call :ensure_db || goto :fail
"%VENV_PY%" -m alembic -c app\alembic.ini upgrade head || goto :fail
echo Loading synthetic sample data...
"%VENV_PY%" scripts\seed_app_data.py --customers 250 --min-txns 10 --max-txns 40 || goto :fail
echo Scheduling risk-based periodic reviews...
"%VENV_PY%" scripts\seed_periodic_reviews.py --backfill-last-review || goto :fail
echo Done.
exit /b 0

REM ---------------------------------------------------------------
:ensure_db
"%VENV_PY%" scripts\ensure_local_db.py
exit /b %errorlevel%

:ensure_venv
if not exist "%VENV_PY%" (
    where python >nul 2>&1 || (
        echo [!] Python not found. Install Python 3.11+ from https://www.python.org/ and tick "Add to PATH".
        exit /b 1
    )
    echo Creating virtual environment in .venv ...
    python -m venv .venv || exit /b 1
)
if exist "%DEPS_MARKER%" (
    echo Python environment OK.
    exit /b 0
)
echo Installing Python dependencies - first run takes a few minutes...
"%VENV_PY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%VENV_PY%" -m pip install --disable-pip-version-check -q -r requirements-api.txt -r requirements-ml.txt "pandas<3" || exit /b 1
REM Pure-Python SQLAlchemy - its compiled speedups are optional and get
REM blocked by Smart App Control.
set "DISABLE_SQLALCHEMY_CEXT=1"
"%VENV_PY%" -m pip install --disable-pip-version-check -q --force-reinstall --no-deps --no-binary sqlalchemy "sqlalchemy>=2.0.30" || exit /b 1
echo installed> "%DEPS_MARKER%"
exit /b 0

REM ---------------------------------------------------------------
:fail
echo.
echo [X] Something went wrong - see the messages above.
pause
exit /b 1
