# 🎯 Skill: app_control.py

A skill `app_control.py` pertence à categoria **Automation**. Diferente de *scripts* básicos de automação que precisam de caminhos literais de atalhos, esta skill é o motor avançado responsável por prospectar, abrir, focar e encerrar de forma cirúrgica softwares instalados no Windows usando comandos de voz genéricos ou indiretos.

## 📝 Contrato

- **INTENT**: `APP_CONTROL`
- **PROMPT_TEXT**: Carregada no prompt global. O Jarvis aprende que deve ativá-la quando o usuário pedir para "Abrir", "Fechar" ou "Mostrar" entidades de software (como navegadores, jogos ou IDEs).

---

## ⚙️ Arquitetura e Funcionamento Interno

### 1. O Sub-Agente Autônomo (`_ask_ollama_app_expert`)

Analisar texto via Regex é frágil ("Jarvis, fecha esse Spotify pelo amor de Deus"). Para lidar com caos verbal, a skill cria um **Agente Especialista (Sub-Agent)**.

- Ela chama o Ollama por `core.llm.query_ollama(..., format="json")` (nunca `requests.post` direto: o `core.llm` normaliza o `OLLAMA_HOST`).
- Utiliza um *Prompt Rígido* (`APP_DECISION_PROMPT`) com `Temperatura = 0.1` que ordena que a IA só faça uma coisa: extrair o Verbo e o Alvo para um JSON enxuto.
- Se a frase for "Mostra a calculadora", o agente cospe: `{"action": "focus", "target": "calculadora"}`, limpando toda a complexidade semântica para o código Python processar.

### 2. Auto-Discovery de Softwares (`get_installed_apps`)

A skill não pede para o usuário configurar caminhos absolutos como `C:/Program Files/...`. Ela varre silenciosamente a máquina através de duas frentes de busca:

- **Modern Apps (UWP)**: Abre um túnel com o *PowerShell* (`Get-StartApps`) e converte os metadados brutos do Menu Iniciar do Windows 11 para JSON.
- **Classic Apps (Win32)**: Executa varreduras `os.walk` diretas nos diretórios físicos globais e de usuário (`%APPDATA%` e `%ProgramData%`) buscando estritamente atalhos `.lnk`.
- O resultado combinado (Dicionário de milhares de itens) é cravado na variável em memória RAM `INSTALLED_APPS_CACHE` para que futuras invocações de programas demorem milissegundos.

### 3. Sistema de Dedução (Fuzzy Match & Aliases)

Para maximizar o UX, o sistema perdoa nomes errados:

- **Fuzzy Match (`difflib`)**: Com um `cutoff` configurado para `0.6` (Sensibilidade alta para evitar falsos positivos). Se o usuário falar "Opera", o script sabe matematicamente que o executável oficial "Opera GX Browser.lnk" é o que ele quer.
- **Dicionário de Aliases (`ALIASES`)**: Um mapa puramente manual para gírias extremas. É aqui que o sistema mapeia o input "Zap" para o executável "WhatsApp", e o termo "Code" para "Visual Studio Code".

### 4. Gestão do Ciclo de Vida do Processo

A Skill não executa comandos às cegas. Ela implementa as 3 chaves de estado de janela (Ação de `close`, `focus` ou `open`):

- **Ação [OPEN] Inteligente**: Quando pedem para abrir, ela engatilha um `find_active_processes()`. Se o Spotify já existir rodando na barra de tarefas, **ela aborta a abertura** (para não gastar CPU criando processos clones) e força silenciosamente um comando de [FOCUS] na janela original. Se não estiver rodando, ela roda `os.startfile()` injetando `stdout=subprocess.DEVNULL` para silenciar apps (como o Discord/Notion) que dão _spam_ no terminal impedindo a visão de logs do Jarvis.
- **Ação [CLOSE] com nome exato**: Varre os PIDs com `psutil` e compara o **nome exato** do executável (sem `.exe`, sem maiúsculas) com o alvo ou com o `PROCESS_MAP` (ex.: "calculadora" vira "CalculatorApp"). Nunca por substring ("code" não pega "vscode-helper"). Alvo com menos de 3 letras é recusado, e processos do sistema e o próprio JARVIS nunca entram (`core/processes.py`, `PROTECTED`).
  - App **conhecido** (`PROCESS_MAP`/`ALIASES`) com um único executável: fecha direto, todas as instâncias (ex.: as abas do Chrome).
  - App **desconhecido** ou vários executáveis diferentes: tira um snapshot (PID + nome + hora de criação) e pede confirmação por `core.pending.arm`. Após o "sim", só o snapshot é encerrado (`processes.terminate_if_same`; PID reaproveitado fica de fora).
  - `close_now(target)`: encerra sem perguntar, para quem já confirmou (ex.: alerta de consumo crítico).
- **Ação [FOCUS] Mágica**: Usa um script customizado em *PowerShell* para levantar o objeto `.ComObject WScript.Shell`. O comando `AppActivate($p.MainWindowTitle)` obriga o kernel gráfico do Windows a trazer aquela janela submersa diretamente para a cara do usuário.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Expansão de Suporte de Nomes Específicos (`PROCESS_MAP`)**: Alguns aplicativos da Windows Store possuem um nome visível, mas um *Binary Name* completamente esotérico sob o capô da aba Detalhes no Gerenciador de Tarefas. Se você pedir para o Jarvis fechar o aplicativo "X" e ele disser "Fechei", mas o App continuar rodando, você deve descobrir o nome bruto daquele `.exe` e mapeá-lo manualmente no dicionário `PROCESS_MAP` no topo do código.
- **Último recurso ao abrir (sem shell)**: se o app não está nos atalhos nem no Modern Apps, o alvo só é tentado como programa do `PATH` (ex.: "notepad") quando é um nome simples (`[\w .+-]`, sem barra, aspas nem `&|;<>`) **e** `shutil.which` o encontra; aí roda `Popen([caminho])`, em lista. O texto vindo do LLM **nunca** vai para `shell=True` (Security Advisory GHSA-8j53: o antigo `Popen(target_raw, shell=True)` executava qualquer coisa que a voz/LLM produzisse).
