# Backend — regras e convenções

Regras de código do backend. Leia antes de alterar qualquer arquivo em `backend/`. Resumo do projeto e workflow em [`AGENTS.md`](../AGENTS.md). Banco de dados em [`banco-de-dados.md`](banco-de-dados.md); skills em [`skills.md`](skills.md).

## Logging

- **Proibido `print()`** em qualquer arquivo. Sempre: `from core import log` → `log.info()` / `log.warning()` / `log.critical()`
- **Nunca escrever direto em `sys.stdout`** — corrompe a tela da TUI. Para mostrar algo ao usuário use `state.announce(texto)` (ou `speak()`, que já passa por ele)
- Com a TUI ativa, `log.use_tui()` desliga o console; WARNING+ vira notificação na tela e tudo segue no arquivo `backend/logs/`
- `log.debug()` para loops, streaming e tracking de variáveis
- `log.critical()` apenas antes de `sys.exit(1)`

## Ollama (LLM)

- **Proibido `requests.post`** para chamar o Ollama diretamente nos serviços principais
- Sempre usar: `from core.llm import query_ollama, query_ollama_stream`
- `query_ollama(messages, format='json', temperature=0)` para classificação/extração
- `query_ollama_stream(messages, temperature=0.7)` para o chat da TUI

## Prompts

- **Proibido hardcodar prompts como strings Python** dentro de arquivos `.py`
- Sempre criar um arquivo `.md` em `backend/prompts/` e usar: `from core.prompts import load_prompt`
- Variáveis no `.md`: sintaxe `$variavel` (string.Template)
- `load_prompt("arquivo.md", variavel=valor)` → retorna a string com substituição

## Threading

- Toda I/O pesada disparada pela TUI **deve** rodar em worker de thread (`@work(thread=True)`) e voltar para a tela com `self.call_from_thread(...)` — nunca mexer em widget fora da thread da UI
- Toda nova `threading.Thread` **deve** ter `daemon=True` (garante que `os._exit(0)` no fim do `main.py` a destrua)
- A `speech_lock` do `speak.py` **nunca deve ser removida**

## Sentidos (voz) — imports sem efeito colateral

- Voz é **opcional** e começa desligada (`state.voice_enabled = False`); liga com `/voice` ou `Ctrl+T`
- **Proibido** abrir microfone, pyttsx3 ou pygame no import de módulo. `services.listen` usa `get_ear()` lazy e `speak.py` inicializa os motores na 1ª fala
- Em outros módulos, importe `listen`/`speak` **dentro da função** que usa (import tardio), como em `core/alerts.py`

## Estado global

- `sys_monitor`, `pending_critical_action`, `voice_enabled` e `announce` vivem em `core/state.py`
- Acesso: `import core.state as state` → `state.sys_monitor` / `state.pending_critical_action`
- Ação crítica pendente: **só** por `core/pending.py` — `arm()` (não sobrescreve pendência válida, devolve `None`; responda `pending.BUSY_REPLY`), `take(id)` e `parse_reply()` (só frase de confirmação aprova). Toda pendência tem `owner` (padrão `pending.current_owner()`: `local` na TUI/voz; `canal:usuário` na ponte, via `pending.owner_scope` no brain) — só resposta do mesmo dono a resolve. `on_other(frase)` trata pedido de ajuste (ex.: "deixa mais formal" num rascunho de e-mail); negação pura vence. Nunca atribuir `state.pending_critical_action` direto fora dos testes; nunca confiar em `confirmed` vindo do LLM; nunca passar texto do LLM para `shell=True`
- **Nunca** instanciar `SystemInfo()` novamente em outros módulos

## Configurações

- **Nunca** usar `os.getenv("CHAVE")` diretamente em `brain.py`, na TUI ou em skills
- Toda variável do `.env` deve ser declarada em `core/config.py` como atributo da classe `Settings`
- Lista das variáveis: [`variaveis-ambiente.md`](variaveis-ambiente.md)

## Privacidade

- Nova integração externa (API, site, serviço) ou dado novo guardado no disco **exige** atualizar [`politica-de-privacidade.md`](politica-de-privacidade.md) (seções 2 e 4) e, se mudar o que o JARVIS faz no PC, os [`termos-de-uso.md`](termos-de-uso.md)
- Tudo que envia dados do usuário para fora do PC fica **desligado por padrão** ou depende de conexão explícita do usuário (card em `/config` → INTEGRAÇÕES)
- Nunca usar API de IA em nuvem para o conteúdo do usuário: a IA é local (Ollama)
