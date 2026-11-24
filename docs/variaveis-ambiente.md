# Variáveis de ambiente (`.env`)

Todas as variáveis que o `Settings` (`backend/core/config.py`) lê do `.env`, com o padrão usado quando ela falta. O modelo comentado é o [`env.example`](../env.example) na raiz. Toda variável nova precisa de **default** no `Settings` (`.env` antigos não ganham a chave); veja [`regras-backend.md`](regras-backend.md). No app instalado o `.env` fica em `%APPDATA%\JARVIS` (`JARVIS_DATA_DIR`).

## Geral

| Variável | Padrão | Para quê |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Nível do log |
| `DEBUG_MODE` | `False` | Modo de depuração |
| `CHAT_HISTORY_TURNS` | `10` | Turnos (pergunta + resposta) da sessão enviados ao modelo |

## Ollama (LLM local)

| Variável | Padrão | Para quê |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2` | Modelo de texto |
| `OLLAMA_HOST` | `http://localhost:11434` | Servidor do Ollama |
| `OLLAMA_KEEP_ALIVE` | `-1` | Tempo do modelo na VRAM (`-1` = nunca descarrega; aceita `30m`) |
| `OLLAMA_NUM_CTX` | vazio (padrão do Ollama) | Janela de contexto; menor = KV cache menor = cabe mais na VRAM |
| `OLLAMA_NUM_GPU` | vazio | Camadas na GPU (`99` = todas); se o Ollama recusar, é desativado sozinho |
| `OLLAMA_AUTOSTART` | `True` | Sobe `ollama serve` no boot se o servidor local estiver fora |
| `OLLAMA_START_TIMEOUT` | `30` | Segundos esperando a API depois de subir o servidor |
| `TIMEOUT_LLM` | `30` | Segundos das chamadas curtas ao Ollama: classificador de intenção e decisões das skills |
| `TIMEOUT_API` | `10` | Segundos das requisições HTTP (GitHub, notícias, web, YouTube) |
| `OLLAMA_VISION_MODEL` | `moondream` | Modelo de visão para imagem anexada (`/attach`) |
| `OLLAMA_VISION_KEEP_ALIVE` | `5m` | Tempo do modelo de visão na VRAM |
| `TIMEOUT_VISION` | `60` | Segundos para a resposta do modelo de visão (a 1ª carga é lenta) |

## Leitura de tela, áudio anexado e uploads

| Variável | Padrão | Para quê |
|---|---|---|
| `OCR_LANGUAGE` | vazio | Idioma do OCR (`SCREEN_READ`); vazio = pt-BR → en-US → idiomas do Windows |
| `SCREEN_TEXT_MAX` | `6000` | Caracteres do OCR enviados ao modelo |
| `WHISPER_MODEL_SIZE` | `base` | Modelo do faster-whisper (áudio anexado) |
| `WHISPER_DEVICE` | `auto` | `cpu`, `cuda` ou `auto` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Precisão do Whisper (`int8` é leve na CPU) |
| `TIMEOUT_TRANSCRIPTION` | `60` | Segundos para transcrever |
| `MAX_UPLOAD_SIZE_MB` | `15` | Tamanho máximo de um anexo |

## Obsidian (memória de longo prazo)

| Variável | Padrão | Para quê |
|---|---|---|
| `OBSIDIAN_HOST` | `http://127.0.0.1:27123` | Plugin Local REST API |
| `OBSIDIAN_API_KEY` | vazio | Chave do plugin |
| `VAULT_MIN_SCORE` | vazio (sem corte) | Score mínimo da busca para a nota entrar no chat |

## Integrações de conta

Chaves **pessoais**: cada usuário cria as suas ([`integracoes-oauth.md`](integracoes-oauth.md)). Nunca versionar. Tokens ficam no Cofre de Credenciais do Windows.

