@echo off
:: jarvis.cmd - launcher do J.A.R.V.I.S instalado pelo JARVIS-Setup.exe
::
:: Layout da instalacao:
::   {app}\jarvis.cmd            (este arquivo)
::   {app}\runtime\python.exe    (Python 3.11 embutido, com todas as libs)
::   {app}\app\backend\main.py   (codigo do JARVIS)
::
:: Dados gravaveis (.env, logs, banco, uploads) ficam em %APPDATA%\JARVIS
:: (JARVIS_DATA_DIR, lido pelo backend\core\config.py), porque a pasta do
:: programa pode ser so leitura (Arquivos de Programas).
::
:: Abre no Windows Terminal quando existir (o conhost antigo renderiza mal a
:: TUI); "jarvis --here" roda no terminal atual.
setlocal
set "JARVIS_HOME=%~dp0"
if not defined JARVIS_DATA_DIR set "JARVIS_DATA_DIR=%APPDATA%\JARVIS"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "JARVIS_PY=%JARVIS_HOME%runtime\python.exe"

if /i "%~1"=="--here" goto run
if defined WT_SESSION goto run
where wt.exe >nul 2>&1
if errorlevel 1 goto run
start "" wt.exe -w new --title "JARVIS" cmd.exe /c "%~f0" --here
exit /b 0

:run
if not exist "%JARVIS_PY%" (
    echo [ERRO] Python embutido nao encontrado em "%JARVIS_PY%". Reinstale o JARVIS.
    pause
    exit /b 1
)
cd /d "%JARVIS_HOME%app\backend"
"%JARVIS_PY%" main.py
if errorlevel 1 pause
exit /b %errorlevel%
