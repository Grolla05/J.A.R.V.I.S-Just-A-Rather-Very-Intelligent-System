# build_runtime.ps1 - monta o conteudo do JARVIS-Setup.exe em dist\
#
#   dist\runtime\  Python 3.11 completo (pacote NuGet oficial "python") com
#                  todas as libs do backend\requirements.txt ja instaladas
#   dist\app\      codigo do JARVIS (backend\ sem testes/dados, frontend\, VERSION...)
#
# O instalador (installer\jarvis.iss) so copia essas pastas: a maquina de quem
# instala nao precisa de Python, pip, compilador nem internet para as libs.
#
# Uso: powershell -File installer\build_runtime.ps1 [-Versao 1.0.3] [-PythonVersion 3.11.9]
# Mensagens sem acento: o PowerShell 5.1 le .ps1 sem BOM como ANSI.

param(
    [string]$Versao = '',
    [string]$PythonVersion = '3.11.9'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest fica muito lento com a barra

$raiz    = Resolve-Path (Join-Path $PSScriptRoot '..')
$dist    = Join-Path $raiz 'dist'
$runtime = Join-Path $dist 'runtime'
$app     = Join-Path $dist 'app'
$cache   = Join-Path $dist 'cache'

function Passo([string]$msg) { Write-Host "==> $msg" }

function Roda([string]$exe, [string[]]$argumentos) {
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "falhou ($LASTEXITCODE): $exe $($argumentos -join ' ')" }
}

# Remove pastas e arquivos com caminho longo (site-packages passa de 260 chars)
function Apaga([string]$caminho) {
    if (Test-Path -LiteralPath $caminho) { Remove-Item -LiteralPath $caminho -Recurse -Force }
}

# --- 1. Runtime Python -------------------------------------------------------
Passo "Python $PythonVersion (NuGet) -> $runtime"
New-Item -ItemType Directory -Force $cache | Out-Null
$nupkg = Join-Path $cache "python.$PythonVersion.zip"
if (-not (Test-Path $nupkg)) {
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.nuget.org/api/v2/package/python/$PythonVersion" -OutFile $nupkg
}
$extraido = Join-Path $cache "python.$PythonVersion"
Apaga $extraido
Expand-Archive -LiteralPath $nupkg -DestinationPath $extraido
Apaga $runtime
Move-Item (Join-Path $extraido 'tools') $runtime
Apaga $extraido

$py = Join-Path $runtime 'python.exe'
$env:PYTHONNOUSERSITE = '1'   # nao herdar pacotes do usuario de quem gera o build
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
Roda $py @('--version')

# --- 2. Dependencias --------------------------------------------------------
Passo 'pip install -r backend\requirements.txt'
Roda $py @('-m', 'ensurepip', '--upgrade')
Roda $py @('-m', 'pip', 'install', '--no-cache-dir', '--no-warn-script-location', '--upgrade', 'pip')
Roda $py @('-m', 'pip', 'install', '--no-cache-dir', '--no-warn-script-location', '--prefer-binary',
    '-r', (Join-Path $raiz 'backend\requirements.txt'))

# --- 3. Limpeza --------------------------------------------------------------
Passo 'Limpando runtime (caches, testes das libs)'
Get-ChildItem $runtime -Recurse -Directory -Force -Filter '__pycache__' | ForEach-Object { Apaga $_.FullName }
$site = Join-Path $runtime 'Lib\site-packages'
foreach ($d in Get-ChildItem $site -Directory) {
    foreach ($t in 'tests', 'test') { Apaga (Join-Path $d.FullName $t) }
}
foreach ($d in 'Lib\test', 'Lib\idlelib', 'Lib\tkinter', 'Lib\turtledemo', 'tcl') {
    Apaga (Join-Path $runtime $d)
}

# --- 4. Codigo do JARVIS -----------------------------------------------------
Passo "Copiando o codigo -> $app"
Apaga $app
New-Item -ItemType Directory -Force $app | Out-Null
# robocopy: 0-7 = sucesso; /XD e /XF pulam testes, dados locais e caches
$xd = @('tests', 'logs', 'database', 'uploads', 'assets', '__pycache__', '.pytest_cache', '.ruff_cache', 'venv', '.venv')
$xf = @('*.db', '*.log', '*.pyc', '.env')
foreach ($pasta in 'backend', 'frontend') {
    & robocopy (Join-Path $raiz $pasta) (Join-Path $app $pasta) /E /NFL /NDL /NJH /NJS /NP /XD @xd /XF @xf | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy falhou em $pasta ($LASTEXITCODE)" }
}
# backend\database\README.md e afins: a pasta de dados e criada em %APPDATA%\JARVIS
foreach ($arq in 'env.example', 'LICENSE', 'README.md', 'VERSION') {
    Copy-Item (Join-Path $raiz $arq) $app
}
if ($Versao) { Set-Content -Path (Join-Path $app 'VERSION') -Value $Versao -Encoding ascii -NoNewline }

# Bytecode pre-compilado: a pasta instalada pode ser so leitura
Roda $py @('-m', 'compileall', '-q', '-j', '0', $app, $site)

# --- 5. Smoke test -----------------------------------------------------------
Passo 'Smoke test das libs'
$env:PYGAME_HIDE_SUPPORT_PROMPT = '1'
Roda $py @('-c', 'import textual, ollama, faster_whisper, PIL, dotenv, speech_recognition, pyaudio, edge_tts, pyttsx3, pygame, pyautogui, comtypes, pycaw, psutil, GPUtil, requests, ddgs, github, mcp, colorama; print(''libs OK'')')

# --- 6. MAX_PATH ---------------------------------------------------------------
# O ISCC (Inno Setup) nao aceita caminhos com mais de 260 caracteres e falha so
# com "The system cannot find the path specified". Clone numa pasta curta ou
# mapeie com "subst J: <pasta>" (o release.yml faz isso).
$longo = Get-ChildItem $runtime, $app -Recurse -File | Sort-Object { $_.FullName.Length } -Descending | Select-Object -First 1
if ($longo.FullName.Length -ge 260) {
    throw "caminho com $($longo.FullName.Length) caracteres (limite do ISCC: 259): $($longo.FullName). Use uma pasta mais curta ou 'subst J: $raiz'."
}
Write-Host "Maior caminho: $($longo.FullName.Length) caracteres"

$mb = [math]::Round(((Get-ChildItem $dist -Recurse -File -Exclude *.zip | Where-Object { $_.FullName -notlike "$cache*" } | Measure-Object Length -Sum).Sum / 1MB))
Write-Host "RUNTIME OK ($mb MB em dist\runtime + dist\app)"