| Variável | Padrão | Para quê |
|---|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | vazio | Client OAuth "App para computador": Google Agenda e Gmail (um card para cada em `/config` → INTEGRAÇÕES) |
| `EMAIL_TEXT_MAX` | `6000` | Caracteres do corpo do e-mail enviados ao modelo |
| `SPOTIFY_CLIENT_ID` | vazio | App do Spotify (PKCE, sem client secret) |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8888/callback` | Callback do OAuth do Spotify |
| `SPOTIFY_MARKET` | `BR` | Mercado das buscas |
| `GITHUB_TOKEN` | vazio | Token pessoal (skill `GITHUB`, `/gh`, briefing) |
| `GITHUB_DEFAULT_REPO` | vazio | `dono/repo` usado quando o pedido não cita um |
| `TOMTOM_API_KEY` | vazio | Trânsito ao vivo; vazio = OSRM (estimado, grátis) |

## Ponte Telegram / Discord (`messenger.py`)

| Variável | Padrão | Para quê |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | vazio | Token do bot (BotFather) |
| `TELEGRAM_ALLOWED_IDS` | vazio = ninguém | IDs liberados, separados por vírgula |
| `DISCORD_BOT_TOKEN` | vazio | Token do bot |
| `DISCORD_ALLOWED_IDS` | vazio = ninguém | IDs liberados, separados por vírgula |

## Voz

| Variável | Padrão | Para quê |
|---|---|---|
| `SPEECH_RATE` | `180` | Velocidade do pyttsx3 (fallback do edge-tts) |
| `MIC_INDEX` | `0` | Índice do microfone |
| `MIC_ENERGY_THRESHOLD` | `300` | Sensibilidade do microfone |
| `WAKE_WORDS` | lista padrão | Palavras que acordam o Copilot, separadas por vírgula |

O idioma do reconhecimento (`DEFAULT_LANGUAGE = "pt-BR"`) é fixo no `Settings`, não vem do `.env`.

## Agente residente e atualização

| Variável | Padrão | Para quê |
|---|---|---|
| `GLOBAL_HOTKEY` | `win+j` | Abre/foca a TUI no Copilot; vazio desliga |
| `TRANSLATE_HOTKEY` | `ctrl+alt+t` | Traduz o texto selecionado em qualquer app; vazio desliga |
| `EXPLAIN_HOTKEY` | `ctrl+alt+e` | Explica o código/erro selecionado no Chat da TUI; vazio desliga |
| `AUTO_UPDATE` | `True` | Procura versão nova nos Releases (só no app instalado); o toggle em `/config` → SISTEMA vence |
| `UPDATE_REPO` | repositório oficial | `dono/nome` dos Releases |

## Pomodoro / Não Perturbe

| Variável | Padrão | Para quê |
|---|---|---|
| `POMODORO_FOCUS_MIN` | `25` | Minutos de foco |
| `POMODORO_SHORT_BREAK_MIN` | `5` | Pausa curta |
| `POMODORO_LONG_BREAK_MIN` | `15` | Pausa longa |
| `POMODORO_CYCLES` | `4` | Focos até a pausa longa |

## Consumo de energia (`core/power.py`)

Desktop não tem sensor do consumo total: a GPU NVIDIA é medida (`nvidia-smi`), CPU e resto são estimados.

| Variável | Padrão | Para quê |
|---|---|---|
| `POWER_TARIFF_KWH` | `0.85` | R$/kWh da conta de luz (custo de hoje e do mês) |
| `POWER_BASE_W` | `45` | Watts fixos de placa-mãe, RAM, discos e ventoinhas |
| `POWER_CPU_TDP_W` | `65` | TDP do processador: consumo estimado a 100 % de carga (parado = 15 %) |
| `POWER_PSU_EFF` | `0.85` | Eficiência da fonte (0–1); o total é dividido por ela = consumo na tomada |

## Fora do `.env`

`JARVIS_DATA_DIR` é definida pelo `jarvis.cmd` do app instalado (`%APPDATA%\JARVIS`) e muda onde ficam `.env`, banco, logs e uploads. Em dev, sem ela, tudo fica em `backend/` e o `.env` na raiz.
