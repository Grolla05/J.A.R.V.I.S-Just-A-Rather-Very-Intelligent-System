# Skills do J.A.R.V.I.S.

Skills são as ações do JARVIS. Cada uma é um arquivo `.py` em `backend/skills/<categoria>/`, descoberto sozinho pelo `SkillManager` (`core/skill_loader.py`) no boot — sem registro manual.

## Contrato

```python
from core.prompts import load_prompt

INTENT = "NOME_UNICO"                          # chave do roteamento (única)
PROMPT_TEXT = load_prompt("skills/nome.md")    # explica ao classificador quando usar
KEYWORDS = ("spotify", "music*", "toc*")       # opcional: pré-filtro do classificador
# CATEGORY é herdada da pasta (automation, system, productivity, web)

def execute(entity: str, command: str) -> str:
    # entity: alvo extraído pelo classificador ("spotify", "50", None…)
    # command: frase original do usuário
    return "resposta do JARVIS (Markdown na TUI; o TTS limpa para a voz)"
```

> `execute` recebe **dois** argumentos. Skill com um só quebra o roteamento.

> Resposta longa vinda do LLM pode sair em **stream**: `execute` devolve um iterável de pedaços de texto (ex.: o gerador de `query_ollama_stream`) em vez de `str`. O `brain` repassa pedaço a pedaço na TUI (`execute_command_stream`) e junta tudo no modo voz standalone (`execute_command`). Exemplo: `skills/productivity/screen_read.py`.

### `KEYWORDS` (pré-filtro do classificador)

Antes de chamar o Ollama, `services/intent.py` compara a mensagem (minúsculas, sem acento e sem pontuação) com as `KEYWORDS` de cada skill. Só o `PROMPT_TEXT` das skills que casaram vai para o prompt; se nenhuma casar, vão todas (como antes). Isso corta o prompt de ~6 mil caracteres para algumas centenas na maioria dos comandos e evita estourar o `OLLAMA_NUM_CTX`.

- Escreva sem acento. `"toc*"` casa o começo da palavra (toca, tocar, tocando); sem `*` só a palavra ou frase inteira (`"pr"` não casa "preciso").
- Inclua os verbos e substantivos que o usuário usaria, inclusive os citados no `PROMPT_TEXT`. Falta de palavra-chave só faz a skill sair do prompt quando **outra** skill casou.
- Skill sem `KEYWORDS` entra sempre (compatível com skills antigas).
- Mensagem trivial ("oi", "valeu", "ok, obrigado") nem chega ao classificador: vira `CHAT` direto (`intent.is_trivial`).

## Onde cada categoria roda

| Categoria | Chat | Copilot / voz |
|---|---|---|
| `automation` (mexe no PC) | não | sim |
| `system` (limpeza, energia, processos) | não | sim |
| `productivity` | sim | sim |
| `web` | sim | sim |

O Chat usa a lista branca `CHAT_ALLOWED_CATEGORIES = ("productivity", "web")` em `services/intent.py`: skills de outras categorias nem são oferecidas ao classificador, e o `brain` confere de novo antes de executar. O usuário ainda pode desligar qualquer skill ou categoria em `/skills`.

## Skills atuais

