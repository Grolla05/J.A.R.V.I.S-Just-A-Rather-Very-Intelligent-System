# 🔎 Skill: fact_check.py

Verifica se uma afirmação ou notícia é verdadeira cruzando **fontes independentes** (domínios diferentes) e devolve um veredito com as fontes. Categoria **web**: roda no Chat e no Copilot (voz). Na TUI também existem `/checar <afirmação>` e `/clip checar` (o que foi copiado).

## 📝 Contrato

- **INTENT**: `FACT_CHECK`
- **PROMPT_TEXT**: `prompts/skills/fact_check.md`. "NÃO use para…" contra `WEB_SEARCH` (pesquisa aberta, sem afirmação a julgar).
- **KEYWORDS**: `verdade`, `fake`, `mentira`, `boato*`, `checa*`, `cheque`, `confer*`, `verific*`, `fato*`.
- **Entity**: a afirmação (a skill usa a frase inteira e limpa o pedido).
- **Retorno**: `str` (Markdown).

## ⚙️ Fluxo (`core/factcheck.py`)

```
check(texto)
  ├─ clean_claim            tira "isso é verdade:", "checa se", "é fake que"… (vazio → pede a afirmação)
  ├─ texto > 280 caracteres → modelo extrai a afirmação central (factcheck_claim.md, JSON)
  ├─ cache (10 min) pela afirmação
  ├─ gather_sources         busca a afirmação + "<afirmação> é verdade ou fake"
  │                         1 resultado por domínio, só URL pública (is_fetch_safe), até 5
  ├─ < 2 domínios           → INCONCLUSIVO sem chamar o modelo
  ├─ web.read_pages         texto das 3 primeiras (o resto vai com o trecho da busca)
  ├─ ask_verdict            factcheck_verdict.md → JSON {veredito, resumo, fontes_a_favor, fontes_contra}
  └─ parse_verdict          regras duras → render (selo, afirmação, resumo, [n] a favor/contra, Fontes)
```

## ⚖️ Regras que não dependem do modelo

| Situação | Resultado |
|---|---|
| menos de 2 domínios diferentes nas buscas | `INCONCLUSIVO` (sem modelo) |
| `CONFIRMADO` com menos de 2 fontes a favor citadas | `IMPRECISO` (se citou alguma) ou `INCONCLUSIVO` |
| `FALSO` com menos de 2 fontes contra citadas | idem |
| JSON inválido, veredito desconhecido, resumo vazio, modelo fora | `INCONCLUSIVO` |
| índice de fonte inexistente ou repetido | descartado |

O prompt manda julgar **só pelas fontes** e trata o conteúdo delas como dado, não instrução.

## 🧪 Testes

`tests/test_factcheck.py` (limpeza do pedido, texto longo → modelo, fontes por domínio e seguras, regras do veredito, fluxo completo com cache, domínio único sem modelo, nunca levanta, skill e `/clip checar`) e `tests/test_tui_tools.py::TestChecarCommand`.
