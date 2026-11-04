# 📂 Backend J.A.R.V.I.S. (Just A Rather Very Intelligent System)

Este diretório contém o motor lógico, a cognição e a infraestrutura do assistente virtual. O projeto foi construído seguindo princípios de **Modularidade Dinâmica**, permitindo que a inteligência artificial, os sentidos (áudio/visão) e a memória de longo prazo operem de forma independente e altamente extensível.

## 🎯 Objetivo do Projeto

O objetivo do J.A.R.V.I.S. é ser um assistente pessoal de **IA Local** de baixíssima latência. Ele prioriza a privacidade e a autonomia rodando o modelo `llama3.1` via Ollama diretamente no hardware do usuário. Ele oferece controle profundo do sistema operacional Windows, persistência de memória em Markdown (Cofre Obsidian) via protocolo MCP, e uma interface de terminal (TUI em Textual) com modos Chat e Copilot alternados por `Shift+Tab`.

---

## 📚 Documentação Granular por Feature

Para garantir a fácil manutenção e escalabilidade do backend, cada módulo principal possui sua própria documentação detalhada na pasta `docs/`. Recomendamos fortemente a leitura dos arquivos abaixo antes de alterar a arquitetura:

### 🧩 Orquestração e Core

- [O Orquestrador Principal (`main.py`)](docs/main_orchestrator.md)
- [Configurações Globais (`config.py`)](docs/core/config.md)
- [Motor de Telemetria (`SystemInfo.py`)](docs/core/SystemInfo.md)
- [Integração Obsidian e MCP (`obsidian.py`)](docs/core/obsidian.md)
- [Motor de Persistência SQLite (`database.py`)](docs/core/database.md)
- [Sistema de Observabilidade (`logger.py`)](docs/core/logger.md)
- [Carregador Dinâmico de Skills (`skill_loader.py`)](docs/core/skill_loader.md)
- `llm.py` — wrapper de chamadas ao Ollama (streaming e síncrono)
- `hardware.py` — varredura via PowerShell e persistência de specs no SQLite
- `state.py` — container de estado global em runtime (`sys_monitor`, `pending_critical_action`)
- `prompts.py` — carregamento e substituição de variáveis em templates `.md`
- `alerts.py` — processamento de alertas de sistema com cache de julgamento de processos

### 🧠 Serviços (Sentidos e Cognição)

- [O Cérebro Cognitivo (`brain.py`)](docs/services/brain.md)
- [Ouvidos e Transcrição (`listen.py`)](docs/services/listen.md)
- [Voz e Sincronia (`speak.py`)](docs/services/speak.md)
- `intent.py` — classificação de intenção via LLM (JSON mode) e verificação de skill habilitada
- `chat.py` — montagem de prompt com histórico, contexto de vault e injeção de telemetria live
- `memory.py` — extração de fatos de falas do usuário e gravação no Obsidian vault

### 🚀 Skills Dinâmicas

O J.A.R.V.I.S. suporta *Skills* Plug-and-Play. Adicionar um novo arquivo `.py` com o contrato correto em `skills/` fará o J.A.R.V.I.S aprender a habilidade no próximo boot.

- **Automação:**
  - [Controle de Aplicativos (`app_control.py`)](docs/skills/automation/app_control.md)
  - [Controle de Áudio (`audio_control.py`)](docs/skills/automation/audio_control.md)
  - [Controle de Teclado Fantasma (`keyboard_control.py`)](docs/skills/automation/keyboard_control.md)
  - [Controle de Tela e Retina (`screen_control.py`)](docs/skills/automation/screen_control.md)
  - [Macros de Ambiente (`work_macros.py`)](docs/skills/automation/work_macros.md)
- **Sistema:**
  - [Relatório de Status (`status_report.py`)](docs/skills/system/status_report.md)
  - [Limpeza de Sistema (`system_clear.py`)](docs/skills/system/system_clear.md)
  - [Segurança Física (`system_security.py`)](docs/skills/system/system_security.md)

---

## 🏗️ Resumo da Arquitetura

O backend é dividido em três blocos operacionais:

1. **`core/` (A Fundição)**: Singletons e infraestrutura de baixo nível — SQLite, Ollama LLM, Monitoramento de CPU/GPU, Logging, MCP Client, sistema de alertas e carregamento de prompts.
2. **`services/` (Os Sentidos e a Mente)**: Pipeline de processamento de comandos. `listen.py` capta áudio → `brain.py` coordena → `intent.py` classifica a intenção via LLM (JSON mode) → roteia para skill, `chat.py` (resposta LLM), ou `memory.py` (gravação no vault) → `speak.py` sintetiza em áudio com efeito "Typewriter" no terminal.
3. **`skills/` (Os Membros)**: Comandos plug-and-play. Cada arquivo com contrato `INTENT + execute()` é carregado automaticamente no boot e mapeado para o roteador de intenção.

---

## 🚀 Como Executar Localmente (Standalone)

1. Certifique-se de ter o **Ollama** instalado e o modelo `llama3.1` (ou o definido no `.env`) baixado.
2. Certifique-se de que o **uvx** (Astral UV) está instalado globalmente para o servidor MCP funcionar (`pip install uv`).
3. Instale as dependências Python:

```bash
pip install -r requirements.txt
```

4. Configure o arquivo `.env` na raiz (Caminhos de Banco de Dados, Obsidian Vault, etc).
5. Inicie o sistema:

```bash
python main.py
```
