# Skills do J.A.R.V.I.S.

Skills são as ações do JARVIS. Cada uma é um arquivo `.py` em `backend/skills/<categoria>/`, descoberto sozinho pelo `SkillManager` (`core/skill_loader.py`) no boot — sem registro manual.

## Contrato

```python
from core.prompts import load_prompt

INTENT = "NOME_UNICO"                          # chave do roteamento (única)
PROMPT_TEXT = load_prompt("skills/nome.md")    # explica ao classificador quando usar
# CATEGORY é herdada da pasta (automation, system, productivity, web)

def execute(entity: str, command: str) -> str:
    # entity: alvo extraído pelo classificador ("spotify", "50", None…)
    # command: frase original do usuário
    return "resposta do JARVIS (Markdown na TUI; o TTS limpa para a voz)"
```

> `execute` recebe **dois** argumentos. Skill com um só quebra o roteamento.

## Onde cada categoria roda

| Categoria | Chat | Copilot / voz |
|---|---|---|
| `automation` (mexe no PC) | não | sim |
| `system` (limpeza, energia, processos) | não | sim |
| `productivity` | sim | sim |
| `web` | sim | sim |

O bloqueio no Chat vem de `CHAT_BLOCKED_CATEGORIES` em `services/intent.py`: essas skills nem são oferecidas ao classificador, e o `brain` confere de novo antes de executar. O usuário ainda pode desligar qualquer skill ou categoria em `/skills`.

## Skills atuais

| Pasta | `INTENT` | O que faz |
|---|---|---|
| automation | `APP_CONTROL` | Abre, foca e fecha apps (busca fuzzy nos instalados) |
| automation | `AUDIO_CONTROL` | Volume relativo/absoluto e mudo (pycaw) |
| automation | `CLIPBOARD` | Explica, traduz ou resume o que está copiado |
| automation | `KEYBOARD_CONTROL` | Digita, atalhos e teclas na janela em foco |
| automation | `SCREEN_CONTROL` | Brilho, protocolo "retina" (gamma) e mover janelas entre monitores |
| automation | `SPOTIFY_CONTROL` | Play/pause/próxima sem LLM; busca de faixa com LLM (Premium para o player) |
| automation | `WORK_MACRO` | Cenas (trabalho, estudo…): abre apps, organiza janelas, silencia notificações |
| system | `SYSTEM_REPORT` | Relatório da máquina (também usado na saudação) |
| system | `SYSTEM_CLEANUP` | Esvazia a Lixeira, limpa temporários, desinstala app |
| system | `SYSTEM_SECURITY` | Bloquear, suspender, desligar, modo sentinela |
| productivity | `CALENDAR` | Eventos do Google Agenda (hoje, amanhã, dia da semana, próxima reunião) |
| productivity | `DAILY_BRIEFING` | Briefing do dia (`core/briefing.py`) |
| productivity | `FOCUS_MODE` | Pomodoro e Não Perturbe |
| productivity | `GITHUB` | PRs, issues, último commit, CI; criar issue pede confirmação |
| productivity | `PRESENTATION_MODE` | Liga/desliga o Modo Apresentação |
| productivity | `TRAFFIC` | Tempo entre locais cadastrados com `/rota` |
| web | `WEB_SEARCH` | Pesquisa na web e resume com fontes |

## Criar uma skill

1. Crie `backend/skills/<categoria>/minha_skill.py` com `INTENT`, `PROMPT_TEXT` e `execute(entity, command)`.
2. Escreva o `PROMPT_TEXT` em `backend/prompts/skills/minha_skill.md` (nunca string no `.py`).
3. Se precisar do LLM, use `core.llm.query_ollama(..., format="json", temperature=0)` e um prompt `.md`. Resolva frases óbvias sem LLM primeiro (veja `parse_fast` em `focus_mode.py` e `github_control.py`).
4. Ação destrutiva ou externa (apagar, publicar, encerrar)? Não execute direto: grave `state.pending_critical_action = {"type": ..., "target": ..., "question": ..., "timeout": time.time() + 30, "on_confirm": fn}` e devolva a pergunta (modelo: `request_issue` em `github_control.py`). A TUI abre a `ConfirmScreen`; a voz aceita "sim".
5. Faça imports pesados dentro de `execute`. Valide `entity` antes de passar para subprocesso.
6. Use `log` (nunca `print`) e devolva sempre uma string — erro vira mensagem amigável.
7. Escreva testes em `backend/tests/` (sem hardware real: mocke as chamadas de sistema).

A skill aparece em `/skills` e na paleta `Ctrl+K` no próximo boot.
