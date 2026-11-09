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
| `widgets.py` | `MessageView`, `PromptInput`, `JarvisOrb`, `CopilotHero`, `VoiceBar`, `ConfirmScreen` (expira em 30 s), `format_slot_when` |
| `orb.py` | Orb pixel-art 16×16 do Copilot: quadros de cada estado e conversão para meio-bloco (lógica pura) |
| `commands.py` | Parser puro dos `/comandos` e entradas da paleta Ctrl+K |
| `jarvis.tcss` | Tema. Todas as cores ficam aqui como variáveis `$j-*` |
| `pyproject.toml` | Herda as regras do ruff de `backend/pyproject.toml` |

## Telas

- **Chat:** barra superior azul (selo CHAT, título, "sessão N de M"), conversa em Markdown, barra de anexo, input e uma linha única com telemetria (esquerda) e atalhos (direita).
- **Copilot (`Shift+Tab` ou `Ctrl+T`) — só voz:** tudo em ciano, "somente voz · skills ativas: N" no topo, orb pixel-art com o estado (ouvindo / pensando / respondendo) e barra "Ouvindo… diga "Jarvis"" no lugar do input. A resposta mostra o selo da skill (`[AUDIO_CONTROL] ✓`) e é falada.
- **Protocolo crítico:** topo vermelho, confirmação `s`/`n` que expira sozinha em 30 s (= não) e barra de voz pedindo "sim" ou "não".
- **Save slots (`Ctrl+O`):** tela cheia `CARREGAR` com um cartão por sessão em 2 colunas (nº do slot, título, `★` fixada, `quando · N msgs · modo`, última fala do JARVIS e barra do tamanho). Setas navegam, Enter carrega, `p` fixa, `Del Del` apaga, `/` busca por título ou trecho (`frontend/screens/save_slots.py`).
- **Skills (`/skills`):** cartuchos retrô — aba na cor da categoria, etiqueta com ícone + INTENT, `■ categoria  ON` e contatos dourados; desligado fica apagado e 1 linha abaixo.

## Testes

Os testes ficam em `backend/tests/` (`test_tui_app.py`, `test_tui_commands.py`, `test_tui_orb.py`) e usam `App.run_test()` com stream e voz falsos (`JarvisApp(stream_fn=..., voice=...)`), sem Ollama, microfone nem hardware:

```bash
cd backend
python -m pytest tests -q
```

> Se a variável `NO_COLOR` estiver definida, o Textual desenha tudo em tons de cinza. Não é bug do tema.
