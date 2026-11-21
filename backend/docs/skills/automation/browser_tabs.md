# 🌐 Skill: browser_tabs.py

Controla as **abas** do navegador por voz: abrir aba nova (vazia, num site ou com uma busca), fechar a atual ou uma aba pelo nome/número, fechar as outras, ir para uma aba, próxima/anterior, reabrir a fechada, listar, recarregar, voltar/avançar, duplicar e abrir janela anônima. Categoria **automation**: só no Copilot (voz).

Só navegadores **Chromium** (Opera GX, Chrome, Edge, Brave, Vivaldi). Sem extensão e sem `--remote-debugging-port` — com ele qualquer processo local dirigiria o navegador logado.

## 📝 Contrato

- **INTENT**: `BROWSER_TABS`
- **PROMPT_TEXT**: `prompts/skills/browser_tabs.md`, com "NÃO use para…" contra `APP_CONTROL` (abrir/fechar o programa), `YOUTUBE_CONTROL`, `SCREEN_READ` e `WEB_SEARCH`.
- **KEYWORDS**: `aba`, `abas`, `guia`, `guias`, `navegador`, `recarreg*`, `anonim*`, `reabr*`.
- **Retorno**: `str`.

## ⚙️ Fluxo

```
execute(entity, command)
  ├─ parse()            regex, sem Ollama: "fecha a aba do youtube" → (CLOSE_TAB, "youtube")
  │   └─ _ask_llm()     só se nenhuma regex casar · browser_tabs_decision.md · ação validada em ACTIONS
  ├─ browser.find_browser_window()   janela Chromium mais recente na ordem Z (pula o terminal do JARVIS)
  └─ run()
        NEW_TAB      site conhecido/URL/busca → browser.open_url · vazia → Ctrl+T
        CLOSE_TAB    atual → Ctrl+W · por nome/número → list_tabs + match_tab → close_tab (botão "x" da UIA)
        GOTO_TAB     número/ordinal/nome → select_tab (UIA; Ctrl+1..9 de reserva) · site sem aba → abre nova
        LIST_TABS    list_tabs → lista numerada, marca a ativa
        CLOSE_OTHERS / CLOSE_ALL → pending.arm() com os títulos; só fecha depois do "sim"
        NEXT/PREV/REOPEN/RELOAD/BACK/FORWARD/INCOGNITO/DUPLICATE → atalho fixo (HOTKEYS)
```

Atalhos só saem depois de `browser.focus()` confirmar que o navegador está em primeiro plano. Sem foco, a resposta é `NO_FOCUS` e nenhuma tecla é enviada.

## 🔒 Segurança

- Texto do modelo nunca vira atalho: as ações saem de uma tabela fixa.
- Fechar várias abas (ou a janela) passa por `core/pending.py` (`ConfirmScreen` na TUI).
- `open_url` aceita só `http(s)://`.

## 🧪 Testes

- `tests/test_browser_tabs.py`: frases → ação sem LLM, atalho certo por ação, fechar/ir por nome e número, site sem aba, lista, confirmação de fechar várias (ordem da direita para a esquerda, poupa a ativa), `BUSY_REPLY`, sem navegador, sem foco, LLM com ação inválida.
- `tests/test_browser.py`: escolha da janela, `match_tab`, título limpo, UIA indisponível, atalho sem foco.
