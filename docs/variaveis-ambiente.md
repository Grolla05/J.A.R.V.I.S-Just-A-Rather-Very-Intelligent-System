# Variáveis de ambiente (`.env`)

Principais variáveis do `.env`. O modelo completo e comentado é o [`env.example`](../env.example) na raiz. Toda variável nova precisa de **default** em `core/config.py` (`Settings`); veja [`regras-backend.md`](regras-backend.md). Instalação e execução em [`AGENTS.md`](../AGENTS.md).

```bash
OLLAMA_MODEL=llama3
OLLAMA_HOST=http://localhost:11434
# Opcionais (vazio = padrão do Ollama). Ver core/llm.py
OLLAMA_NUM_CTX=4096      # contexto menor = KV cache menor = cabe mais na VRAM
OLLAMA_NUM_GPU=99        # camadas na GPU; se o Ollama recusar, é desativado sozinho
OBSIDIAN_HOST=http://127.0.0.1:27123
OBSIDIAN_API_KEY=sua_chave
MIC_INDEX=1
WAKE_WORDS=jarvis,javis,jarbas   # vírgula separa; vazio = lista padrão
GLOBAL_HOTKEY=win+j              # atalho do agente residente; vazio desliga
TRANSLATE_HOTKEY=ctrl+alt+t      # traduz a seleção (agente); vazio desliga
EXPLAIN_HOTKEY=ctrl+alt+e        # explica a seleção no Chat da TUI (agente); vazio desliga
AUTO_UPDATE=True                 # atualiza no logon pelo Release do GitHub (só instalado)
UPDATE_REPO=                     # dono/nome dos Releases; vazio = repositório oficial
GOOGLE_CLIENT_ID=                # client OAuth "App para computador" do próprio usuário (+ GOOGLE_CLIENT_SECRET)
TOMTOM_API_KEY=                  # opcional: trânsito ao vivo (sem ela, OSRM)
EMAIL_TEXT_MAX=6000              # Gmail (mesmo GOOGLE_CLIENT_ID; card próprio): corpo enviado ao modelo
TELEGRAM_BOT_TOKEN=              # ponte (messenger.py) + TELEGRAM_ALLOWED_IDS (vazio = ninguém)
DISCORD_BOT_TOKEN=               # ponte (discord.py) + DISCORD_ALLOWED_IDS
OCR_LANGUAGE=                    # leitura de tela (SCREEN_READ); vazio = pt-BR → en-US → idiomas do Windows
SCREEN_TEXT_MAX=6000             # caracteres do OCR enviados ao modelo
POMODORO_FOCUS_MIN=25            # + POMODORO_SHORT_BREAK_MIN, _LONG_BREAK_MIN, _CYCLES
DEFAULT_LANGUAGE=pt-BR
DEBUG_MODE=False
```

Chaves OAuth (Google Agenda, Gmail, Spotify) são **pessoais**: veja [`integracoes-oauth.md`](integracoes-oauth.md). Nunca versionar chaves.
