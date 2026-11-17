# 🔒 Skill: system_security.py

A skill `system_security.py` pertence à categoria **System**. É a linha final de defesa do J.A.R.V.I.S, responsável por gerenciar a camada física de energia (Power Management) e proteção perimetral do núcleo hospedeiro (Windows).

## 📝 Contrato

- **INTENT**: `SYSTEM_SECURITY`
- **PROMPT_TEXT**: Injetada no Cérebro mestre para interceptar qualquer tentativa verbal de desligamento, suspensão ou bloqueio do computador.

---

## ⚙️ Arquitetura e Engenharia Interna

### 1. O Sub-Agente de Defesa (`_ask_ollama_security`)

O motor extrai as intenções táticas através do prompt `SECURITY_DECISION_PROMPT`.

- Chamada por `core.llm.query_ollama(..., format="json")`. O retorno JSON é espartano: `{"action": "suspend" | "power_down" | "sentry_mode"}`.
- **Não existe mais o campo `confirmed`**: antes ele deixava o LLM pular a confirmação de desligar (Security Advisory GHSA-ph22). O LLM só classifica; quem confirma é sempre o usuário.

### 2. Fallback sem LLM

Se o Ollama não responder (`query_ollama` devolve `None`), a skill cai em palavras-chave: "sentinela/proteger/vou sair" → Modo Sentinela; "desligar/desliga" → `power_down_protocol` (que **pede confirmação**, como sempre); "dormir/suspender" → suspensão. Qualquer outra frase responde "Não compreendi" — não bloqueia mais a tela por padrão.

### 3. Protocolo: Modo Sentinela (`sentry_mode`)

O ato de travar a estação ("Sair", "Bloquear Tela") é complexo por conta de restrições das APIs de aúdio do kernel NT do Windows:

- **Silenciamento Forçado (`_stop_media`)**: Se você bloquear a tela com um vídeo no YouTube tocando, o Windows continua tocando o som no *Lock Screen*. O Jarvis resolve isso injetando silenciosamente o evento nativo `0xB3` (`VK_MEDIA_PLAY_PAUSE`), pausando tudo na máquina instantaneamente.
- **Micro-threading de Voz (`_delayed_lock`)**: O comando bruto `LockWorkStation()` da *C-Types* assassina imediatamente os canais da placa de áudio do usuário. Se o Jarvis fizesse isso sincronicamente, a fala *"Protocolo Sentinela Ativado"* seria cortada no meio. A skill mitiga isso injetando uma nova `threading.Thread(daemon=True)`. Essa *thread* dorme por precisos `3.5s` (o tempo exato da recitação de áudio do Jarvis terminar) e só então empurra a *LockWorkStation*, criando um bloqueio elegantemente coreografado.

### 4. Protocolo de Desenergização (`power_down_protocol`)

1. **Confirmação sempre**: `power_down_protocol()` arma `core.pending.arm("POWER_DOWN", "Desligar o computador em 15 segundos?", _shutdown)` e devolve a pergunta. Na TUI abre o `ConfirmScreen` (`s`/`n`, 30 s = não); na voz, só uma frase de confirmação ("sim", "pode desligar") aprova. Se já houver outra pergunta aberta, responde `pending.BUSY_REPLY` e não arma nada.
2. **Sem limpeza no desligamento**: Lixeira e `%TEMP%` não são mais apagados aqui (efeito destrutivo e surpreendente). Isso fica com a skill `SYSTEM_CLEANUP`, quando pedido.
3. **Shutdown com aviso**: após o "sim", `_shutdown()` roda `subprocess.run(["shutdown", "/s", "/t", "15", "/c", "J.A.R.V.I.S: Núcleo desenergizado."])` — em lista, sem shell. Os 15 s dão tempo de o TTS terminar a despedida.

### 5. Suspensão (`suspend_system`)

Suspender a máquina para um estado S3 de energia é feito através da DLL profunda do Windows: `rundll32.exe powrprof.dll,SetSuspendState 0,1,0`. Isso evita os travamentos de permissões do comando de linha `shutdown /h` em algumas máquinas limitadas.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **A Risco do Modo Sleep (`SetSuspendState`)**: Dependendo das configurações da placa mãe (BIOS) do usuário em relação a ErP/EuP Ready ou Wake-On-LAN, o comando `powrprof.dll` pode forçar uma Hibernação violenta em vez do modo Dormir (S3). Certifique-se de que a hibernação nativa do Windows no seu PC físico está desativada via CMD Admin (`powercfg -h off`) para que o comando suspenda a máquina rapidamente.
- **Testes**: `tests/test_system_security.py` substitui `subprocess.run` e `ctypes` por mocks. Nunca chame `_shutdown()` nem o `on_confirm` de uma pendência `POWER_DOWN` sem esses mocks: desligaria a máquina de desenvolvimento.
