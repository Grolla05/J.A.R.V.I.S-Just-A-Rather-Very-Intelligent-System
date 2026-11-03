# frontend — interface de terminal do J.A.R.V.I.S

TUI em [Textual](https://textual.textualize.io), 100% Python. Não tem build, Node.js nem WebView: roda no próprio terminal e chama o backend (`core/`, `services/`) por import direto.

O visual segue o canvas de design aprovado ("JARVIS TUI": Chat, Copilot, Protocolo crítico e Trocar sessão).

## Como rodar

O ponto de entrada continua sendo o backend, que põe a raiz do repositório no `sys.path` e importa este pacote:

```bash
cd backend
python main.py
```

Ou `boot.bat` na raiz (sobe o Ollama antes). Prefira o Windows Terminal.

## Arquivos

| Arquivo | Papel |
|---|---|
| `app.py` | `JarvisApp`: modos chat/copilot, atalhos, stream, sessões, anexos, voz, alertas, telemetria |
| `widgets.py` | `MessageView`, `PromptInput`, `SessionPicker` (com filtro), `ConfirmScreen` (expira em 30 s), `format_when` |
| `commands.py` | Parser puro dos `/comandos` e o `/help` |
| `jarvis.tcss` | Tema. Todas as cores ficam aqui como variáveis `$j-*` |
| `pyproject.toml` | Herda as regras do ruff de `backend/pyproject.toml` |

## Telas

- **Chat:** barra superior azul (selo CHAT, título, "sessão N de M"), conversa em Markdown, barra de anexo, input, status e atalhos.
- **Copilot (`Shift+Tab`):** tudo em ciano, "skills ativas: N" no topo e o selo da skill na resposta (`[AUDIO_CONTROL] ✓`).
- **Protocolo crítico:** topo vermelho e confirmação `s`/`n` que expira sozinha em 30 s (= não).
- **Trocar sessão (`Ctrl+O`):** lista com filtro por título; `●` sessão atual, `★` fixada.

## Testes

Os testes ficam em `backend/tests/` (`test_tui_app.py`, `test_tui_commands.py`) e usam `App.run_test()` com stream falso, sem Ollama nem hardware:

```bash
cd backend
python -m pytest tests -q
```

> Se a variável `NO_COLOR` estiver definida, o Textual desenha tudo em tons de cinza. Não é bug do tema.
