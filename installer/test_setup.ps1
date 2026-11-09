# test_setup.ps1 - teste do instalador dist\JARVIS-Setup.exe
#
# Instala em silencio numa pasta temporaria (so para o usuario atual, sem as
# paginas do Ollama), confere os arquivos e a chave de desinstalacao, roda o
# Python instalado importando o JARVIS em modo instalado (dados numa pasta
# temporaria) e desinstala, conferindo que nada ficou para tras.
# Uso: powershell -File installer\test_setup.ps1
# Mensagens sem acento: o PowerShell 5.1 le .ps1 sem BOM como ANSI.

$ErrorActionPreference = 'Stop'

$raiz    = Resolve-Path (Join-Path $PSScriptRoot '..')
$setup   = Join-Path $raiz 'dist\JARVIS-Setup.exe'
$appId   = '{C73936E3-24F9-49BF-97C8-A9878023BAF6}'
$chave   = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\${appId}_is1"
$tmp     = [IO.Path]::GetTempPath()
$destino = Join-Path $tmp ("jarvis_teste_setup_" + [guid]::NewGuid().ToString('N'))
$dados   = Join-Path $tmp ("jarvis_teste_dados_" + [guid]::NewGuid().ToString('N'))
$probe   = Join-Path $tmp ("jarvis_teste_probe_" + [guid]::NewGuid().ToString('N') + '.py')
# O setup copia o .env para o %APPDATA% real (pasta de shell, nao a variavel)
$envReal = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'JARVIS\.env'
$envJaExistia = Test-Path $envReal
$verificacoes = 0

function Falha([string]$msg) {
    Write-Host "SETUP FALHOU: $msg"
    exit 1
}

function Confere([bool]$cond, [string]$msg) {
    if (-not $cond) { Falha $msg }
    $script:verificacoes++
}

# 1. O instalador foi gerado
Confere (Test-Path $setup) "instalador nao encontrado em $setup (rode build_runtime.ps1 e o iscc)"

# 2. Instalacao silenciosa, sem tarefas opcionais e sem Ollama/modelo
$p = Start-Process -FilePath $setup -Wait -PassThru -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/CURRENTUSER', '/NORESTART', '/SKIPOLLAMA',
    "/DIR=`"$destino`"", '/TASKS=""')
Confere ($p.ExitCode -eq 0) "instalacao saiu com codigo $($p.ExitCode)"

# 3. Arquivos instalados
foreach ($arq in 'jarvis.cmd', 'unins000.exe', 'runtime\python.exe', 'runtime\pythonw.exe', 'app\VERSION',
                 'app\env.example', 'app\backend\main.py', 'app\backend\agent.py', 'app\backend\prompts\system_prompt.md', 'app\frontend\app.py',
                 'app\frontend\jarvis.tcss') {
    Confere (Test-Path (Join-Path $destino $arq)) "arquivo ausente apos instalar: $arq"
}
Confere (-not (Test-Path (Join-Path $destino 'app\backend\tests'))) "testes do backend foram empacotados"
Confere (Test-Path $envReal) ".env nao foi criado em $envReal"

# 4. O Python instalado importa o JARVIS em modo instalado (JARVIS_DATA_DIR)
@'
import json, os, sys
# cwd = app\backend (como no jarvis.cmd); ".." = app\, onde mora o pacote frontend
sys.path[:0] = [os.getcwd(), os.path.dirname(os.getcwd())]
import textual, ollama, faster_whisper, pyaudio, pycaw, psutil, mcp, edge_tts, pygame, pystray
import core.autostart, core.presence, core.hotkey, core.launcher
from core.config import settings as s
import frontend.app
print(json.dumps({"data": str(s.DIR_DATA), "installed": s.IS_INSTALLED, "db": str(s.DB_PATH), "version": s.VERSION}))
'@ | Set-Content -Path $probe -Encoding ascii
$env:JARVIS_DATA_DIR = $dados
$env:PYTHONNOUSERSITE = '1'
$env:PYGAME_HIDE_SUPPORT_PROMPT = '1'
Push-Location (Join-Path $destino 'app\backend')
$ErrorActionPreference = 'Continue'   # stderr de exe nativo vira erro no PS 5.1
try {
    $saida = & (Join-Path $destino 'runtime\python.exe') $probe 2>&1 | ForEach-Object { "$_" }
    $rc = $LASTEXITCODE
} finally {
    $ErrorActionPreference = 'Stop'
    Pop-Location
    Remove-Item Env:\JARVIS_DATA_DIR
}
Remove-Item $probe
if ($rc -ne 0) { $saida | Select-Object -Last 15 | Write-Host }
Confere ($rc -eq 0) "python instalado falhou ao importar o JARVIS (codigo $rc)"
$cfg = ($saida | Where-Object { $_ -like '{*' } | Select-Object -Last 1) | ConvertFrom-Json
Confere ($cfg.installed -eq $true) "config nao entrou em modo instalado"
Confere ($cfg.data -eq $dados) "pasta de dados inesperada: $($cfg.data)"
Confere (Test-Path (Join-Path $dados 'database')) "pasta do banco ausente em $dados"
Confere (-not (Test-Path (Join-Path $destino 'app\backend\database'))) "JARVIS criou o banco na pasta de instalacao"
Confere (-not (Test-Path (Join-Path $destino 'app\backend\logs'))) "JARVIS criou logs na pasta de instalacao"
Remove-Item -Recurse -Force $dados

# 5. Registro de desinstalacao (aparece em "Aplicativos instalados")
Confere (Test-Path $chave) "chave de desinstalacao ausente: $chave"
$nome = (Get-ItemProperty $chave).DisplayName
Confere ($nome -like 'J.A.R.V.I.S*') "DisplayName inesperado: '$nome'"

# 6. Desinstalacao silenciosa remove pasta e chave
$p = Start-Process -FilePath (Join-Path $destino 'unins000.exe') -Wait -PassThru `
    -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
Confere ($p.ExitCode -eq 0) "desinstalacao saiu com codigo $($p.ExitCode)"
# O desinstalador se copia para %TEMP% e termina de apagar logo depois
for ($i = 0; $i -lt 40 -and (Test-Path $destino); $i++) { Start-Sleep -Milliseconds 250 }
Confere (-not (Test-Path $destino)) "pasta de instalacao ainda existe: $destino"
Confere (-not (Test-Path $chave)) "chave de desinstalacao ainda existe: $chave"
# Os dados do usuario sobrevivem a desinstalacao silenciosa
Confere (Test-Path $envReal) ".env do usuario foi apagado pela desinstalacao"
if (-not $envJaExistia) { Remove-Item -Recurse -Force (Split-Path $envReal) }

Write-Host "SETUP OK ($verificacoes verificacoes)"