| Pasta | `INTENT` | O que faz |
|---|---|---|
| automation | `APP_CONTROL` | Abre, foca e fecha apps (busca fuzzy nos instalados) |
| automation | `AUDIO_CONTROL` | Volume relativo/absoluto e mudo (pycaw) |
| automation | `BROWSER_TABS` | Abas do navegador Chromium (abrir, fechar, ir para, listar, reabrir) pela UI Automation; fechar várias pede confirmação |
| automation | `CLIPBOARD` | Explica, traduz ou resume o que está copiado |
| automation | `KEYBOARD_CONTROL` | Digita, atalhos e teclas na janela em foco |
| automation | `SCREEN_CONTROL` | Brilho, protocolo "retina" (gamma) e mover janelas entre monitores |
| automation | `SOFTWARE_INSTALL` | Busca no winget e instala/baixa o instalador (sempre com confirmação) |
| automation | `SPOTIFY_CONTROL` | Play/pause/próxima sem LLM; busca de faixa com LLM (Premium para o player) |
| automation | `YOUTUBE_CONTROL` | "Toca X no YouTube" abre o vídeo direto; player por teclas oficiais (pausar, avançar, legenda, tela cheia, velocidade, próximo) |
| automation | `WORK_MACRO` | Cenas (trabalho, estudo…): abre apps, organiza janelas, silencia notificações |
| system | `SYSTEM_REPORT` | Relatório da máquina (também usado na saudação) |
| system | `SYSTEM_CLEANUP` | Esvazia a Lixeira, limpa temporários, desinstala app |
| system | `SYSTEM_SECURITY` | Bloquear, suspender, desligar, modo sentinela |
| system | `POWER_REPORT` | "Quanto o PC está gastando?" — watts agora, kWh e custo de hoje e do mês (`core/power.py`) |
| productivity | `CALENDAR` | Eventos do Google Agenda: dia (hoje, amanhã, dia da semana), semana, fim de semana, mês, ano, os próximos e a próxima reunião |
| productivity | `DAILY_BRIEFING` | Briefing do dia (`core/briefing.py`) |
| productivity | `EMAIL_MANAGEMENT` | Cartucho do Gmail: lê por prioridade e resume ("leia o e-mail 2"); responde/escreve com anexo e contato por nome (rascunho + "sim"); "apaga o e-mail 3" → Lixeira (30 dias) com confirmação; organiza a caixa (plano + "sim", nunca apaga). Ação escolhida por regex |
| productivity | `FOCUS_MODE` | Pomodoro e Não Perturbe |
| productivity | `REMINDER` | "Me lembra em 30 min de…", listar e cancelar lembretes |
| productivity | `INSIGHT_SAVE` | "Anota essa ideia: …" → 🧠 Brainstorms no Obsidian |
| system | `NETWORK_SCAN` | "Tem alguém na minha rede?" — varredura sob demanda |
| productivity | `GITHUB` | PRs, issues, último commit, CI; criar issue pede confirmação |
| productivity | `PRESENTATION_MODE` | Liga/desliga o Modo Apresentação |
| productivity | `SCREEN_READ` | Lê a janela/monitor pelo OCR do Windows (ou a página pela URL da aba) e explica, resume, traduz ou resolve |
| productivity | `TRAFFIC` | Tempo entre locais cadastrados com `/rota` |
| web | `WEB_SEARCH` | Pesquisa na web e resume com fontes |

## Criar uma skill

1. Crie `backend/skills/<categoria>/minha_skill.py` com `INTENT`, `PROMPT_TEXT`, `KEYWORDS` e `execute(entity, command)`.
2. Escreva o `PROMPT_TEXT` em `backend/prompts/skills/minha_skill.md` (nunca string no `.py`).
3. Se precisar do LLM, use `core.llm.query_ollama(..., format="json", temperature=0)` e um prompt `.md`. Resolva frases óbvias sem LLM primeiro (veja `parse_fast` em `focus_mode.py` e `github_control.py`).
4. Ação destrutiva ou externa (apagar, publicar, encerrar)? Não execute direto: arme com `core.pending.arm(tipo, pergunta, on_confirm, target=...)` e devolva a pergunta (modelo: `request_issue` em `github_control.py`). Nunca atribua `state.pending_critical_action` direto: `arm` devolve `None` quando já há outra pergunta aberta (responda `pending.BUSY_REPLY`), e só ele dá o `id` que impede o "sim" de uma pergunta executar outra. Nunca confie num campo `confirmed` vindo do LLM, e nunca passe texto do LLM para `shell=True`. A TUI abre a `ConfirmScreen`; a voz aceita "sim". O dono da pendência vem sozinho (`pending.current_owner()`): pela ponte Telegram/Discord só o "sim" daquela pessoa aprova. Para aceitar ajuste em vez de cancelar (ex.: "deixa mais formal"), passe `on_other=fn(frase)` — modelo: `confirm_send` em `services/email_compose.py`.
5. Faça imports pesados dentro de `execute`. Valide `entity` antes de passar para subprocesso.
6. Use `log` (nunca `print`) e devolva sempre uma string — erro vira mensagem amigável.
7. Escreva testes em `backend/tests/` (sem hardware real: mocke as chamadas de sistema).

A skill aparece em `/skills` e na paleta `Ctrl+K` no próximo boot.
