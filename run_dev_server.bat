@echo off
rem Double-click: opens one Windows Terminal window with two cmd tabs running
rem the SHOP (15173) and SIA (15174) Vite dev servers.
rem Needs the dev stack for API calls: docker compose -f deploy/compose.dev.yml up -d
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\node_modules" (
  pushd "%ROOT%" && call npm install && popd
)

rem Stop leftover node servers (old dev/preview/Playwright runs) on our ports.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 15173,15174 -State Listen -EA SilentlyContinue | ForEach-Object { Get-Process -Id $_.OwningProcess -EA SilentlyContinue } | Where-Object Name -eq 'node' | Stop-Process -Force"

where wt >nul 2>nul
if %errorlevel%==0 (
  wt -w new new-tab --title "SHOP :15173" -d "%ROOT%\web\shop" cmd /k npm run dev ; new-tab --title "SIA :15174" -d "%ROOT%\web\sia" cmd /k npm run dev
) else (
  start "SHOP :15173" /d "%ROOT%\web\shop" cmd /k npm run dev
  start "SIA :15174" /d "%ROOT%\web\sia" cmd /k npm run dev
)
