; jarvis.iss — instalador completo do J.A.R.V.I.S (Inno Setup 6.1+)
;
; Gera dist\JARVIS-Setup.exe a partir de dist\runtime (Python 3.11 com todas as
; libs) e dist\app (código), montados por installer\build_runtime.ps1.
; Quem instala não precisa de Python, pip nem compilador.
;
; O Ollama (servidor do LLM) é um programa à parte: se faltar, uma página do
; setup mostra o link oficial e espera ele ser instalado (checa a cada 2 s);
; depois o usuário escolhe o modelo num dropdown e o setup roda "ollama pull".
;
; Uso: iscc /DVersao=x.y.z installer\jarvis.iss
; Silencioso (CI): JARVIS-Setup.exe /VERYSILENT /SKIPOLLAMA [/MODEL=llama3.2]
; Atualização automática (agente no logon): /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SKIPOLLAMA /UPDATE

#ifndef Versao
  #define Versao "0.0.0-dev"
#endif
#define Icone AddBackslash(SourcePath) + "assets\jarvis.ico"

[Setup]
; AppId fixo: uma versão nova instala por cima da antiga, no mesmo lugar
AppId={{C73936E3-24F9-49BF-97C8-A9878023BAF6}
AppName=J.A.R.V.I.S
AppVersion={#Versao}
AppVerName=J.A.R.V.I.S {#Versao}
AppPublisher=Grolla05
AppPublisherURL=https://github.com/Grolla05/J.A.R.V.I.S-Just-A-Rather-Very-Intelligent-System
AppSupportURL=https://github.com/Grolla05/J.A.R.V.I.S-Just-A-Rather-Very-Intelligent-System/issues
AppUpdatesURL=https://github.com/Grolla05/J.A.R.V.I.S-Just-A-Rather-Very-Intelligent-System/releases
; Caminhos abaixo são relativos à raiz do repositório
SourceDir=..
OutputDir=dist
OutputBaseFilename=JARVIS-Setup
#if FileExists(Icone)
SetupIconFile=installer\assets\jarvis.ico
UninstallDisplayIcon={app}\jarvis.ico
#else
UninstallDisplayIcon={app}\runtime\python.exe
#endif
LicenseFile=LICENSE
; Sem admin por padrão (%LOCALAPPDATA%\Programs\JARVIS); o diálogo inicial
; permite instalar para todos os usuários (Arquivos de Programas)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\JARVIS
DefaultGroupName=J.A.R.V.I.S
DisableProgramGroupPage=yes
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
ptbr.TarefaPath=Adicionar o JARVIS ao PATH (rodar "jarvis" em qualquer terminal)
ptbr.GrupoOutras=Outras opções:
ptbr.TarefaAutostart=Iniciar o J.A.R.V.I.S com o Windows (agente na bandeja, Win+J abre)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:TarefaAutostart}"; GroupDescription: "{cm:GrupoOutras}"
Name: "path"; Description: "{cm:TarefaPath}"; GroupDescription: "{cm:GrupoOutras}"; Flags: unchecked

[InstallDelete]
; Atualização limpa: skills/libs removidas numa versão nova não ficam para trás
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\runtime"

[Files]
Source: "dist\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer\jarvis.cmd"; DestDir: "{app}"; Flags: ignoreversion
#if FileExists(Icone)
Source: "installer\assets\jarvis.ico"; DestDir: "{app}"; Flags: ignoreversion
#endif
; Configuração do usuário: copiada só na 1ª instalação e nunca apagada pelo
; desinstalador (o .env pode ter chaves do Obsidian/Spotify)
Source: "env.example"; DestDir: "{userappdata}\JARVIS"; DestName: ".env"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
#if FileExists(Icone)
Name: "{group}\J.A.R.V.I.S"; Filename: "{app}\jarvis.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\jarvis.ico"
Name: "{autodesktop}\J.A.R.V.I.S"; Filename: "{app}\jarvis.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\jarvis.ico"; Tasks: desktopicon
#else
Name: "{group}\J.A.R.V.I.S"; Filename: "{app}\jarvis.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python.exe"
Name: "{autodesktop}\J.A.R.V.I.S"; Filename: "{app}\jarvis.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python.exe"; Tasks: desktopicon
#endif
Name: "{group}\Configuração (.env)"; Filename: "{userappdata}\JARVIS\.env"
Name: "{group}\{cm:UninstallProgram,J.A.R.V.I.S}"; Filename: "{uninstallexe}"

[Registry]
; Agente residente (pythonw, sem janela) no logon: segura o Win+J e reabre a TUI.
; O /config e o ícone da bandeja ligam/desligam este mesmo valor depois.
; --logon: só nessa subida o agente procura versão nova (backend\core\updater.py).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JARVIS"; ValueData: """{app}\runtime\pythonw.exe"" ""{app}\app\backend\agent.py"" --logon"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\backend\agent.py"""; WorkingDir: "{app}\app\backend"; Tasks: autostart; Flags: nowait skipifsilent
; Atualização automática (/UPDATE, aberta pelo agente no logon): o agente se
; fechou para liberar o runtime; reabre ele sem --logon (não verifica de novo)
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\backend\agent.py"""; WorkingDir: "{app}\app\backend"; Check: EhAtualizacao; Flags: nowait runasoriginaluser
Filename: "{app}\jarvis.cmd"; Description: "{cm:LaunchProgram,J.A.R.V.I.S}"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
; Fecha o agente antes de apagar os arquivos (o pythonw.exe dele trava o runtime)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\runtime\*' } | Stop-Process -Force"""; Flags: runhidden waituntilterminated; RunOnceId: "FechaAgente"

[UninstallDelete]
; __pycache__ e afins criados depois da instalação
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\runtime"
; Perfil "JARVIS" do Windows Terminal (logo na aba), gravado pelo app no 1º boot
Type: filesandordirs; Name: "{localappdata}\Microsoft\Windows Terminal\Fragments\JARVIS"

[Code]
const
  URL_OLLAMA = 'https://ollama.com/download';
  NAO_BAIXAR = '';

var
  PaginaOllama: TWizardPage;
  StatusOllama: TNewStaticText;
  PaginaModelo: TWizardPage;
  ComboModelo: TNewComboBox;
  ChkVisao: TNewCheckBox;
  InfoModelo: TNewStaticText;
  Modelos: TArrayOfString;      // tag do Ollama de cada item do combo ('' = não baixar)
  Rotulos: TArrayOfString;      // texto base de cada item do combo
  TimerId: LongWord;
  ListaCarregada: Boolean;

function SetTimer(hWnd, nIDEvent, uElapse, lpTimerFunc: LongWord): LongWord;
  external 'SetTimer@user32.dll stdcall';
function KillTimer(hWnd, uIDEvent: LongWord): BOOL;
  external 'KillTimer@user32.dll stdcall';

// ---------------------------------------------------------------------------
// Parâmetros de linha de comando
// ---------------------------------------------------------------------------
function TemParam(Nome: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/' + Nome) = 0 then begin
      Result := True;
      exit;
    end;
end;

// /UPDATE: setup silencioso aberto pelo próprio agente (core/updater.py)
function EhAtualizacao: Boolean;
begin
  Result := TemParam('UPDATE');
end;

function PularOllama: Boolean;
begin
  Result := TemParam('SKIPOLLAMA');
end;

// ---------------------------------------------------------------------------
// Detecção do Ollama (mesma ideia de backend\core\ollama_server.py)
// ---------------------------------------------------------------------------
// Procura ollama.exe em cada pasta de uma lista separada por ';'
function ProcuraNoPath(Lista: String): String;
var
  P: Integer;
  Dir: String;
begin
  Result := '';
  Lista := Lista + ';';
  while Lista <> '' do begin
    P := Pos(';', Lista);
    Dir := Trim(Copy(Lista, 1, P - 1));
    Delete(Lista, 1, P);
    if Dir <> '' then begin
      Dir := RemoveQuotes(Dir);
      if FileExists(AddBackslash(Dir) + 'ollama.exe') then begin
        Result := AddBackslash(Dir) + 'ollama.exe';
        exit;
      end;
    end;
  end;
end;

function OllamaExe: String;
var
  Valor: String;
begin
  Result := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe');
  if FileExists(Result) then exit;
  Result := ExpandConstant('{commonpf64}\Ollama\ollama.exe');
  if FileExists(Result) then exit;
  // PATH do processo do setup fica velho depois que o Ollama é instalado:
  // lê também o PATH atual do registro (usuário e máquina)
  Result := ProcuraNoPath(GetEnv('PATH'));
  if Result <> '' then exit;
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Valor) then begin
    Result := ProcuraNoPath(ExpandConstant(Valor));
    if Result <> '' then exit;
  end;
  if RegQueryStringValue(HKEY_LOCAL_MACHINE,
     'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Valor) then
    Result := ProcuraNoPath(Valor);
end;

function OllamaInstalado: Boolean;
begin
  Result := OllamaExe <> '';
end;

// ---------------------------------------------------------------------------
// Página 1: "Ollama necessário" — espera a instalação
// ---------------------------------------------------------------------------
procedure ParaTimer;
begin
  if TimerId <> 0 then begin
    KillTimer(0, TimerId);
    TimerId := 0;
  end;
end;

procedure AtualizaOllama(Automatico: Boolean);
begin
  if OllamaInstalado then begin
    ParaTimer;
    StatusOllama.Caption := 'Ollama detectado! Clique em Avançar para escolher o modelo.';
    StatusOllama.Font.Color := clGreen;
    WizardForm.NextButton.Enabled := True;
    // Avança sozinho para a escolha do modelo
    if Automatico and (WizardForm.CurPageID = PaginaOllama.ID) then
      WizardForm.NextButton.OnClick(WizardForm.NextButton);
  end else begin
    StatusOllama.Caption := 'Aguardando a instalação do Ollama... (verificando a cada 2 segundos)';
    StatusOllama.Font.Color := clMaroon;
    WizardForm.NextButton.Enabled := False;
  end;
end;

procedure TimerOllama(H, Msg, IdEvento, Tempo: LongWord);
begin
  AtualizaOllama(True);
end;

procedure AbreLinkOllama(Sender: TObject);
var
  Erro: Integer;
begin
  ShellExecAsOriginalUser('open', URL_OLLAMA, '', '', SW_SHOWNORMAL, ewNoWait, Erro);
end;

procedure VerificarAgora(Sender: TObject);
begin
  AtualizaOllama(True);
end;

procedure CriaPaginaOllama;
var
  Texto, Link: TNewStaticText;
  BtnAbrir, BtnVerificar: TNewButton;
begin
  PaginaOllama := CreateCustomPage(wpSelectTasks, 'Ollama necessário',
    'O J.A.R.V.I.S usa o Ollama para rodar a inteligência artificial localmente.');

  Texto := TNewStaticText.Create(PaginaOllama);
  Texto.Parent := PaginaOllama.Surface;
  Texto.AutoSize := False;
  Texto.WordWrap := True;
  Texto.Width := PaginaOllama.SurfaceWidth;
  Texto.Height := ScaleY(56);
  Texto.Caption := 'O Ollama não foi encontrado neste computador. Baixe e instale o Ollama ' +
    'pelo link oficial abaixo. Deixe este instalador aberto: assim que o Ollama ' +
    'terminar de instalar, o setup percebe sozinho e segue para a escolha do modelo.';

  Link := TNewStaticText.Create(PaginaOllama);
  Link.Parent := PaginaOllama.Surface;
  Link.Top := Texto.Top + Texto.Height + ScaleY(8);
  Link.Caption := URL_OLLAMA;
  Link.Cursor := crHand;
  Link.Font.Color := clBlue;
  Link.Font.Style := [fsUnderline];
  Link.OnClick := @AbreLinkOllama;

  BtnAbrir := TNewButton.Create(PaginaOllama);
  BtnAbrir.Parent := PaginaOllama.Surface;
  BtnAbrir.Top := Link.Top + Link.Height + ScaleY(12);
  BtnAbrir.Width := ScaleX(200);
  BtnAbrir.Height := ScaleY(25);
  BtnAbrir.Caption := 'Abrir página de download';
  BtnAbrir.OnClick := @AbreLinkOllama;

  BtnVerificar := TNewButton.Create(PaginaOllama);
  BtnVerificar.Parent := PaginaOllama.Surface;
  BtnVerificar.Top := BtnAbrir.Top;
  BtnVerificar.Left := BtnAbrir.Left + BtnAbrir.Width + ScaleX(8);
  BtnVerificar.Width := ScaleX(140);
  BtnVerificar.Height := ScaleY(25);
  BtnVerificar.Caption := 'Verificar agora';
  BtnVerificar.OnClick := @VerificarAgora;

  StatusOllama := TNewStaticText.Create(PaginaOllama);
  StatusOllama.Parent := PaginaOllama.Surface;
  StatusOllama.Top := BtnAbrir.Top + BtnAbrir.Height + ScaleY(16);
  StatusOllama.Font.Style := [fsBold];
  StatusOllama.Caption := '';
end;

// ---------------------------------------------------------------------------
// Página 2: escolha do modelo (dropdown)
// ---------------------------------------------------------------------------
procedure AddModelo(Tag, Rotulo: String);
var
  N: Integer;
begin
  N := GetArrayLength(Modelos);
  SetArrayLength(Modelos, N + 1);
  SetArrayLength(Rotulos, N + 1);
  Modelos[N] := Tag;
  Rotulos[N] := Rotulo;
  ComboModelo.Items.Add(Rotulo);
end;

procedure CriaPaginaModelo;
var
  Texto: TNewStaticText;
begin
  PaginaModelo := CreateCustomPage(PaginaOllama.ID, 'Modelo de IA',
    'Escolha o modelo de linguagem que o J.A.R.V.I.S vai usar.');

  Texto := TNewStaticText.Create(PaginaModelo);
  Texto.Parent := PaginaModelo.Surface;
  Texto.AutoSize := False;
  Texto.WordWrap := True;
  Texto.Width := PaginaModelo.SurfaceWidth;
  Texto.Height := ScaleY(42);
  Texto.Caption := 'O modelo é baixado pelo Ollama no fim da instalação (precisa de internet). ' +
    'Modelos maiores respondem melhor, mas pedem mais RAM/VRAM. Dá para trocar depois ' +
    'no arquivo .env (OLLAMA_MODEL).';

  ComboModelo := TNewComboBox.Create(PaginaModelo);
  ComboModelo.Parent := PaginaModelo.Surface;
  ComboModelo.Top := Texto.Top + Texto.Height + ScaleY(8);
  ComboModelo.Width := PaginaModelo.SurfaceWidth;
  ComboModelo.Style := csDropDownList;
  AddModelo('llama3.2', 'llama3.2 — Llama 3.2 3B (~2,0 GB) — recomendado, leve');
  AddModelo('llama3.1:8b', 'llama3.1:8b — Llama 3.1 8B (~4,9 GB) — mais capaz');
  AddModelo('qwen2.5:7b', 'qwen2.5:7b — Qwen 2.5 7B (~4,7 GB) — ótimo em português');
  AddModelo('mistral', 'mistral — Mistral 7B (~4,1 GB)');
  AddModelo('gemma2:9b', 'gemma2:9b — Gemma 2 9B (~5,4 GB) — pede GPU boa');
  AddModelo('phi3', 'phi3 — Phi-3 Mini 3.8B (~2,2 GB) — PCs modestos');
  AddModelo(NAO_BAIXAR, 'Não baixar agora (escolho depois)');
  ComboModelo.ItemIndex := 0;

  ChkVisao := TNewCheckBox.Create(PaginaModelo);
  ChkVisao.Parent := PaginaModelo.Surface;
  ChkVisao.Top := ComboModelo.Top + ComboModelo.Height + ScaleY(12);
  ChkVisao.Width := PaginaModelo.SurfaceWidth;
  ChkVisao.Height := ScaleY(17);
  ChkVisao.Caption := 'Baixar também o modelo de visão (moondream, ~1,7 GB) para analisar imagens';

  InfoModelo := TNewStaticText.Create(PaginaModelo);
  InfoModelo.Parent := PaginaModelo.Surface;
  InfoModelo.Top := ChkVisao.Top + ChkVisao.Height + ScaleY(12);
  InfoModelo.Caption := '';
end;

// "llama3.2" no Ollama aparece como "llama3.2:latest"
function TagCompleta(Tag: String): String;
begin
  Result := Tag;
  if Pos(':', Result) = 0 then
    Result := Result + ':latest';
end;

// Garante o servidor no ar (o app do Ollama costuma subir sozinho; se não, "ollama serve")
procedure GaranteServidor(Exe: String);
var
  Rc: Integer;
begin
  if Exec(Exe, 'list', '', SW_HIDE, ewWaitUntilTerminated, Rc) and (Rc = 0) then
    exit;
  Exec(Exe, 'serve', '', SW_HIDE, ewNoWait, Rc);
  Sleep(3000);
end;

// Marca "(já instalado)" nos modelos que o "ollama list" já mostra
procedure CarregaModelosInstalados;
var
  Exe, Tmp, Nome: String;
  Linhas: TArrayOfString;
  I, J, Rc, P: Integer;
  Algum: Boolean;
begin
  Exe := OllamaExe;
  if Exe = '' then exit;
  WizardForm.NextButton.Enabled := False;
  InfoModelo.Caption := 'Consultando os modelos já instalados...';
  WizardForm.Refresh;
  GaranteServidor(Exe);
  Tmp := ExpandConstant('{tmp}\ollama_list.txt');
  Exec(ExpandConstant('{cmd}'), '/C ""' + Exe + '" list > "' + Tmp + '" 2>&1"', '',
    SW_HIDE, ewWaitUntilTerminated, Rc);
  Algum := False;
  if LoadStringsFromFile(Tmp, Linhas) then
    for I := 1 to GetArrayLength(Linhas) - 1 do begin   // linha 0 = cabeçalho
      Nome := Trim(Linhas[I]);
      P := Pos(' ', Nome);
      if P > 0 then Nome := Copy(Nome, 1, P - 1);
      for J := 0 to GetArrayLength(Modelos) - 1 do
        if (Modelos[J] <> NAO_BAIXAR) and (CompareText(TagCompleta(Modelos[J]), Nome) = 0) then begin
          ComboModelo.Items[J] := Rotulos[J] + '  (já instalado)';
          Algum := True;
        end;
    end;
  if Algum then
    InfoModelo.Caption := 'Modelos marcados como "já instalado" não serão baixados de novo.'
  else
    InfoModelo.Caption := '';
  WizardForm.NextButton.Enabled := True;
end;

function ModeloEscolhido: String;
begin
  if WizardSilent then
    Result := ExpandConstant('{param:MODEL|}')
  else if (ComboModelo <> nil) and (ComboModelo.ItemIndex >= 0) then
    Result := Modelos[ComboModelo.ItemIndex]
  else
    Result := NAO_BAIXAR;
end;

// ---------------------------------------------------------------------------
// Pós-instalação: ollama pull + OLLAMA_MODEL no .env
// ---------------------------------------------------------------------------
// python-dotenv usa o último valor de uma chave repetida: acrescentar a linha
// no fim troca o modelo sem reescrever (nem recodificar) o resto do .env
procedure GravaModeloEnv(Modelo: String);
var
  Arq: String;
begin
  Arq := ExpandConstant('{userappdata}\JARVIS\.env');
  SaveStringToFile(Arq, #13#10 + '# Modelo escolhido no instalador' + #13#10 +
    'OLLAMA_MODEL=' + Modelo + #13#10, True);
end;

function BaixaModelo(Exe, Modelo: String): Boolean;
var
  Rc: Integer;
begin
  WizardForm.StatusLabel.Caption := 'Baixando o modelo ' + Modelo + ' com o Ollama (acompanhe na janela aberta)...';
  WizardForm.Refresh;
  // Janela visível: o usuário vê a barra de progresso do próprio Ollama
  Result := Exec(Exe, 'pull ' + Modelo, '', SW_SHOWNORMAL, ewWaitUntilTerminated, Rc) and (Rc = 0);
  if not Result then
    SuppressibleMsgBox('Não foi possível baixar o modelo "' + Modelo + '" (código ' + IntToStr(Rc) + ').' + #13#10 +
      'Depois, rode num terminal: ollama pull ' + Modelo, mbError, MB_OK, IDOK);
end;

procedure ConfiguraOllama;
var
  Exe, Modelo: String;
begin
  if PularOllama then exit;
  Exe := OllamaExe;
  if Exe = '' then exit;
  Modelo := ModeloEscolhido;
  if Modelo <> NAO_BAIXAR then begin
    GaranteServidor(Exe);
    if BaixaModelo(Exe, Modelo) then
      GravaModeloEnv(Modelo);
  end;
  if (not WizardSilent) and (ChkVisao <> nil) and ChkVisao.Checked then begin
    GaranteServidor(Exe);
    BaixaModelo(Exe, 'moondream');
  end;
end;

// ---------------------------------------------------------------------------
// PATH (igual ao OhmFlow): usuário (HKCU) ou máquina, conforme o modo
// ---------------------------------------------------------------------------
procedure RaizPath(var Raiz: Integer; var Chave: String);
begin
  if IsAdminInstallMode then begin
    Raiz := HKEY_LOCAL_MACHINE;
    Chave := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end else begin
    Raiz := HKEY_CURRENT_USER;
    Chave := 'Environment';
  end;
end;

procedure AdicionaPath;
var
  Raiz: Integer;
  Chave, Path, Dir: String;
begin
  RaizPath(Raiz, Chave);
  Dir := ExpandConstant('{app}');
  if not RegQueryStringValue(Raiz, Chave, 'Path', Path) then
    Path := '';
  if Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';') > 0 then
    exit;
  if (Path <> '') and (Path[Length(Path)] <> ';') then
    Path := Path + ';';
  RegWriteExpandStringValue(Raiz, Chave, 'Path', Path + Dir);
end;

procedure RemovePath;
var
  Raiz: Integer;
  Chave, Path, Dir: String;
begin
  RaizPath(Raiz, Chave);
  Dir := ExpandConstant('{app}');
  if not RegQueryStringValue(Raiz, Chave, 'Path', Path) then
    exit;
  Path := ';' + Path + ';';
  if StringChangeEx(Path, ';' + Dir + ';', ';', True) > 0 then
    RegWriteExpandStringValue(Raiz, Chave, 'Path', Copy(Path, 2, Length(Path) - 2));
end;

// ---------------------------------------------------------------------------
// Eventos do assistente
// ---------------------------------------------------------------------------
procedure InitializeWizard;
begin
  CriaPaginaOllama;
  CriaPaginaModelo;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = PaginaOllama.ID then
    Result := PularOllama or OllamaInstalado
  else if PageID = PaginaModelo.ID then
    Result := PularOllama;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = PaginaOllama.ID then begin
    AtualizaOllama(False);
    if (not OllamaInstalado) and (TimerId = 0) then
      TimerId := SetTimer(0, 0, 2000, CreateCallback(@TimerOllama));
  end else
    ParaTimer;

  if (CurPageID = PaginaModelo.ID) and (not ListaCarregada) then begin
    ListaCarregada := True;
    CarregaModelosInstalados;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PaginaOllama.ID then
    Result := OllamaInstalado;
end;

// Atualização por cima: o agente residente (pythonw do runtime antigo) trava os
// arquivos que o [InstallDelete] apaga. Fecha só os pythonw desta instalação.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Result := '';
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Get-Process pythonw -ErrorAction SilentlyContinue | ' +
       'Where-Object { $_.Path -like ''' + ExpandConstant('{app}') + '\runtime\*'' } | Stop-Process -Force"',
       '', SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    if WizardIsTaskSelected('path') then
      AdicionaPath;
    ConfiguraOllama;
  end;
end;

procedure DeinitializeSetup;
begin
  ParaTimer;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dados: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    RemovePath;
    Dados := ExpandConstant('{userappdata}\JARVIS');
    if (not UninstallSilent) and DirExists(Dados) and
       (MsgBox('Apagar também seus dados do J.A.R.V.I.S (histórico, banco, logs e o .env com suas chaves)?' + #13#10 +
        Dados, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Dados, True, True, True);
  end;
end;
