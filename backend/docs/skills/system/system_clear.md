# 🧹 Skill: system_clear.py

A skill `system_clear.py` atua na categoria **System**. O objetivo dela é atuar como o "Zelador" autônomo da máquina, automatizando rotinas exaustivas de TI como esvaziar a lixeira de forma silenciosa, expurgar cache de sistema corrompido e até mesmo desinstalar softwares completos apenas pela voz.

## 📝 Contrato

- **INTENT**: `SYSTEM_CLEANUP`
- **PROMPT_TEXT**: Ativada instantaneamente quando o usuário profere verbos de destruição de arquivos (Desinstalar, remover, apagar, esvaziar lixeira, limpar temporários).

---

## ⚙️ Arquitetura e Engenharia Interna

### 1. O Sub-Agente de Limpeza (`_ask_ollama_cleanup_expert`)

O cérebro dedica um Agente Neutro para converter o caos da fala humana em 3 comandos rígidos.

- A Prompt `CLEANUP_DECISION_PROMPT` com Temperatura `0.1` amarra a resposta da IA em um JSON restrito contendo apenas `{"action": "recycle_bin" | "temp_files" | "uninstall_app"}`.
- O campo adicional `"target"` é extraído. Se o usuário disser *"Deleta o Chrome daqui"*, a IA empacota `"action": "uninstall_app", "target": "chrome"`.

### 2. Algoritmo de Busca de Apps (Fuzzy Match Reutilizado)

Se a ação for de desinstalação, a skill não pode mandar o Windows apagar "Chrome" se o nome do pacote oficial no sistema for "Google Chrome".

- Ela injeta o comando `Get-StartApps | Select-Object Name` no **PowerShell** para indexar todo o registro de programas modernos.
- Acopla o dicionário `ALIASES` (ex: "Zap" -> "WhatsApp") e aplica o algoritmo de similaridade matemática `difflib.get_close_matches(cutoff=0.5)`. Esse *cutoff* baixo de 50% de similaridade garante que mesmo que o usuário gagueje, o Jarvis vai achar o alvo certo antes de tentar desinstalar.

### 3. Ações Destrutivas (Execução Física)

#### 🪣 Esvaziamento Fantasma de Lixeira (`empty_recycle_bin`)

Programadores amadores esvaziam a lixeira usando atalhos de teclado ou comandos de PowerShell lentos. O Jarvis usa acesso direto ao Kernel via API C.

- Invoca `ctypes.windll.shell32.SHEmptyRecycleBinW`.
- O truque fatal está no injetor de binários `flags = 1 | 2 | 4`:
  - `1` (SHERB_NOCONFIRMATION): Oculta o popup "Tem certeza que deseja excluir?".
  - `2` (SHERB_NOPROGRESSUI): Oculta a barra de progresso.
  - `4` (SHERB_NOSOUND): Impede o Windows de tocar aquele som de papel amassando.
- O resultado é uma lixeira que evapora milissegundos após você pedir, em total silêncio.

#### 🌪️ Expurgo de Arquivos Temporários (`clean_temp_files`)

Não utiliza limpadores de terceiros. A skill lê a variável de ambiente nativa global do Windows (`os.environ.get('TEMP')`).

- Ela gera uma lista estrita de arquivos via `glob.glob`.
- Executa um loop destrutivo: Se for arquivo solto, aplica `os.remove(f)`. Se for pasta, usa recursividade profunda com `shutil.rmtree(f)`.
- **Prevenção de Crash**: Como a pasta Temp sempre tem arquivos travados por apps abertos (como o Chrome no momento), cada deleção é envolta num bloco `try/except: pass`. O Jarvis apaga o que pode, ignora o que está bloqueado e no fim retorna o contador de quantos lixos eliminou ("Limpeza concluída. 320 itens removidos").

#### 💣 O Desinstalador Autônomo Winget (`uninstall_app`)

A skill executa desinstalações limpas via terminal.

- Puxa o Gerenciador de Pacotes nativo do Windows 11 disparando `winget uninstall --name "NOME_REAL" --source winget`.
- **Automação de Licenças**: Adiciona a flag `--accept-source-agreements`. Sem ela, o Winget travaria o terminal oculto perguntando "[Y/N]" na primeira vez que rodasse, bugando a IA pra sempre.
- **O Fallback Elegante (UI)**: O *Winget* só desinstala o que foi instalado por ele ou pela Loja. Se você pedir para desinstalar um app velho (retornando um código de Erro pelo `subprocess.run`), o Jarvis não desiste. Ele engatilha a abertura automática da interface gráfica clássica do Windows disparando `appwiz.cpl` (Painel de Controle -> Adicionar/Remover Programas), e avisa: *"Não consegui remover automaticamente. Abri o painel de controle para você finalizar."*

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Permissões de Administrador**: O comando de `winget uninstall` para certos softwares de sistema operacional irá falhar miseravelmente e ativar o Fallback para o Painel de Controle se o terminal que roda o JARVIS não estiver rodando com privilégios de Administrador. Se você planeja usar o Jarvis como *SysAdmin* de remoção, garanta que o atalho que roda o Python esteja marcado como "Executar como Administrador".
- **Cutoff de Fuzzy Match (`0.5`)**: A desinstalação de apps trabalha com um *cutoff* muito mais baixo e perigoso (50%) do que a Skill de Abrir Apps (60%). O motivo é que geralmente queremos apagar apps com nomes obscuros, e o usuário pode errar severamente a pronúncia de uma ferramenta de "Bloatware" da Asus, por exemplo. Mas cuidado: se você não validar o retorno auditivo do Jarvis, ele pode tentar desinstalar o "Discord" se você gaguejar querendo apagar o "Discover".
