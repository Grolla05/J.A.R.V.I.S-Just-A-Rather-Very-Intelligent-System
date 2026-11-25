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
:: TUI); "jarvis --here" roda no terminal atual. "--copilot" abre no modo voz.
:: O agente residente (Win+J) roda separado: runtime\pythonw.exe app\backend\agent.py
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
:: Perfil JARVIS (fragment gravado pelo main.py) poe a logo do JARVIS na aba
set "JARVIS_WT_PROFILE="
if exist "%LOCALAPPDATA%\Microsoft\Windows Terminal\Fragments\JARVIS\jarvis.json" set "JARVIS_WT_PROFILE=-p JARVIS"
start "" wt.exe -w new %JARVIS_WT_PROFILE% --title "JARVIS" cmd.exe /c "%~f0" --here %*
exit /b 0

:run
if not exist "%JARVIS_PY%" (
    echo [ERRO] Python embutido nao encontrado em "%JARVIS_PY%". Reinstale o JARVIS.
    pause
    exit /b 1
)
cd /d "%JARVIS_HOME%app\backend"
:: %* repassa --copilot (Win+J do agente abre a TUI direto no modo voz)
"%JARVIS_PY%" main.py %*
set "JARVIS_RC=%errorlevel%"
:: Crash nativo nao deixa a TUI restaurar o terminal: desliga rastreio de mouse,
:: tela alternativa e cursor oculto para o prompt nao virar lixo ([555;89;14M...).
for /f %%a in ('echo prompt $E^| cmd') do set "ESC=%%a"
<nul set /p "=%ESC%[?1000l%ESC%[?1002l%ESC%[?1003l%ESC%[?1006l%ESC%[?1015l%ESC%[?1049l%ESC%[?25h"
if not "%JARVIS_RC%"=="0" pause
exit /b %JARVIS_RC%
