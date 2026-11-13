# frontend — a TUI do J.A.R.V.I.S

Interface de terminal em [Textual](https://textual.textualize.io), 100% Python. Sem build, Node.js nem WebView: roda no terminal e chama o backend (`core/`, `services/`) por import direto. O visual segue o canvas de design "JARVIS TUI".

## Rodar

O ponto de entrada é o backend, que põe a raiz do repositório no `sys.path` e importa este pacote:

```bash
cd backend
python main.py             # abre no Chat, com tela de boot
python main.py --copilot   # abre no Copilot, sem tela de boot (é o que o Win+J faz)
```

Prefira o Windows Terminal.

## Arquivos

| Arquivo | Papel |
|---|---|
| `app.py` | `JarvisApp`: modos, atalhos, worker de stream, sessões, anexos, voz, alertas, telemetria, briefing automático, atualização |
| `widgets.py` | `MessageView`, `PromptInput`, `StatusLine`, `JarvisOrb`, `PixelSprite`, `CopilotHero`, `VoiceBar`, `ConfirmScreen` (30 s) |
| `commands.py` | Parser puro dos `/comandos` (fonte única: `COMMANDS`, `ALIASES`, `NEEDS_ARG`) e paleta (`palette_entries`, `filter_entries`) |
| `orb.py` | Orb pixel-art 16×16 (quadros por estado e meio-bloco) — lógica pura |
| `sprites.py` | Sprites 16-bit e efeitos (▰▱, sparkline, barras, CRT, scanline) — lógica pura |
| `jarvis.tcss` | Tema. Todas as cores como variáveis `$j-*` |
| `screens/` | Telas cheias (abaixo) |
| `pyproject.toml` | Herda o ruff de `backend/pyproject.toml` |

## Modos

| Modo | Entra com | Como funciona |
|---|---|---|
| **Chat** | `Shift+Tab` | Texto em Markdown. Roda só skills de `productivity` e `web` (agenda, GitHub, trânsito, busca, briefing, foco, apresentação), com o selo `[INTENT]`. Voz desligada |
| **Copilot** | `Shift+Tab`, `Ctrl+T`, `Win+J` | Só voz: o input vira `VoiceBar` + orb (ouvindo → pensando → respondendo). Todas as skills; ações críticas pedem confirmação. A resposta é falada. Tudo em ciano |

Comandos `/` só existem no Chat.

## Telas

| Tela | Abre com | Arquivo |
|---|---|---|
| Boot (BIOS, `[  OK  ]`) | início | `screens/boot.py` |
| Atualização disponível | início, se houver Release novo | `screens/update.py` |
| Dashboard (CPU, RAM, GPU, rede, processos, saúde) | `/status` | `screens/status.py` |
| Cartuchos das skills | `/skills` | `screens/skills.py` |
| Log de atividade + timeline do último turno | `/log` | `screens/log.py` |
| Memória (vault do Obsidian) | `/vault` | `screens/vault.py` |
| Configurações (VOZ, MICROFONE, ROTINAS, INTEGRAÇÕES, SISTEMA, MODELO, SOBRE) | `/config` | `screens/settings.py`, `screens/integrations_panel.py` |
| Save slots (sessões) | `Ctrl+O`, `/sessions` | `screens/save_slots.py` |
| Paleta de comandos | `Ctrl+K`, `/menu`, `/help` | `screens/palette.py` |
| Desligamento CRT | `Esc`, `/quit` | `screens/shutdown.py` |
| House Party (easter egg) | "house party" no Chat | `screens/house_party.py` |

Todas herdam de `JarvisScreen` (`screens/base.py`): topo com selo, corpo e a linha de status; `Esc` volta.

## Comandos

| Comando | Faz |
|---|---|
| `/menu` | Paleta de comandos, skills e foco (`Ctrl+K`) |
| `/new`, `/sessions`, `/rename <título>`, `/pin` | Sessões (`Ctrl+N`, `Ctrl+O`) |
| `/regen`, `/edit` | Regenerar (`Ctrl+R`) / editar a última (`↑` com input vazio) |
| `/attach <caminho>`, `/detach` | Imagem → modelo de visão; áudio → transcrição no input. Arrastar o arquivo para o terminal também anexa |
| `/mode [chat\|copilot]`, `/voice` | Modo (`Shift+Tab`) e voz (`Ctrl+T`) |
| `/skills [on\|off <skill\|categoria>]` | Cartuchos ou alterna direto |
| `/status`, `/log`, `/vault [termo]`, `/config` | Telas cheias |
| `/web <pergunta>` | Pesquisa na internet e resume com fontes |
| `/gh [prs\|issues\|commit\|ci] [dono/repo]` | GitHub |
| `/briefing` | Briefing do dia |
| `/rota [<local> <endereço>]` | Cadastra um local fixo; sem argumento lista |
| `/clip [explicar\|traduzir\|resumir\|hist]` | Age sobre o clipboard |
| `/focus [min\|stop\|skip\|status]`, `/dnd [on\|off\|min]`, `/silent [on\|off]` | Pomodoro, Não Perturbe, Modo Apresentação |
| `/clear` | Limpa a tela (`Ctrl+L`), sem apagar o histórico |
| `/quit` | Sai (`Esc`) |

`//texto` envia uma mensagem que começa com `/`.

## Linha de status

Uma única linha: telemetria (CPU, RAM, GPU, rede a cada 3 s) · selo de foco (`◷ FOCO 24m 1/4`, `☾ DND`, `[SILENT]`) · voz, e os atalhos à direita. Estado crítico pinta a conversa de vermelho (classe `-critical`); o Copilot usa a classe `-copilot`.

## Testes

Ficam em `backend/tests/` (`test_tui_*.py`) e usam `App.run_test()` + Pilot com `stream_fn` e voz falsos (`JarvisApp(stream_fn=..., voice=FakeVoice(...), start_services=False)`):

```bash
cd backend
python -m pytest tests -q
ruff check ../frontend
```

> Com a variável `NO_COLOR` definida, o Textual desenha tudo em cinza. Não é bug do tema.
