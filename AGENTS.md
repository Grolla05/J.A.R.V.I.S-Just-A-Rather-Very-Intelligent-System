# J.A.R.V.I.S — Instruções para o Codex Project

## O que é este projeto

O **J.A.R.V.I.S.** é um assistente virtual 100% autônomo inspirado no JARVIS do Iron Man. É um **desktop app nativo para Windows** — não uma aplicação web. O frontend React roda embutido numa janela PyWebView sem browser externo. O backend Python é o cérebro cognitivo. Os dois se comunicam via IPC direto (`window.pywebview.api`), sem REST ou HTTP.

**Repositório:** `github.com/Jarvis-Project-2026/J.A.R.V.I.S`
**Dev:** Felipe Grolla Freitas

---

## Workflow obrigatório de funcionamento

1 -> A partir do prompt gere os testes para verificação da feature antes mesmo de começar a desenvolver, todos os testes unitários tem que ser criados dentro da pasta tests na raiz da frente do projeto ou seja dentro de backend ou frontend, caso a pasta não exista crie ela no respectivo lugar.
2 -> Com os testes escritos explore as opções e caminhos nos quais podem ser seguidos para o desenvolvimento
3 -> Escreva o plano de ação para implementar a feature
4 -> Desenvolva o plano proposto, dividindo a atividade do plano em task's
5 -> Após o desenvolvimento execute os testes escritos no passo 1, para validar oque foi gerado, não é necessário rodar a suite inteira de testes e sim somente os testes relacionado a feature implementada, se não passar em algum teste propostos para feature, identifique oque deu problema e conserte e rode o teste novamente
6 -> Após ter ocorrido tudo corretamente por favor crie, edite caso já exista, o arquivo CHANGES.md na raiz do projeto, no qual este por sua vez deve documentar tudo nos mínimos detalhes do que foi feito
7 -> Após ter ter documentado tudo no CHANGES.md prepare para gerar o commit, baseado nas alterações documentadas no CHANGES.md, ou seja deve ser feito baseado neste arquivo o commit mensage, mas espere a validação e comando do usuário
8 -> Com a validação do usuário siga o processo de commit -> push (sync changes) -> Pull Request. Não é necessário abrir uma branch nova para cada feature, apenas utilize a branch Grolla para realizar este processo.
9 -> Após o commit feito por favor limpe o arquivo CHANGES.md, ou seja apague, o conteúdo dele.

---

## Boas práticas

Sempre que for responder ou realizar qualquer prompt é obrigatório que utilize a skill caveman no desenvolvimento da task
também na hora de fazer/abrir o PR e commit, ccoloque sempre a tag de Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>.

---

## Estrutura do Repositório

```
J.A.R.V.I.S/
├── backend/                 ← Python (cérebro cognitivo)
│   ├── main.py              ← Orquestrador Central + PyWebView
│   ├── core/                ← Infraestrutura
│   │   ├── state.py         ← Estado global (sys_monitor, pending_critical_action)
│   │   ├── llm.py           ← Cliente Ollama oficial (query_ollama / stream)
│   │   ├── hardware.py      ← scan_system_hardware() via PowerShell WMI
│   │   ├── alerts.py        ← process_system_alert() + PROCESS_JUDGEMENT_CACHE
│   │   ├── prompts.py       ← load_prompt() com cache e string.Template
│   │   ├── bridge.py        ← JarvisAPI — Bridge IPC com o frontend
│   │   ├── config.py        ← Settings Singleton (.env, paths)
│   │   ├── database.py      ← DatabaseManager SQLite (4 tabelas)
│   │   ├── logger.py        ← JarvisLogger (colorama + multiplexing)
│   │   ├── obsidian.py      ← RAG sobre vault Obsidian via MCP
│   │   ├── skill_loader.py  ← Auto-discovery de skills (plug-and-play)
│   │   └── SystemInfo.py    ← psutil — monitoramento de hardware
│   ├── services/            ← Serviços cognitivos
│   │   ├── brain.py         ← Orquestrador fino (roteador de comandos)
│   │   ├── intent.py        ← classify_intent() + is_skill_enabled()
│   │   ├── chat.py          ← ask_local_ai() + ask_local_ai_stream()
│   │   ├── memory.py        ← extract_fact_to_memory() → Obsidian
│   │   ├── listen.py        ← Ear Singleton (STT + Wake Word "Jarvis")
│   │   └── speak.py         ← TTS (edge-tts → fallback pyttsx3)
│   ├── skills/
│   │   ├── automation/      ← app_control, audio_control, keyboard_control,
│   │   │                       screen_control, work_macros
│   │   └── system/          ← status_report, system_clear, system_security
│   └── prompts/             ← Arquivos .md de prompt (system_prompt, classify_intent, etc.)
│
├── frontend/                ← React 19 + Vite (HUD interface)
│   ├── src/
│   │   ├── App.jsx          ← State Machine (activeMode, jarvisState, isCritical)
│   │   ├── index.css        ← .liquid-glass, .hud-critical-mode
│   │   ├── components/
│   │   │   ├── CHAT/        ← ChatPanel, MessageList, ChatInput, ChatSidebar, MarkdownComponents
│   │   │   ├── CORE/        ← LiquidAuraReactor (canvas único, 30fps), ReactorMath
│   │   │   └── TELEMETRY/   ← LiveTelemetry, TelemetryWidget, CpuRamWidget, NetworkWidget
│   │   ├── hooks/
│   │   │   └── BridgeAPI.js ← Único ponto de saída React → Python
│   │   └── utils/
│   │       └── motion.js    ← Presets de spring physics
│   └── dist/                ← Build para produção (lido pelo PyWebView)
│
└── boot.bat                 ← Sobe tudo com um clique (Windows)
```

