# Decisões arquiteturais importantes

Por que o projeto é como é. Antes de propor uma troca de tecnologia, leia a razão original. Visão ponta a ponta em [`arquitetura.md`](arquitetura.md); resumo do projeto em [`AGENTS.md`](../AGENTS.md).

| Decisão | Razão |
|---------|-------|
| TUI Textual em vez de React + PyWebView | WebView2 + Three.js custavam centenas de MB de RAM e GPU; a TUI roda no terminal com poucas dezenas de MB |
| Chamadas Python diretas em vez de bridge IPC | Sem `evaluate_js`, sem escape de string, sem mock fallback — o cérebro é um generator consumido pela TUI |
| Voz opcional e lazy | Mic, pyttsx3 e pygame só carregam quando a voz é ligada |
| SQLite local em vez de nuvem | Privacidade total, zero latência, funciona offline |
| Ollama local em vez de API Claude/GPT | Sem custo por token, privacidade, funciona sem internet |
| Prompts em `.md` em vez de strings Python | Editáveis sem tocar no código, versionáveis de forma legível |
| `ollama` lib em vez de `requests.post` | Gerenciamento de sessão mais robusto, streaming tipado |
| state.py separado | Evita importações circulares entre brain, alerts e chat |
| `skill.execute(entity, command)` com 2 args | Sub-agentes precisam da frase original para contexto |
