# ▶️ Skill: youtube_control.py

Controle completo do YouTube por voz: tocar ou pesquisar um vídeo, pausar/retomar, avançar ou voltar segundos, pular para uma parte, tela cheia, modo cinema, miniplayer, legendas, mudo, volume do vídeo, velocidade, próximo/anterior e "que vídeo é esse?". Categoria **automation**: só no Copilot (voz).

Só navegadores **Chromium** (Opera GX, Chrome, Edge, Brave, Vivaldi). Sem API key do YouTube.

## 📝 Contrato

- **INTENT**: `YOUTUBE_CONTROL`
- **PROMPT_TEXT**: `prompts/skills/youtube_control.md` — exige "YouTube" ou "vídeo" na frase; "toca Coldplay" continua no `SPOTIFY_CONTROL`. "NÃO use para…" contra Spotify, `AUDIO_CONTROL`, `BROWSER_TABS` e `SCREEN_READ`.
- **KEYWORDS**: `youtube`, `video`, `videos`, `legenda*`, `tela cheia`, `velocidade`, `cinema`, `miniplayer`, `avanc*`, `adiant*`, `retroced*`, `segundos` (os verbos do player: "avança 30 segundos" não cita o vídeo).
- **Retorno**: `str`.

## ⚙️ Fluxo

```
execute(entity, command)
  ├─ parse()              regex, sem Ollama · _ask_llm() só para o que sobrar (youtube_decision.md)
  ├─ PLAY                 core.youtube.find_video(q): youtube.com/results → 1º videoId (parse_results_html)
  │                       falhou → vídeos do ddgs (3 tentativas, DNSError intermitente)
  │                       sem vídeo / sem rede → página de resultados · browser.open_url
  ├─ SEARCH / OPEN_HOME   página de resultados / youtube.com
  ├─ NOW_PLAYING          título da aba do YouTube sem " - YouTube" e sem "(3)"
  └─ player
        locate()          janela cuja aba ativa é o YouTube; senão a aba do YouTube numa janela (UIA)
        select_tab()      se a aba estiver ao fundo
        send_hotkey()     teclas oficiais: k · j/l (10 s) · ←/→ (5 s) · 0–9 (%) · f · t · i · c · m
                          Shift+N/P · > / < · ↑/↓ (×4 = 20 %)
        restore_focus()   nas ações rápidas (pausar, pular, legenda, mudo…) o foco volta à janela anterior
```

- **Velocidade exata** ("velocidade 1.5"): o YouTube não informa a atual, então desce ao mínimo (`<` ×7 = 0,25×) e sobe o necessário com `>`.
- `k` alterna: "pausa" com o vídeo já pausado retoma.

## 🔒 Segurança

- Teclas só saem com o foco confirmado (`browser.focus()`); senão `NO_FOCUS`.
- Ações vêm de tabela fixa; texto do modelo é só termo de busca, que vai na URL (`quote_plus`).

## 🧪 Testes

- `tests/test_youtube.py`: `parse_results_html`, `pick_video`/`find_video` (página do YouTube primeiro, ddgs com nova tentativa, cai nos resultados), títulos, frases → ação sem LLM, conta de seek e velocidade, teclas por ação, aba de fundo selecionada antes, foco devolvido só nas ações rápidas, sem YouTube, sem foco, LLM.
