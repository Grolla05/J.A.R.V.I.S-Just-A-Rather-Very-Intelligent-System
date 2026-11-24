# 📓 obsidian.py (vault do Obsidian e RAG)

O `core/obsidian.py` liga o J.A.R.V.I.S ao **vault do Obsidian** do usuário, que funciona como memória de **longo prazo** (o SQLite guarda a de curto/médio prazo). Tudo passa pela API REST do plugin **Local REST API** (`OBSIDIAN_HOST` + `OBSIDIAN_API_KEY`). Não há MCP nem subprocesso: o `mcp-obsidian` (via `uvx`) foi removido em 19/11/2026 (#48).

## 🎯 Responsabilidades

1. **Cliente REST (`ObsidianClient`, instância `obsidian`)**: ler, buscar, listar e gravar notas.
2. **Memórias e insights**: `save_memory`/`get_memory` em `🚀 Projetos/J.A.R.V.I.S/Memória/{key}.md` e `append_note` nos insights mensais de `🧠 Brainstorms`.
3. **RAG (`get_vault_context`)**: antes de o Chat responder, procura a nota que responde à pergunta e devolve `(arquivo, trecho)` para o prompt.

---

## ⚙️ Cliente REST

| Método | O que faz |
|---|---|
| `search_scored(query, limit)` | **POST** `/search/simple/` (timeout `SEARCH_TIMEOUT_S` = 15 s). `[{filename, score}]`, maior score primeiro. **Levanta** se o Obsidian estiver fora |
| `search(query)` | Mesma rota (POST); devolve trechos `[arquivo]: contexto` |
| `search_results(query)` | Igual ao `search_scored`, mas `[]` em erro (tela `/vault`) |
| `get_file(path, quiet=False)` | Conteúdo da nota ou `None` |
| `list_dir(path)` | Itens de uma pasta (pastas terminam em `/`) |
| `get_memory` / `save_memory` | Memória da IA; **nunca sobrescreve** nota existente |
| `note_exists` / `append_note` | Distingue 404 de Obsidian fora; POST = append |

> [!warning] A busca simples é POST
> No plugin, `/search/simple/` só aceita **POST**. Um GET devolve 404, que o `_send` lê como "nada encontrado" — foi assim que a busca do RAG ficou vazia sem erro nenhum até 23/11/2026. O score do plugin é **negativo**: mais perto de zero = mais relevante (`VAULT_MIN_SCORE` segue essa escala).

---

## 🔍 RAG em 2 camadas (`get_vault_context`)

### Camada 1 — perfil pessoal
`_PROFILE_KEYWORDS` (palavra inteira, sem acento) → lê `⚙️ Configurações/🧠 Sobre mim.md` e `extract_relevant_section` corta a seção pedida (família, trabalho, setup…).

### Camada 2 — busca no vault

1. **Palavras do assunto (`search_keywords`)**: tira stopwords, conversa fiada e **palavras do pedido** (`_REQUEST_WORDS`: acesse, leia, nota, obsidian, diga, sobre, projeto…); só palavras com mais de 3 letras, até `_MAX_KEYWORDS` (4). Nome próprio ou sigla (com maiúscula) vai primeiro. "jarvis" só é descartado quando chama o assistente ("JARVIS, …" ou primeira palavra) — "projeto jarvis" é assunto.
   - *"JARVIS acesse meu obsidian e leia a nota sobre o meu projeto OHMFLOW"* → `ohmflow`.
2. **Busca**: `search_scored(palavras, limit=SEARCH_LIMIT)`. Vazia com vários termos (a busca simples exige todos) → tenta só o primeiro.
3. **Ranking local (`_rank`)**: caminho que cita as palavras > nota principal da pasta (`Pasta/Pasta.md` ou `index.md`) > score do plugin. Sem isso, uma nota que só *menciona* o termo (ex.: o CHANGES de outro projeto) ganhava das notas do próprio projeto. `_templates/` fica de fora.
4. **Nota principal (`_main_note`)**: se a pasta é o assunto (`🚀 Projetos/OhmFlow/…`), lê `OhmFlow.md`/`index.md` — é onde fica o resumo. Exceção: o nome da nota cita outra palavra da pergunta ("arquitetura do OhmFlow" → `OhmFlow - 02 Arquitetura.md`).
5. **Filtros**: score abaixo de `VAULT_MIN_SCORE` (opcional) ou nota que não cita ao menos metade das palavras (`_is_relevant`) → `("", "")`.

### Nota pedida e não encontrada
`asks_vault(texto)` detecta pedido explícito ("obsidian", "vault", "nota", "anotação", "meu projeto"…). Se o vault não trouxe nada, o `brain` passa `vault_missing=True` e o `chat` injeta `prompts/vault_not_found.md`: o JARVIS diz que não achou e pergunta o nome exato, em vez de inventar. O aviso é uma instrução simples, sem tag — modelos pequenos (gemma2:2b) copiavam blocos com tag palavra por palavra.

A nota encontrada entra como `prompts/vault_memory.md` (`[MEMÓRIA DO VAULT — arquivo]`, a mesma tag que o `system_prompt.md` cita) e a resposta usa temperatura 0,1.

Obsidian fora do ar: aviso **uma vez** por sessão (`_warn_vault_down`), depois só no log; o chat segue sem contexto.

---

## 🛠️ Manutenção

- **Caminhos com acento/emoji** sempre por `urllib.parse.quote(..., encoding="utf-8")` — sem isso, 404.
- **Assunto pessoal novo no "Sobre mim"**: acrescente um termo sem ambiguidade em `_PROFILE_KEYWORDS` e um caso em `tests/test_vault_keywords.py`.
- **Palavra de pedido nova** pegando vaga da busca (ex.: "verifique"): acrescente em `_REQUEST_WORDS` e um caso em `tests/test_vault_search.py`.
- Testes: `test_obsidian_endpoint.py`, `test_vault_keywords.py`, `test_vault_search.py`.
