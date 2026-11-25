# 📝 Skill: form_fill.py

Preenche um formulário de um site com o que o JARVIS já sabe do usuário, numa **janela do Edge** (o usuário vê tudo), e **para antes do envio**: só envia com "sim". Categoria **productivity**: roda no Chat e no Copilot (voz). Na TUI também existe `/formulario [link]`.

## 📝 Contrato

- **INTENT**: `FORM_FILL`
- **PROMPT_TEXT**: `prompts/skills/form_fill.md`. "NÃO use para…" contra `HEADLESS_TASK`, `EMAIL_MANAGEMENT` e `MEMORY_WRITE`.
- **KEYWORDS**: `formulario*`, `preench*`, `cadastro`, `inscricao`, `inscricoes`, `form`, `forms`, `complet*`.
- **Entity**: o link, se houver (a skill junta à frase); sem link usa a aba aberta no navegador.
- **Retorno**: `str` (resumo + pergunta de confirmação).

## ⚙️ Fluxo (`services/form_fill.py` → `core/headless.FormSession`)

```
request(frase)
  ├─ link: da frase → aba ativa do navegador; só URL pública (is_fetch_safe)
  ├─ FormSession: Edge COM janela numa thread própria → lê os campos (_FIELDS_JS, script fixo)
  ├─ load_profile        Sobre mim.md (linhas "- **Campo:** valor" + links GitHub/LinkedIn)
  │                      + e-mail da conta Google + endereço de casa do /rota (cache 5 min)
  ├─ map_fields          sensível → nunca · já preenchido → mantém
  │                      autocomplete → type (email/tel) → nome/id/rótulo/placeholder (regras)
  │                      o que sobrou → form_map.md: o modelo escolhe só a CHAVE do perfil (ou null)
  ├─ preenche            na thread do navegador (fila)
  └─ pending.arm("FORM_SUBMIT")  resumo "campo → valor" + "Não preenchi: …"
        ├─ sim            clica no botão de envio do <form> (ou "Enviar"/"Submit") → "Formulário enviado"
        ├─ não            não envia; a janela fica aberta e preenchida para o usuário terminar
        └─ outra frase    "o telefone é 19 9…" → corrige o campo com o valor DITO e pergunta de novo
```

## 🔒 Segurança

| Regra | Onde |
|---|---|
| Valores só do perfil ou da fala do usuário; o modelo nunca escreve valor, só escolhe uma chave entre as oferecidas | `map_fields` |
| Senha, cartão, CVV, CPF/CNPJ/RG, passaporte, agência/conta, PIX, token/OTP nunca preenchidos (rótulo, nome/id com `_`/camelCase, placeholder, `type=password`, `autocomplete=cc-*`/`*-password`/`one-time-code`, valor com cara de CPF/cartão) — nem pelo perfil, nem pelo modelo, nem pelo ajuste | `headless.is_sensitive_input` + `fill_field` + `adjust` |
| Envio só com confirmação explícita; tempo esgotado não envia | `core/pending.py` |
| Campo já preenchido não é sobrescrito | `map_fields` |
| Só campos de texto (`text`, `email`, `tel`, `url`, `search`, `textarea`, `select`) recebem dado do perfil; data, hora e número ficam com o usuário (o gemma2 já mapeou "Preferred delivery time" para a cidade) | `TEXT_TYPES` |
| Só URL pública; redirecionamento proibido fecha a sessão | `FormSession._run` + `_guard` |
| Janela aberta no máximo 30 min (2 min depois do envio); uma navegação por vez | `FormSession` |

## 🧪 Testes

`tests/test_form_fill.py` (perfil do Obsidian sem CPF nem placeholder, fontes do perfil, regras + lista negra + modelo só para o resto, modelo não inventa valor nem usa chave fora da lista, campo já preenchido, sensíveis por tipo/autocomplete/nome, fluxo com "sim"/"não", ajuste pela fala, ajuste sensível recusado, link/endereço/erro/sem campos, confirmação ocupada, skill, `FormSession` com página falsa: preencher, recusar senha, enviar, fechar, janela fechada pelo usuário, redirecionamento) e `tests/test_tui_tools.py::TestFormularioCommand`.