---

## Backend — Regras e Convenções

### Logging

- **Proibido `print()`** em qualquer arquivo. Sempre: `from core import log` → `log.info()` / `log.warning()` / `log.critical()`
- `log.debug()` para loops, streaming e tracking de variáveis
- `log.critical()` apenas antes de `sys.exit(1)`

### Ollama (LLM)

- **Proibido `requests.post`** para chamar o Ollama diretamente nos serviços principais
- Sempre usar: `from core.llm import query_ollama, query_ollama_stream`
- `query_ollama(messages, format='json', temperature=0)` para classificação/extração
- `query_ollama_stream(messages, temperature=0.7)` para chat no frontend

### Prompts

- **Proibido hardcodar prompts como strings Python** dentro de arquivos `.py`
- Sempre criar um arquivo `.md` em `backend/prompts/` e usar: `from core.prompts import load_prompt`
- Variáveis no `.md`: sintaxe `$variavel` (string.Template)
- `load_prompt("arquivo.md", variavel=valor)` → retorna a string com substituição

### Comunicação com o Frontend (evaluate_js)

- **Escape obrigatório** antes de qualquer `evaluate_js` com texto variável:

  ```python
  safe = text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
  ```

- Uma aspa não escapada na resposta do Ollama **paralisa o frontend silenciosamente**

### Threading

- Toda função nova na `JarvisAPI` que faz I/O pesado **deve** rodar em `threading.Thread(daemon=True)`
- Toda nova thread em `main.py` **deve** ter `daemon=True` (garante que `os._exit(0)` a destrua)
- A `speech_lock` do `speak.py` **nunca deve ser removida**

### Banco de Dados — SQLite (`database.py`)

- Toda operação SQL **deve** terminar com `conn.close()` em bloco `finally`
- Omitir `close()` trava o loop PyWebView na próxima iteração
- Novas colunas: sempre adicionar fallback `PRAGMA table_info` + `ALTER TABLE` para bancos antigos
- Arquivo gerado em `backend/database/jarvis_memory.db` com 4 tabelas: `config`, `history`, `sessions`, `hardware`
- UPSERT via `ON CONFLICT(key) DO UPDATE SET` — nunca checar existência manualmente antes de inserir
- Acesso: `from core.database import db` → `db.log_interaction()`, `db.get_config()`, `db.save_config()`, `db.update_hardware_spec()`

### Banco de Dados — Obsidian (Memória de Longo Prazo)

- O Obsidian funciona como cofre semântico de **longo prazo** — não substitui o SQLite, complementa
- Memórias efêmeras da IA ficam em `Projetos/J.A.R.V.I.S/Memória/{key}.md` (sem emojis no path — urllib quebra)
- **Nunca sobrescreve** notas existentes — preserva edições manuais do usuário no vault
- RAG em 2 camadas via `core/obsidian.py`:
  - **Camada 1**: palavras de perfil pessoal (`_PROFILE_KEYWORDS`) → puxa `Sobre mim.md` inteiro
  - **Camada 2**: busca semântica via MCP `obsidian_simple_search` → retorna arquivo de maior score
- Acesso: `from core.obsidian import obsidian, get_vault_context`
  - `obsidian.save_memory(key, value)` → salva nota no vault
  - `obsidian.get_memory(key)` → lê primeira linha útil da nota
  - `get_vault_context(text)` → retorna `(filename, context_str)` para injetar no prompt
- Paths com acentos **devem** passar por `urllib.parse.quote(..., encoding="utf-8")` — sem isso: 404

### Estado Global

- `sys_monitor` e `pending_critical_action` vivem em `core/state.py`
- Acesso: `import core.state as state` → `state.sys_monitor` / `state.pending_critical_action`
- **Nunca** instanciar `SystemInfo()` novamente em outros módulos

### Skills — Contrato Obrigatório

Toda skill **deve** expor:

