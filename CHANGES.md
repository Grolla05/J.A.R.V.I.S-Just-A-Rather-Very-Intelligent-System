# CHANGES.md

Registro das mudanças aplicadas no J.A.R.V.I.S.

**Data:** 2026-09-28
**Escopo:** Multimodalidade no Chat Mode — upload de imagem (análise via modelo de visão local) e upload de áudio (transcrição local via Whisper).

---

## Resumo

| # | Feature | Arquivos |
|---|---------|----------|
| 1 | Upload de imagem no chat → resposta via modelo de visão Ollama (Moondream) | `core/config.py`, `core/llm.py`, `services/chat.py`, `services/brain.py`, `core/bridge.py`, `core/database.py`, `core/uploads.py` (novo), `prompts/vision_context.md` (novo) |
| 2 | Upload de áudio no chat → transcrição local via faster-whisper, preenchendo a caixa de texto | `core/config.py`, `core/transcription.py` (novo), `core/uploads.py` (novo), `core/bridge.py` |
| 3 | Frontend: anexar/arrastar imagem ou áudio, preview real de imagem, botão de clipe único | `ChatInput.jsx`, `ChatPanel.jsx`, `MessageList.jsx`, `AttachmentPreview.jsx` (novo), `BridgeAPI.js` |

---

## 1. Upload de imagem — análise via modelo de visão

**O quê:** usuário anexa/arrasta uma imagem no Chat Mode e faz uma pergunta sobre ela (ex: "o que é isso?", "descreve o erro nessa screenshot"). A resposta é gerada por um modelo de visão local via Ollama (**Moondream** por padrão, configurável) e streamada na UI exatamente como uma resposta de texto normal.

