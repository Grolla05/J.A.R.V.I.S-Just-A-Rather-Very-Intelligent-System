# 🕶️ Skill: headless_task.py

Executa uma tarefa num site **em segundo plano**: o Microsoft Edge do Windows roda sem janela (Playwright, `channel="msedge"`), abre o site, busca, clica e traz a informação pedida. O resultado chega como aviso na conversa. Categoria **web**: roda no Chat e no Copilot (voz).

## 📝 Contrato

- **INTENT**: `HEADLESS_TASK`
- **PROMPT_TEXT**: `prompts/skills/headless_task.md`. "NÃO use para…" contra `WEB_SEARCH` (pesquisa sem site), `FACT_CHECK`, `WEB_WATCH` e abrir site na tela do usuário.
- **KEYWORDS**: `site`, `sites`, `segundo plano`, `headless`, `naveg*`, `entra no`, `entra na`, `acess*`, `pagina`.
- **Entity**: o pedido (a skill usa a frase inteira).
- **Retorno**: `str` imediato ("Executando em segundo plano…" ou a pergunta de confirmação); a resposta vem depois por `state.announce`.

## ⚙️ Fluxo (`services/headless_tasks.py` → `core/headless.py`)

```
request(frase)
  ├─ Edge e playwright presentes? outra tarefa rodando?  → explica e para
  ├─ plan               headless_plan.md → JSON {objetivo, passos}
  │                     sem plano e com link na frase → [goto link, extract]
  ├─ validate_steps     tipos fixos, ≤ 8 passos, 1º = goto, URL pública, sem dado sensível
  ├─ risky_steps        clique de enviar/comprar/cadastrar/login, Enter depois de um campo que não é busca
  │    └─ tem algum?    pending.arm("HEADLESS_TASK") com a lista de passos (⚠️ envia algo) → só roda no "sim"
  ├─ thread daemon      run_task: Edge sem janela, perfil próprio, um passo por vez
  ├─ headless_answer.md resposta só com o texto visível da página (dado, não instrução)
  └─ state.announce     "**Tarefa em segundo plano concluída** — objetivo … Página: url"
```

## 🧩 Passos

| Tipo | Campos | Observação |
|---|---|---|
| `goto` | `url` | Sempre o 1º; só `http(s)` público (`browser.is_fetch_safe`) |
| `fill` | `label`, `value` | Acha o campo pelo rótulo, placeholder ou nome acessível |
| `press` | `key` | Só `Enter`, `Tab`, `Escape`, `PageDown`, `ArrowDown` |
| `click` | `text` | Botão, link ou texto visível |
| `wait` | `seconds` | 0,5 a 5 s |
| `extract` | — | Copia o texto visível (`<main>` ou `<body>`); sem `extract`, copia no fim |

## 🔒 Segurança

| Regra | Onde |
|---|---|
| Nada de JavaScript vindo do modelo: só os 6 tipos acima | `validate_steps` |
| Navegação principal só para URL pública; recursos (imagem, script, XHR) só para host público — localhost e rede local abortados | `_guard` (rota do contexto) |
| Redirecionamento para endereço não permitido interrompe a tarefa | `run_task` |
| Senha, cartão, CVV, CPF/CNPJ/RG, passaporte, agência/conta, PIX, token/OTP nunca preenchidos: rótulo, valor com cara de CPF/cartão, `type=password` e `autocomplete=cc-*`/`*-password`/`one-time-code` | `validate_steps` + `_do_step` |
| Download desligado, service workers bloqueados, perfil próprio (`headless_profile/` na pasta de dados), sem login | `_edge` |
| Passo que envia algo só com confirmação explícita | `risky_steps` + `core/pending.py` |
| Uma tarefa por vez (lock); o Web Watch não espera — tenta no próximo ciclo | `_lock` |

## 🔁 Uso pelo Web Watch

`webwatch.check_price(url, rendered=headless.render_html)`: quando o HTML cru não traz o preço (loja que monta a página com JavaScript), tenta o HTML renderizado pelo Edge **antes** de perguntar ao modelo.

## ⚙️ Configuração

`HEADLESS_TIMEOUT` (s por página, padrão 30) e `HEADLESS_VISIBLE` (`True` abre a janela para depurar). Dependência: `playwright` (o setup não roda `playwright install`; usa o Edge que vem no Windows).

## 🧪 Testes

`tests/test_headless.py` (validação, passos que enviam algo, rotas, execução com página falsa, recusa de campo de senha, redirecionamento, uma tarefa por vez, texto visível com moeda, Web Watch renderizado, plano com fallback, confirmação, aviso, skill). Nenhum teste abre o Edge nem chama o Ollama.