```python
INTENT = "NOME_UNICO"      # Primary key no dicionário global
PROMPT_TEXT = "..."        # Alimenta o system prompt do LLM
CATEGORY = "automation"    # Herdado automaticamente da pasta-mãe

def execute(entity: str, command: str) -> str:
    # entity: objeto da ação ("spotify", "50", etc.)
    # command: frase original do usuário
    return "resposta do Jarvis"
```

> ⚠️ `execute()` agora recebe **2 argumentos**: `entity` e `command`. Skills antigas com 1 argumento quebrarão o routing.

### Configurações

- **Nunca** usar `os.getenv("CHAVE")` diretamente em `brain.py`, `bridge.py` ou skills
- Toda variável do `.env` deve ser declarada em `core/config.py` como atributo da classe `Settings`

---

## Frontend — Regras e Convenções

### As Três Leis (invioláveis)

1. **Spring Physics absoluta** — `ease` e `linear` são proibidos. Todo elemento interativo usa Framer Motion com `type: "spring"`.

   ```tsx
   transition={{ type: "spring", stiffness: 400, damping: 25 }}
   ```

2. **Translucidez, sem blur** — backplates usam `rgba` translúcido. **`backdrop-filter` é proibido** (custo de RAM/GPU no WebView2). Nada de blur pesado, `mix-blend` ou sombras empilhadas.

   ```css
   background: rgba(255,255,255,0.05);
   border: 1px solid rgba(255,255,255,0.1);
   ```

3. **Zero cortes secos** — componentes que entram/saem do DOM usam `AnimatePresence` com fade + translação Y/X.

### Modos de Interface (`activeMode`)

- `talk` → LiquidAuraReactor centralizado, `JarvisSubtitles` visíveis
- `chat` → ChatPanel expandido (carregado sob demanda via `React.lazy`); orb some quando há mensagens

Não existe modo `code` nem tela de seleção de modo: o boot entra direto em `talk`.

### Estados do Agente (`jarvisState`)

| Estado | Cor principal | Comportamento |
|--------|-------------|---------------|
| `idle` | Azul oceano | Respiração lenta |
| `listening` | Branco/roxo | Ondas sonoras |
| `processing` | Roxo profundo | Rotação agressiva |
| `speaking` | Ciano neon | Escala expandida |
| `isCritical` | Vermelho | Protocolo Stark |

### Bridge API (IPC)

- **`BridgeAPI.js`** é o único ponto de saída do React para o Python
- Ao rodar no browser (`npm run dev`), o Mock Fallback ativa automaticamente
- Adicionar novo método Python → sempre adicionar cláusula em `getMockFallback` também

### Cores (Proibição de Hardcode)

- Jamais usar hexadecimais ou rgb direto no JSX
- Sempre usar variáveis CSS declaradas em `src/index.css`
- `.liquid-glass` é a classe global de painel translúcido (sem blur)

### Otimização Crítica

- Se `activeMode === 'chat'` → cancelar `requestAnimationFrame` do LiquidAuraReactor (CPU cai de ~15% para 0%)
- Nunca omitir `is_status_signal=True` nos callbacks de alerta → evita TTS pronunciar "CRITICAL_START"

---

## Fluxo de um Comando de Voz

```
1. listen.py           → captura áudio (Google STT), detecta wake word "Jarvis"
2. brain.py            → pending_critical_action? → sim: executa; não: continua
3. intent.py           → classify_intent() → {intent, entity, confidence}
4. brain.py            → MEMORY_WRITE? → memory.py
                       → skill ativa? → skill.execute(entity, command)
                       → fallback: chat.py → ask_local_ai() → Ollama → resposta
5. speak.py            → edge-tts (ou pyttsx3) → áudio
6. bridge.py           → evaluate_js → window.receiveStatus("speaking", texto)
```

---

## Fluxo de uma Mensagem no Chat (Frontend)

```
1. ChatInput.jsx       → usuário digita + Enter
2. BridgeAPI.js        → callApi("chat_message", text, session_id)
3. bridge.py           → thread daemon → execute_command_stream()
4. intent.py           → classify_intent(text, skip_skills=True)
5. chat.py             → ask_local_ai_stream() → Ollama stream
6. bridge.py           → evaluate_js → window.receiveChatStream(chunk, isFirst, isDone)
7. ChatPanel.jsx       → acumula chunks na bolha → exibe em tempo real
```

---

## Como Criar uma Nova Skill

1. Criar arquivo em `backend/skills/{categoria}/nome_da_skill.py`
2. Declarar `INTENT`, `PROMPT_TEXT`, `CATEGORY` e `execute(entity, command)`
3. A skill é **auto-descoberta** pelo `SkillLoader` no próximo boot — sem registro manual
4. Adicionar entrada em `getMockFallback` no `BridgeAPI.js` do frontend (se a skill retornar dados para a UI)

