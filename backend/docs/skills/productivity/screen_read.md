# 👁️ Skill: screen_read.py

Lê o texto que está na tela e responde sobre ele: explica um erro ou um trecho de código, resume um documento, traduz uma página ou resolve uma questão de prova aberta. Categoria **productivity**: roda no Chat e no Copilot (voz).

Não usa modelo de visão. A tela vira texto pelo **OCR nativo do Windows** (0 VRAM) e quem responde é o modelo de texto (`OLLAMA_MODEL`). Em placa de 4 GB, isso evita tirar o modelo do chat da VRAM a cada pedido. Interpretar imagem (foto, gráfico, layout) fica para depois, junto com o plano da Thinking Layer.

## 📝 Contrato

- **INTENT**: `SCREEN_READ`
- **PROMPT_TEXT**: `prompts/skills/screen_read.md` ("explica o erro na minha tela", "resolve a questão aberta no monitor 2"). Tem "NÃO use para…" contra `SCREEN_CONTROL` (brilho, mover janela), `CLIPBOARD` (o que foi copiado) e texto já colado na mensagem (`CHAT`).
- **KEYWORDS**: `tela`, `janela*`, `monitor*`, `print`, `aberto`/`aberta`, `questao`, `exercicio*`.
- **Entity**: `"monitor N"`, `"tela inteira"` ou `null`.
- **Retorno**: um **gerador** (`query_ollama_stream`), para a resposta chegar em stream. Mensagens fixas (sem captura, sem texto) saem como `str`.

## ⚙️ Fluxo

```
execute(entity, command)
  ├─ scope_for()            "monitor 2" → ("monitor", 2) · "tela inteira" → ("monitor", None) · resto → ("window", None)
  ├─ screen_capture.capture()
  │     janela em foco; se for o terminal do JARVIS (Chat), desce na ordem Z até a 1ª janela real
  │     (visível, não minimizada, não "cloaked", com título, fora do shell, não é janela de ferramenta)
  │     imagem só em memória — nunca vai para disco nem SQLite
  ├─ ocr.recognize()        Windows.Media.Ocr · OCR_LANGUAGE → pt-BR → en-US → perfil · ×2 se altura < 900 px
  ├─ ocr.mask_secrets()     linha com token de cara de chave (sk-, ghp_…, ou 20+ caracteres aleatórios) → [oculto]
  ├─ < 20 caracteres?       → NO_TEXT_REPLY (sugere /attach)
  ├─ clip_text()            corta em SCREEN_TEXT_MAX (6000) no fim de linha + "[texto cortado]"
  ├─ clipboard.classify()   error → explain_error.md · code → explain_code.md · resto → screen_read.md
  └─ query_ollama_stream(temperature=0.3)
```

O `brain` repassa os pedaços na TUI (`execute_command_stream`) e junta tudo no modo voz standalone (`execute_command`).

## 🔧 Configuração (`.env`)

| Variável | Padrão | O que faz |
|---|---|---|
| `OCR_LANGUAGE` | vazio | Idioma do OCR (`pt-BR`, `en-US`…). Vazio = pt-BR → en-US → idiomas do Windows |
| `SCREEN_TEXT_MAX` | `6000` | Máximo de caracteres lidos enviados ao modelo (cabe no `OLLAMA_NUM_CTX` 4096) |

Idioma de OCR ausente: Configurações do Windows → Hora e idioma → Idioma → Português (Brasil) → Opções → **Reconhecimento óptico de caracteres**.

## 🔒 Privacidade

- A captura nunca é gravada; o texto vai só ao Ollama local.
- Tokens com cara de chave são mascarados antes do modelo e do histórico. A regra é mais rígida que a do clipboard (`clip_history.looks_secret`), para não esconder `NameError:` ou `main.py:3`.
- A pergunta e a resposta ficam na sessão do chat, como qualquer turno.

## 🧪 Testes

- `tests/test_screen_read.py`: prompt por tipo (erro, código, texto), pouco texto, falha de captura, segredos, corte, escopo.
- `tests/test_screen_capture.py`: escolha da janela (`pick_target`) e do monitor, captura com `grab` falso.
- `tests/test_ocr.py`: tamanho, ordem de idiomas, `mask_secrets`, ausência do `winrt`.
- `tests/test_mode_routing.py` (`TestStreamingSkill`): skill em stream no `brain`.
