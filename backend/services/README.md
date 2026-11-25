# `backend/services/` — roteamento, conversa, voz e rotinas

Os serviços ficam entre a interface e o `core/`. Recebem texto (digitado ou falado), decidem o que fazer e devolvem texto em stream.

## Pipeline

```
texto (TUI ou voz)
  └─ brain.execute_command_stream(texto, session_id, images, mode, on_route)
       ├─ ação crítica pendente?  → confirm_pending_action (sim/não)
       ├─ intent.classify_intent  → Ollama em JSON {intent, entity, confidence}
       │     Chat: allowed_categories=("productivity", "web")
       ├─ MEMORY_WRITE            → memory.extract_fact_to_memory → Obsidian
       ├─ skill ligada/permitida  → on_route(intent) → skill.execute(entity, texto)
       │     str → 1 pedaço · iterável (ex.: SCREEN_READ) → repassado em stream
       └─ CHAT / HARDWARE / MEMORY_READ
             → chat.ask_local_ai_stream(histórico + vault + live_context + telemetria)
```

`execute_command` (sem stream) é a versão do modo voz standalone (`python -m services.brain`), sempre com todas as skills; resposta de skill em stream é juntada num texto só.

## Módulos

| Módulo | Papel |
|---|---|
| `brain.py` | Roteador. Modos `chat` (só skills ativas de `productivity`/`web`) e `copilot` (todas). `force_chat=True` manda direto ao LLM (trecho a explicar). `confirm_pending_action(approved, explicit_decline)` executa `pending['on_confirm']`, ou `pending['on_decline']` na recusa explícita, ou encerra o processo-alvo |
| `intent.py` | `classify_intent(texto, skip_skills, allowed_categories)` com cache TTL (30 s, 64 entradas). Intents fixos: `HARDWARE`, `MEMORY_READ`, `MEMORY_WRITE`, `CHAT`, mais os `INTENT` das skills ligadas. `is_skill_enabled`, `skill_allowed_in_chat` |
| `chat.py` | `build_messages` monta: `system_prompt.md` + regras do modo (`mode_chat.md`, `mode_copilot.md` ou `mode_voice.md`) + `hardware_context.md` (intent `HARDWARE`) ou `memory_read.md` (intent `MEMORY_READ`) + `live_data.md` (telemetria) + `vault_memory.md` (nota do vault) ou `vault_not_found.md` (`vault_missing`: pediu nota e o vault não achou) + `live_context` + últimas 8 mensagens da sessão. Nenhum texto de prompt no `.py`. Imagens vão para o modelo de visão (`vision_context.md`) |
| `live_context.py` | Pergunta sobre agenda ("o que tenho amanhã?") → eventos reais do Google Agenda no prompt, com instrução de não inventar |
| `memory.py` | Extrai chave/valor de "lembre que…" e grava em `🚀 Projetos/J.A.R.V.I.S/Memória/{chave}.md` |
| `reminders.py` | Lembretes contextuais. Agenda: `due()` decide os avisos de cada evento (LEAD = antecedência, LEAVE = hora de sair com tempo de trajeto, FINAL = início iminente), dedup por `id|início|tipo`; `phrase()` pede a frase ao LLM (`reminder.md`) e cai no texto fixo se o horário não vier certo. Pedido: tabela `reminders`, `parse_when()` por regex. `collect()` junta tudo para a TUI |
| `insights.py` | Registro de insights: `worth_checking()` filtra sem LLM, `extract()` pergunta ao modelo (`extract_insight.md`), `save()` anexa na nota mensal de 🧠 Brainstorms (dedup de 7 dias, fila `insights_pending` com o Obsidian fora) |
| `clip_history.py` | Histórico do clipboard no SQLite (200 cópias, recopiar sobe o item): `add`, `recent`, `search`, `get(n)`, `clear`; `looks_secret()` descarta senhas/tokens |
| `net_guard.py` | Guarda de rede: `judge()` (LLM, `judge_connection.md`), `handle()` (alerta + confirmação para encerrar o processo), `kill_process`, `block_ip` (só elevado), textos do `/rede` e do bloco PERÍMETRO do `/status` |
| `sessions.py` | Sessões e histórico (listar, renomear, fixar, apagar, editar a partir de uma mensagem). `to_local()` converte o UTC do SQLite |
| `skill_settings.py` | Lista skills e liga/desliga skill ou categoria (`disabled_skills`, `disabled_categories` na tabela `config`) |
| `user_prefs.py` | Preferências do `/config`: voz, velocidade, volume, sensibilidade do mic, janela de atenção, briefing automático, manchetes, manchetes escolhidas pela IA (`news_ai`), monitor de clipboard, registro de insights, aviso de saída, lembretes da agenda (antecedência e aviso final), vigia de rede, silêncio em reunião/tela cheia, apresentação automática |
| `integrations.py` | Cards de `/config` → INTEGRAÇÕES. Estados `on`/`wait`/`off`/`setup`; `connect`/`disconnect` devolvem texto e nunca levantam |
| `listen.py` | Ouvido lazy (`get_ear()`): mic só abre com a voz ligada; wake word (`WAKE_WORDS`) por palavra inteira; Google STT; janela de atenção; `ear_pause`/`ear_resume`; nível do mic para a `VoiceStage` (espectro e VU) |
| `speak.py` | TTS: edge-tts (voz da pref, padrão `pt-BR-AntonioNeural`) com fallback pyttsx3; `speech_lock`; limpa Markdown e símbolos e expande gírias (`SLANG_MAP`); no-op com a voz desligada ou em apresentação |
| `focus.py` | `FocusManager`: Pomodoro (25/5, longa 15 a cada 4) e Não Perturbe (toasts do Windows off + backlog de alertas com resumo no fim) |
| `presentation.py` | Modo Apresentação manual (`/silent`, skill) ou automático (PowerPoint, Canva, Google Slides, PDF em tela cheia) |
| `mailbox.py` | Caixa de entrada para TUI/voz/briefing/ponte: lista priorizada (o cache é a numeração que o usuário viu), resumo do corpo como **dado**, VIP, `/email` |
| `email_triage.py` | Prioridade (ALTA/MÉDIA/BAIXA) e categoria (urgente/financeiro/promoções/social) — regras puras |
| `email_compose.py` | Rascunho pelo LLM (só assunto e corpo); `confirm_send` arma a pendência (180 s): sim envia · não salva rascunho no Gmail · outra frase refaz (`on_other`); assinatura em `email_signature` |
| `email_contacts.py` | "Guilherme" → endereço (tabela `email_contacts` + histórico do Gmail; vários = pergunta) |
| `email_organize.py` | Plano (arquivar promoções/social, marcadores `JARVIS/Financeiro` e `JARVIS/Urgente`) → "sim" → `batch_modify`; nunca apaga |
| `email_trash.py` | "Apaga o e-mail 3" / "as promoções" → lista → "sim" → Lixeira do Gmail (o que apagar vem só da fala) |
| `local_files.py` | Acha arquivo do usuário para anexar (Área de Trabalho, Documentos, Downloads, OneDrive); bloqueia sensíveis, fora do perfil e >25 MB |
| `software.py` | Download inteligente: winget → confirmação → instala/baixa numa thread e anuncia |
| `remote_chat.py` | Núcleo da ponte Telegram/Discord: allowlist (`*_ALLOWED_IDS`), sessão por usuário (`remote_session:<canal>:<id>`), `brain` em modo Chat com `owner` `canal:usuário`, divide a resposta no limite da plataforma (Telegram 4000, Discord 1900) |
| `net_trust.py` | Softwares mantidos no Vigia de rede (tabela `net_trusted_apps`: nome + executável); conferido antes do juiz e sobrevive ao `/rede reset` |
| `notify_filter.py` | Prioridade do alerta (`critical`/`high`/`normal`) × contexto (apresentação, DND, reunião, tela cheia) → falar, guardar ou descartar; selo da linha de status |

## Regras

- `listen` e `speak` nunca são importados no topo de outros módulos (import dentro da função).
- A `speech_lock` do `speak.py` não pode ser removida.
- Ações do `FocusManager` devolvem texto; só troca de fase e fim de prazo anunciam sozinhas.
- Dado pessoal que o Chat precisa responder entra como contexto (`live_context`), nunca deixado para o LLM adivinhar.