---

## Variáveis de Ambiente (`.env`)

```bash
OLLAMA_MODEL=llama3
OLLAMA_HOST=http://localhost:11434
# Opcionais (vazio = padrão do Ollama). Ver core/llm.py
OLLAMA_NUM_CTX=4096      # contexto menor = KV cache menor = cabe mais na VRAM
OLLAMA_NUM_GPU=99        # camadas na GPU; se o Ollama recusar, é desativado sozinho
OBSIDIAN_HOST=http://127.0.0.1:27123
OBSIDIAN_API_KEY=sua_chave
MIC_INDEX=1
DEFAULT_LANGUAGE=pt-BR
DEBUG_MODE=False
```

---

## Instalação de Dependências

### Backend (Python)

```bash
cd backend

# Criar e ativar ambiente virtual (recomendado)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Instalar todas as dependências
pip install -r requirements.txt
```

Principais pacotes do `requirements.txt`:
```
pywebview          # Janela nativa + Bridge IPC
ollama             # Cliente oficial do Ollama (LLM local)
SpeechRecognition  # STT via Google
edge-tts           # TTS neural Microsoft (nuvem)
pyttsx3            # TTS offline (fallback)
pygame             # Reprodução de áudio .mp3
psutil             # Monitoramento de hardware (CPU, RAM, disco, rede)
GPUtil             # Monitoramento de GPU Nvidia (opcional)
pycaw              # Core Audio API Windows (controle de volume)
pyautogui          # Ghost keyboard e mouse virtual
python-dotenv      # Carregamento de .env
colorama           # Logs coloridos no terminal
requests           # HTTP (usado nas skills sub-agentes)
```

> ⚠️ O Ollama deve estar instalado e rodando separadamente: [ollama.ai](https://ollama.ai). Baixar o modelo com `ollama pull llama3`.

### Frontend (Node.js)

```bash
cd frontend
npm install --legacy-peer-deps
```

Principais pacotes do `package.json`:
```
react + vite                   # Core + dev server
tailwindcss                    # Estilização utilitária
framer-motion                  # Física de mola e animações
animejs                        # Micro-interações DOM
@react-three/fiber             # Renderização 3D (LiquidAuraReactor)
@react-three/drei              # Helpers Three.js
@react-three/postprocessing    # Shaders pós-processados
react-markdown                 # Parse de output do LLM
remark-math + rehype-katex     # Renderização de LaTeX
lucide-react                   # Ícones vetoriais
```

### Plugin Obsidian (para RAG)

Instalar o plugin **"Local REST API"** no Obsidian e configurar no `.env`:

```bash
OBSIDIAN_HOST=http://127.0.0.1:27123
OBSIDIAN_API_KEY=sua_chave_gerada_pelo_plugin
```

---

## Desenvolvimento Local

### Só o Frontend (sem Python)

```bash
cd frontend
npm install && npm run dev
# Mock Fallbacks ativam automaticamente — sem necessidade do backend
```

### Build completo

```bash
cd frontend && npm run build
# Abre o boot.bat na raiz para subir Python + PyWebView com o /dist
```

### Backend standalone (modo voz sem GUI)

```bash
cd backend
python -m services.brain
# Roda start_brain() diretamente no terminal
```

---

## Tom e Personalidade do JARVIS

- **Frio, educado, levemente sarcástico** — tom Tony Stark
- **Modo Voz**: texto puro, sem Markdown, sem asteriscos, sem emojis
- **Modo Chat (tela)**: Markdown obrigatório, `**negrito**`, blocos de código, KaTeX para matemática (`$$` bloco, `$` inline)
- **Proibido**: `\(`, `\[` matemáticos — o React-KaTeX não suporta
- Respostas limpas de `*` e `#` antes de ir para o TTS
- Gírias expandidas via `SLANG_MAP` em `speak.py`

---

## Decisões Arquiteturais Importantes

| Decisão | Razão |
|---------|-------|
| PyWebView em vez de Electron | Mais leve, sem Node.js, integração Python nativa |
| SQLite local em vez de nuvem | Privacidade total, zero latência, funciona offline |
| Ollama local em vez de API Codex/GPT | Sem custo por token, privacidade, funciona sem internet |
| Prompts em `.md` em vez de strings Python | Editáveis sem tocar no código, versionáveis de forma legível |
| `ollama` lib em vez de `requests.post` | Gerenciamento de sessão mais robusto, streaming tipado |
| state.py separado | Evita importações circulares entre brain, alerts e chat |
| `skill.execute(entity, command)` com 2 args | Sub-agentes precisam da frase original para contexto |

## Imported Claude Cowork project instructions

Claude sempre que for realizar qualquer atividade relacionada a este projeto deve ser consultado no obsidian primeiro com os arquivos existentes na vault, e também se basear no repositório apresentado como contexto
