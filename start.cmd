@echo off
rem Starts WhyChain and warms it up. Double-click this file, or run  start.cmd  from the project folder.
rem The default needs nothing but Python and NEBIUS_API_KEY in .env: every model call goes to NVIDIA Nemotron on
rem Nebius Token Factory, data is queried in place with DuckDB, and memory lives in runs\. Optional extras start only
rem when .env asks for them: the ERP database in Docker (USE_POSTGRES=true), the Zetaris platform (ZETARIS_DIR) and
rem the Meterless engines bridge (METERLESS_BRIDGE_URL).
cd /d "%~dp0"

for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if /i "%%a"=="ZETARIS_DIR" set "ZETARIS_DIR=%%b"
  if /i "%%a"=="USE_POSTGRES" set "USE_POSTGRES=%%b"
  if /i "%%a"=="METERLESS_BRIDGE_URL" set "METERLESS_BRIDGE_URL=%%b"
)

if defined ZETARIS_DIR goto needdocker
if /i "%USE_POSTGRES%"=="true" goto needdocker
goto nodocker

:needdocker
docker info >nul 2>&1
if not errorlevel 1 goto dockerready
echo Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
:waitdocker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto waitdocker
:dockerready
if defined ZETARIS_DIR (
  echo Starting Zetaris from %ZETARIS_DIR% ...
  pushd "%ZETARIS_DIR%"
  docker compose up -d
  popd
)
if /i "%USE_POSTGRES%"=="true" (
  echo Starting the ERP database...
  docker compose up -d
)
:nodocker

if defined METERLESS_BRIDGE_URL (
  echo Starting the optional Meterless engines bridge...
  start "WhyChain - Meterless bridge" cmd /k "cd meterless_bridge && npm start"
)

echo Starting the web app...
start "WhyChain - web app" cmd /k ".venv\Scripts\python -m whychain.api"

echo Warming up...
.venv\Scripts\python scripts\warmup.py

start http://localhost:8000
echo WhyChain is running at http://localhost:8000  (close the web app window to stop it)
