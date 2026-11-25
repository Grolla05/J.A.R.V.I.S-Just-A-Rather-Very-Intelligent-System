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
| fonte citada "a favor" cujo **título** (da busca) desmente: "Mito:", "Desmentido:", "Por que NÃO…", "é fake/falso", "não é verdade/possível" | passa para "contra" |
| `CONFIRMADO` com menos de 2 a favor **ou com alguma contra** | `FALSO` (≥ 2 contra e nenhuma a favor), `IMPRECISO` (fontes dos dois lados) ou `INCONCLUSIVO` |
| `FALSO` com menos de 2 contra ou com ≥ 2 a favor | `IMPRECISO` ou `INCONCLUSIVO` — nunca vira `CONFIRMADO` (na dúvida, o lado cético) |
| regra mudou o veredito do modelo | a resposta avisa: "O modelo disse X, mas as fontes citadas não sustentam isso" |
| JSON inválido, veredito desconhecido, resumo vazio, modelo fora | `INCONCLUSIVO` |
| índice de fonte inexistente ou repetido | descartado |

O prompt manda julgar **só pelas fontes**, define os lados ("fonte que chama a afirmação de mito é CONTRA") e trata o conteúdo delas como dado, não instrução. Títulos colados pelo buscador ("…Mundo EducaçãoA muralha…") são cortados em `web.clean_title`.

Caso real que motivou as regras (25/11/2026): o gemma2:2b deu `CONFIRMADO` para "a Muralha da China é visível do espaço" citando "Desmentido: A Grande Muralha da China Não É Visível do Espaço" como a favor.

## 🧪 Testes

`tests/test_factcheck.py` (limpeza do pedido, texto longo → modelo, fontes por domínio e seguras, regras do veredito, fluxo completo com cache, domínio único sem modelo, nunca levanta, skill e `/clip checar`) e `tests/test_tui_tools.py::TestChecarCommand`.
