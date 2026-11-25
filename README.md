# J.A.R.V.I.S.

**J.A.R.V.I.S.** é um assistente pessoal inspirado na IA do Homem de Ferro, feito para **Windows** e rodando **localmente**. É um app de terminal (TUI em [Textual](https://textual.textualize.io)), 100% Python. O LLM é local (Ollama), a memória fica num SQLite local e no seu vault do Obsidian, e nada de conversa vai para a nuvem.

## O que ele faz

- **Chat** (texto, Markdown) e **Copilot** (só voz, com wake word "Jarvis"), alternados com `Shift+Tab`.
- **Skills** plug-and-play (26): abrir/fechar apps, volume, Spotify, brilho, limpeza, bloqueio, agenda do Google, Gmail, GitHub, trânsito, pesquisa na web, Pomodoro, Modo Apresentação, lembretes, ideias no Obsidian, consumo de energia… No Chat só rodam as de produtividade e web; no Copilot, todas. Ação que apaga, envia ou encerra algo sempre pede confirmação.
- **Leitura de tela**: "explica o erro na minha tela", "resolve a questão aberta". O OCR do próprio Windows lê a janela (sem gastar VRAM) e o modelo local explica o erro, o código, o documento ou a questão. Com o navegador em foco, "resume essa página" baixa a página inteira pela URL da aba (inclusive o que está fora da tela); página logada ou link com token cai no OCR.
- **Navegador por voz** (Opera GX, Chrome, Edge, Brave, Vivaldi — sem extensão): abas ("abre uma aba no github", "fecha a aba do YouTube", "vai para a terceira aba", "lista as abas", "reabre a aba"; fechar várias pede confirmação) e **YouTube** ("toca lo-fi no YouTube" abre o vídeo direto, "pausa o vídeo", "avança 30 segundos", "legenda", "tela cheia", "velocidade 1.5", "próximo vídeo"). Usa a UI Automation do Windows e atalhos de teclado; tecla só sai com o navegador em foco.
- **Gmail**: "quais são meus e-mails mais urgentes?" (lista por prioridade), "leia o e-mail 2", "responda o e-mail 2 dizendo que confirmo", "manda a proposta.txt para o Guilherme" (anexo do computador, contato por nome), "apaga as promoções" (Lixeira, 30 dias) e "organize meu e-mail". O rascunho, a lista ou o plano aparecem antes, e nada é excluído de vez. Também por `/email`.
- **Ponte Telegram / Discord**: converse com o JARVIS pelo celular; o cérebro continua rodando no seu PC, só IDs liberados falam com ele e a confirmação fica presa a quem pediu.
- **Download inteligente**: "instala o 7-zip" / `/instalar` / `/baixar` procuram no winget e pedem confirmação.
- **Clipboard, lembretes e ideias**: histórico do clipboard (`/clip`, sem guardar senhas), lembretes com horário (`/lembrete`, avisos antes dos eventos da agenda com o tempo de trajeto) e ideias da conversa registradas em 🧠 Brainstorms no Obsidian (`/ideia`).
- **Vigia de rede**: aprende o que é normal na sua rede e avisa de porta exposta, programa novo falando com a internet ou aparelho desconhecido (`/rede`); encerrar ou bloquear pede confirmação.
- **Briefing diário** no 1º boot do dia: clima, computador (CPU, RAM, GPU, internet), GitHub, agenda, trânsito e a manchete mais relevante de cada portal, escolhida pela IA entre as mais importantes do dia.
- **Consumo de energia**: watts na linha de status, medidor no `/status`, kWh e custo do dia e do mês ("quanto o PC está gastando?"). A GPU NVIDIA é medida; CPU e resto são estimados (ajuste `POWER_*` no `.env`).
- **Alertas de hardware** com filtro de interrupções (Não Perturbe, reunião, tela cheia, apresentação).
- **Memória de longo prazo** no Obsidian (RAG) e histórico de sessões estilo *save slots*.
- **Agente residente** na bandeja: `Win+J` abre/foca o JARVIS de qualquer lugar, `Ctrl+Alt+T` traduz o texto selecionado e `Ctrl+Alt+E` explica no Chat o código ou erro selecionado, em qualquer app.
- **Atualização automática** pelo Release do GitHub, com SHA-256 e assinatura conferidos antes de instalar.

## Instalar (Windows 10/11)

Baixe o **`JARVIS-Setup.exe`** do [Release mais recente](https://github.com/Grolla05/J.A.R.V.I.S-Just-A-Rather-Very-Intelligent-System/releases/latest) e execute. O instalador já traz o Python e todas as bibliotecas.

- Se o **Ollama** não estiver instalado, o setup mostra o link oficial ([ollama.com/download](https://ollama.com/download)) e espera. Depois, você escolhe o **modelo de IA**, baixado no fim da instalação.
- Abra pelo atalho **J.A.R.V.I.S**, pelo `Win+J` ou com `jarvis` no terminal (se marcou a opção do PATH). Usa o Windows Terminal quando existir.
- Configurações e dados ficam em `%APPDATA%\JARVIS` (`.env`, banco, logs) e sobrevivem a atualizações.

### Integrações de conta (Google Agenda, Gmail, Spotify, GitHub, Telegram, Discord)

Cada usuário cria as **próprias chaves** (apps grátis no Google Cloud e no Spotify Developer, token do GitHub, bots do Telegram/Discord) e preenche `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SPOTIFY_CLIENT_ID`, `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`/`DISCORD_BOT_TOKEN` (com os `*_ALLOWED_IDS`) no `.env`. Todas as variáveis: [docs/variaveis-ambiente.md](docs/variaveis-ambiente.md). Depois, conecte em `/config` → INTEGRAÇÕES. O JARVIS não traz chave de nenhum serviço. Passo a passo: **[docs/integracoes-oauth.md](docs/integracoes-oauth.md)**.

## Rodar a partir do código

Pré-requisitos: Windows, Python 3.11+, [Ollama](https://ollama.com) com um modelo (`ollama pull llama3.2`) e, para a memória de longo prazo, o Obsidian com o plugin **Local REST API**.

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy ..\env.example ..\.env
python main.py
```

Se o Ollama local estiver fora do ar, o JARVIS sobe o `ollama serve` sozinho. Prefira o Windows Terminal (o conhost antigo renderiza mal cores e Unicode).

Primeiros passos dentro da TUI: `Ctrl+K` abre a paleta com todos os comandos, `Shift+Tab` troca Chat ⇄ Copilot e `/config` ajusta voz, microfone, rotinas e integrações.

### Testes e lint

```bash
cd backend
python -m pytest tests -q -n auto
ruff check . && ruff check ../frontend
```

### Gerar o instalador localmente

```powershell
powershell -File installer\build_runtime.ps1          # dist\runtime (Python + libs) e dist\app (código)
iscc /DVersao=0.0.0-dev installer\jarvis.iss          # dist\JARVIS-Setup.exe (Inno Setup 6)
powershell -File installer\test_setup.ps1             # instala, testa e desinstala em silêncio
```

Cada PR e push na `main`/`DEV` passa por ruff, compileall e pytest (`main.yml`). Cada push na `main` roda os testes e publica um Release novo, com o setup assinado (`release.yml`).

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/arquitetura.md](docs/arquitetura.md) | Como tudo funciona, ponta a ponta e módulo a módulo |
| [docs/integracoes-oauth.md](docs/integracoes-oauth.md) | Criar as chaves do Google e do Spotify |
| [backend/README.md](backend/README.md) | Visão do backend e índice das docs por módulo |
| [backend/core/README.md](backend/core/README.md) | Infraestrutura (`core/`) |
| [backend/services/README.md](backend/services/README.md) | Roteamento, conversa, voz e rotinas (`services/`) |
| [backend/skills/README.md](backend/skills/README.md) | Contrato e lista das skills; como criar uma |
| [backend/database/README.md](backend/database/README.md) | Esquema do SQLite |
| [frontend/README.md](frontend/README.md) | A TUI: telas, comandos e atalhos |
| [AGENTS.md](AGENTS.md) | Regras do projeto para quem (ou o agente que) escreve código; índice de `docs/` |
| [docs/variaveis-ambiente.md](docs/variaveis-ambiente.md) | Todas as variáveis do `.env`, com padrão |
| [docs/tui.md](docs/tui.md) | Modos, atalhos, todos os comandos `/` e telas |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Como contribuir |
| [CHANGES.md](CHANGES.md) | Histórico de mudanças |