**Backend:**
- `core/config.py`: novos settings `OLLAMA_VISION_MODEL` (default `moondream`), `OLLAMA_VISION_KEEP_ALIVE` (default `5m` — não fica residente na VRAM como o modelo de chat principal), `TIMEOUT_VISION`, `DIR_UPLOADS`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_IMAGE_MIME`/`ALLOWED_AUDIO_MIME`.
- `core/llm.py`: `query_ollama`/`query_ollama_stream` ganharam `model=` e `keep_alive=` opcionais (default preserva comportamento atual).
- `core/uploads.py` (novo): `save_base64_upload()` valida mime/tamanho e grava o anexo em `backend/uploads/<kind>/`; `read_upload_as_data_url()` relê um anexo salvo pra reconstruir preview ao reabrir sessão antiga.
- `prompts/vision_context.md` (novo): instrução curta e dedicada pro modelo de visão — não reusa o system prompt completo do JARVIS (personalidade/telemetria/histórico), já que modelos pequenos como Moondream degradam com contexto irrelevante.
- `services/chat.py`: `ask_local_ai_stream()` ganhou parâmetro `images=None`; quando presente, monta uma lista de mensagens mínima (`vision_context.md` + pergunta + imagem) e chama `query_ollama_stream(model=OLLAMA_VISION_MODEL, keep_alive=OLLAMA_VISION_KEEP_ALIVE)`.
- `services/brain.py`: `execute_command_stream()` ganhou passthrough `images=None`.
- `core/bridge.py`: `chat_message(text, session_id, images=None)` — salva a(s) imagem(ns) recebida(s) (base64) em disco, loga a interação com referência ao anexo, e repassa pro pipeline de streaming existente (zero mudança no lado de recebimento do frontend).
- `core/database.py`: tabela `history` ganhou colunas `attachment_type`/`attachment_path` (migração automática via `PRAGMA table_info` + `ALTER TABLE`, retrocompatível com bancos existentes). `get_chat_history` (bridge.py) relê imagens do disco como data URL pra reconstruir o preview ao reabrir uma sessão.

**Frontend:**
- `ChatPanel.jsx`: `handleFileChange` reescrito como `processFiles()` — agora lê o `File` de verdade via `FileReader` (base64), em vez de descartá-lo (comportamento anterior só guardava nome/ícone). `handleSend` monta o payload de imagem e chama `chat_message(text, sessionId, imagePayload)`.
- `ChatInput.jsx`: `accept="image/*,audio/*"` no input de arquivo; adicionado drag-and-drop na área do input (spring transition, sem duplicar lógica — reusa `processFiles`).
- `MessageList.jsx` / `AttachmentPreview.jsx` (novo): imagens anexadas agora renderizam thumbnail real (`<img>`) na bolha da mensagem, não só um chip com nome de arquivo.

---

## 2. Upload de áudio — transcrição local via Whisper

**O quê:** usuário anexa um arquivo de áudio no chat. Ao enviar, o áudio **sempre** intercepta o envio (mesmo com texto já digitado) e é transcrito localmente via **faster-whisper** (modelo `base`, PT-BR). O texto preenche a caixa de input — **não é enviado automaticamente**, o usuário revisa e aperta Enviar.

**Backend:**
- `core/config.py`: `WHISPER_MODEL_SIZE` (default `base`), `WHISPER_DEVICE` (`auto`/`cpu`/`cuda`), `WHISPER_COMPUTE_TYPE` (`int8`), `TIMEOUT_TRANSCRIPTION`.
- `core/transcription.py` (novo): `transcribe_audio_file()` — singleton lazy do `WhisperModel` (carrega só na 1ª transcrição, não trava o boot).
- `core/bridge.py`: novo método `transcribe_audio(audio_b64, mime_type, filename)` — síncrono do ponto de vista do frontend (`await callApi(...)`), roda a transcrição numa thread própria com `.join()` internamente (segue a convenção do projeto de I/O pesado rodar em thread). Retorna `{"success": bool, "text"/"error": ...}`. Não loga no histórico nem passa pelo LLM — é uma ação isolada de transcrição.

**Frontend:**
- `ChatPanel.jsx`: `handleSend` — qualquer arquivo de áudio anexado sempre dispara `transcribe_audio(...)` em vez de `chat_message(...)`; resultado é concatenado no `inputValue`.
- `BridgeAPI.js`: mock fallback pra `transcribe_audio` (modo browser-dev sem pywebview).

---

## Dependências novas

`backend/requirements.txt`: `faster-whisper`, `Pillow`.

**Passos manuais necessários antes de testar:**
```bash
ollama pull moondream
cd backend && pip install -r requirements.txt
```

---

## Limitações conhecidas / follow-ups não implementados

- Sem OCR dedicado (Tesseract) — decisão explícita do usuário, só modelo de visão puro (Moondream).
- Envio de múltiplas imagens numa mesma mensagem: só a primeira é persistida com `attachment_path` no histórico (todas são enviadas ao modelo de visão, mas só uma fica referenciada pra preview ao reabrir sessão).
- Sem pré-aviso de "modelo de visão não baixado" — se `ollama pull moondream` nunca rodou, o erro cai no tratamento genérico já existente (`query_ollama_stream`).
- Sem redimensionamento client-side de imagens grandes antes do envio (mitigado por `MAX_UPLOAD_SIZE_MB=15` no backend).

---

# Otimização de performance do frontend — Fase 1: streaming do chat

**Data:** 2026-09-29
**Escopo:** reduzir re-renders e re-parse de markdown/KaTeX durante o streaming de respostas no Chat Mode.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `MessageItem` com `React.memo`; `MarkdownBody` memoizado por texto; plugins do ReactMarkdown como constantes de módulo | `CHAT/MessageList.jsx` |
| 2 | Chunks do stream acumulados num buffer e aplicados 1x por frame (`requestAnimationFrame`); `isDone` faz flush síncrono | `ChatPanel.jsx` |
| 3 | Scroll `auto` durante o streaming (antes: um `smooth` novo por chunk) | `CHAT/MessageList.jsx` |
| 4 | Handlers de editar/regenerar estáveis (leem `messagesRef`), não trocam identidade a cada chunk | `ChatPanel.jsx` |
| 5 | Último-mensagem-do-usuário por loop reverso em `useMemo` (antes: cópia + reverse do array a cada render) | `CHAT/MessageList.jsx` |
| 6 | `JarvisPixelAvatar` memoizado; `animate-pulse` só fora de `idle` (avatares de mensagens antigas ficam estáticos) | `CHAT/JarvisPixelAvatar.jsx` |
| 7 | App passa `hasMessages` (boolean) ao orb em vez de ler `chatMessages.length` várias vezes; `console.log` removido dos listeners quentes (`receiveStatus`, `updateHudState`) | `App.jsx` |
| 8 | Vitest + Testing Library (dev): testes de batching do stream, flush no `isDone`, markdown e scroll | `vite.config.js`, `package.json`, `components/__tests__/chatStreaming.test.jsx` |

**Decisão:** `chatMessages` permanece no `App` (não foi movido para o `ChatPanel`) porque o histórico precisa sobreviver à troca de modo — `ChatPanel` desmonta em talk/code.

**Como testar:** `cd frontend && npm test && npm run lint && npm run build`.

---

# Simplificação da interface e redução de RAM — Fase 2

**Data:** 2026-09-29
**Escopo:** remover a tela CODE e dependências mortas, achatar a UI (sem blur) e deixar o chat minimalista.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **Removido o modo CODE** e a tela de seleção de modo (boot entra direto em `talk`; troca só pelo header Copilot/Chat) | `App.jsx`, `HeaderNavigation.jsx`, `CORE/NavIcons.jsx`; removidos `CodePanel`, `CODE/*`, `JarvisPixelReactor`, `ModeSelectionScreen` |
| 2 | **Removidas deps sem uso:** `@react-three/postprocessing`, `animejs`, `path`, `@tailwindcss/postcss` | `package.json` |
| 3 | **Orb reescrito:** 1 canvas (antes 2 + `mix-blend-screen`), 140 partículas (antes 320), sem linhas de conexão, sem `blur(60px)`, sem lente com `backdrop-filter`, 10fps em idle / 30fps ativo, pausa com a janela oculta, DPR limitado a 2, `React.memo` | `LiquidAuraReactor.jsx`; removido `ReactorCoreLens` |
| 4 | **Zero `backdrop-filter`** no app (havia ~20 camadas, incluindo a janela inteira) | `App.jsx`, `index.css`, `SkillsSidebar`, `JarvisSubtitles`, `LiveTelemetry`, `StartupScreen`, header, chat |
| 5 | **Chat simplão:** sem avatar, sem bolha do Jarvis (texto direto), bolha simples do usuário, ações em texto (Copiar/Editar/Regenerar), "Pensando…" em vez de bolha animada, input e sidebar chapados | `CHAT/MessageList.jsx`, `ChatInput.jsx`, `ChatSidebar.jsx`, `ChatPanel.jsx`; removido `JarvisPixelAvatar` |
| 6 | `ChatPanel` (markdown + KaTeX) carregado sob demanda com `React.lazy`; `manualChunks` com match exato (antes `includes('react')` puxava react-markdown e lucide) | `App.jsx`, `vite.config.js` |
| 7 | CSS: removidos `@import` do Google Fonts (fonte do sistema, funciona offline), scanline/glitch/tech-grid sem uso, `App.css` órfão; `.hud-critical-mode` anima só `opacity` | `index.css` |
| 8 | CLAUDE.md atualizado: sem modo `code`; Lei 2 agora proíbe `backdrop-filter` | `CLAUDE.md` |

**Bundle (JS carregado no startup):** ~870KB → ~380KB (index 34KB + framer 136KB + react 211KB). O chat (449KB) só carrega ao abrir o modo Chat.

**Observação de RAM:** não foi medida com profiler. As mudanças atacam as maiores fontes prováveis de memória no WebView2 (superfícies de compositing de `backdrop-filter`, canvases com blend, camadas com blur). Comparar antes/depois no Gerenciador de Tarefas (processos `msedgewebview2`).

---

# Ollama: opções de VRAM (`num_ctx` / `num_gpu`) com fallback

**Data:** 2026-09-29
**Escopo:** permitir empurrar o modelo para a VRAM sem risco de derrubar o chat.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Novas settings opcionais `OLLAMA_NUM_CTX` e `OLLAMA_NUM_GPU` (vazio = não repassa; comportamento atual preservado). `0` é respeitado (tudo na CPU) | `core/config.py` |
| 2 | `_build_options()` centraliza `options`; `query_ollama`, `query_ollama_stream` e `warm_up_ollama` usam as mesmas opções (evita reload do modelo por opções divergentes) | `core/llm.py` |
| 3 | **Fallback:** se o Ollama recusar `num_gpu` (VRAM insuficiente), a opção é desativada para o processo todo e a chamada repete 1x sem ela. No stream, só repete se nada foi emitido ainda | `core/llm.py` |
| 4 | Testes: opções padrão/configuradas, `num_gpu=0`, fallback normal e stream, sem retry após saída parcial | `tests/test_llm_options.py` |

**Não incluído (a discutir):** as 7 skills que chamam `/api/generate` direto via `requests` (sem `keep_alive`/`options`) ainda não usam essas opções. Enquanto isso, se `OLLAMA_NUM_CTX`/`OLLAMA_NUM_GPU` forem ativados, uma chamada de skill pode causar reload do modelo por divergência de opções.

**Servidor (variáveis do Windows, reiniciar o Ollama):** `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_FLASH_ATTENTION=1`.
