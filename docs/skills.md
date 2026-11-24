# Skills — contrato e como criar uma nova

Toda ação do JARVIS (abrir app, tocar música, consultar agenda…) é uma skill. Resumo do projeto em [`AGENTS.md`](../AGENTS.md); regras gerais em [`regras-backend.md`](regras-backend.md).

## Contrato obrigatório

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

> ⚠️ `execute()` recebe **2 argumentos**: `entity` e `command`. Skills antigas com 1 argumento quebrarão o routing.
> `execute()` devolve `str` ou, para resposta longa do LLM, um iterável de pedaços (stream): o `brain` repassa na TUI e junta na voz (ex.: `SCREEN_READ`).
> No modo **Copilot** (e no modo voz) todas as skills executam. No modo **Chat** só as **ativas** das categorias em `CHAT_ALLOWED_CATEGORIES` (`productivity` e `web`, lista branca em `services/intent.py`): o classificador roda com `allowed_categories=` e o `brain` confere `skill_allowed_in_chat()`. Categoria nova fica fora do Chat até entrar na lista. Productivity e web (agenda, trânsito, GitHub, busca, briefing, foco, apresentação, leitura de tela) rodam nos dois modos.
> Dado externo que o Chat precisa responder (ex.: agenda) entra como contexto via `services/live_context.py` (detecção por palavra-chave + bloco de sistema em `prompts/*_context.md` com "não invente") — nunca deixe o LLM responder sobre dado pessoal sem a fonte no prompt.

## Como criar uma nova skill

1. Criar arquivo em `backend/skills/{categoria}/nome_da_skill.py`
2. Declarar `INTENT`, `PROMPT_TEXT`, `CATEGORY` e `execute(entity, command)`
3. A skill é **auto-descoberta** pelo `SkillLoader` no próximo boot — sem registro manual
4. Ela aparece em `/skills`. Categorias `automation`/`system` só rodam no Copilot (ou voz); `productivity`/`web` rodam também no Chat
   - Skill com intent parecido com outro precisa de um exemplo em `prompts/classify_intent.md` e de um "NÃO use para…" no próprio `PROMPT_TEXT` (ex.: `INSIGHT_SAVE` × `MEMORY_WRITE`, `REMINDER` × `CALENDAR`)
5. Guia completo (contrato, confirmação de ação crítica, testes): `backend/skills/README.md`. Visão ponta a ponta do projeto: [`arquitetura.md`](arquitetura.md)
