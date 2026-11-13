# J.A.R.V.I.S.

**J.A.R.V.I.S.** é um assistente pessoal inspirado na IA do Homem de Ferro, feito para **Windows** e rodando **localmente**. É um app de terminal (TUI em [Textual](https://textual.textualize.io)), 100% Python. O LLM é local (Ollama), a memória fica num SQLite local e no seu vault do Obsidian, e nada de conversa vai para a nuvem.

## O que ele faz

- **Chat** (texto, Markdown) e **Copilot** (só voz, com wake word "Jarvis"), alternados com `Shift+Tab`.
- **Skills** plug-and-play: abrir/fechar apps, volume, Spotify, brilho, limpeza, bloqueio, agenda do Google, GitHub, trânsito, pesquisa na web, Pomodoro, Modo Apresentação… No Chat só rodam as de consulta/produtividade; no Copilot, todas.
- **Briefing diário** no 1º boot do dia: clima, computador (CPU, RAM, GPU, internet), GitHub, agenda, trânsito e a manchete mais relevante de cada portal.
- **Alertas de hardware** com filtro de interrupções (Não Perturbe, reunião, tela cheia, apresentação).
- **Memória de longo prazo** no Obsidian (RAG) e histórico de sessões estilo *save slots*.
- **Agente residente** na bandeja: `Win+J` abre/foca o JARVIS de qualquer lugar e `Ctrl+Alt+T` traduz o texto selecionado em qualquer app.
- **Atualização automática** pelo Release do GitHub.

## Instalar (Windows 10/11)

Baixe o **`JARVIS-Setup.exe`** do [Release mais recente](https://github.com/Grolla05/J.A.R.V.I.S-Just-A-Rather-Very-Intelligent-System/releases/latest) e execute. O instalador já traz o Python e todas as bibliotecas.

- Se o **Ollama** não estiver instalado, o setup mostra o link oficial ([ollama.com/download](https://ollama.com/download)) e espera. Depois, você escolhe o **modelo de IA**, baixado no fim da instalação.
- Abra pelo atalho **J.A.R.V.I.S**, pelo `Win+J` ou com `jarvis` no terminal (se marcou a opção do PATH). Usa o Windows Terminal quando existir.
- Configurações e dados ficam em `%APPDATA%\JARVIS` (`.env`, banco, logs) e sobrevivem a atualizações.

### Integrações de conta (Google Agenda e Spotify)

Cada usuário cria as **próprias chaves** (apps grátis no Google Cloud e no Spotify Developer) e preenche `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `SPOTIFY_CLIENT_ID` no `.env`. Depois, conecte em `/config` → INTEGRAÇÕES. O JARVIS não traz chave de nenhum serviço. Passo a passo: **[docs/integracoes-oauth.md](docs/integracoes-oauth.md)**.

## Rodar a partir do código

Pré-requisitos: Windows, Python 3.11+, [Ollama](https://ollama.com) com um modelo (`ollama pull llama3.2`) e, para a memória de longo prazo, o Obsidian com o plugin **Local REST API** e o [uv](https://docs.astral.sh/uv/) (`uvx mcp-obsidian`).

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
python -m pytest tests -q
ruff check . && ruff check ../frontend
```

### Gerar o instalador localmente

```powershell
powershell -File installer\build_runtime.ps1          # dist\runtime (Python + libs) e dist\app (código)
iscc /DVersao=0.0.0-dev installer\jarvis.iss          # dist\JARVIS-Setup.exe (Inno Setup 6)
powershell -File installer\test_setup.ps1             # instala, testa e desinstala em silêncio
```

Cada push na `main` roda os testes e publica um Release novo (`.github/workflows/release.yml`).

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
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Regras do projeto para quem (ou o agente que) escreve código |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Como contribuir |
| [CHANGES.md](CHANGES.md) | Histórico de mudanças |
