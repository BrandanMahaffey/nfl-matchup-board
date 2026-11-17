@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PORT=8501"
if defined NFL_BOARD_PORT set "PORT=%NFL_BOARD_PORT%"
set "URL=http://127.0.0.1:!PORT!"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('NFL Board is missing its Python environment.','NFL Board')"
  exit /b 1
)
curl.exe -sf --max-time 2 "!URL!/_stcore/health" >nul 2>&1
if errorlevel 1 (
  pushd "%ROOT%"
  start "NFL Board" /MIN "%PYTHON%" -m streamlit run app.py --server.headless true --server.port !PORT! --browser.gatherUsageStats false
  popd
  set "READY=0"
  for /L %%N in (1,1,60) do (
    curl.exe -sf --max-time 1 "!URL!/_stcore/health" >nul 2>&1
    if not errorlevel 1 (
      set "READY=1"
      goto :open
    )
    timeout /t 1 /nobreak >nul
  )
) else (
  set "READY=1"
)
:open
if not "!READY!"=="1" (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('NFL Board did not start.','NFL Board')"
  exit /b 1
)
start "" "!URL!"
exit /b 0
