# J.A.R.V.I.S.

**J.A.R.V.I.S.** é um projeto focado no desenvolvimento de um assistente virtual 100% autônomo, inspirado na inteligência artificial de mesmo nome do universo Homem de Ferro. Seu propósito é prover um sistema integrado capaz de interagir de forma inteligente e contínua.

---

## 📚 Documentação

Este repositório principal atua apenas como o ponto de entrada e integrador do projeto. **A documentação detalhada, bem como instruções técnicas, dependências e guias específicos de cada módulo, encontram-se dentro de seus respectivos repositórios e subdiretórios.**

Por favor, navegue até a pasta do componente específico (ex: `backend`, `backend/tui`, serviços, etc.) para consultar sua documentação dedicada.

---

## 💾 Instalar (Windows 10/11)

Baixe o **`JARVIS-Setup.exe`** do [Release mais recente](https://github.com/Grolla05/J.A.R.V.I.S-Just-A-Rather-Very-Intelligent-System/releases/latest) e execute. O instalador já traz o Python e todas as bibliotecas — não precisa instalar mais nada.

- Se o **Ollama** não estiver instalado, o setup mostra o link oficial ([ollama.com/download](https://ollama.com/download)) e espera: assim que o Ollama terminar de instalar, ele segue sozinho para a escolha do **modelo de IA** (dropdown), baixado no fim da instalação.
- Abra pelo atalho **J.A.R.V.I.S** (ou `jarvis` no terminal, se marcou a opção do PATH). Usa o Windows Terminal quando existir.
- Configurações e dados ficam em `%APPDATA%\JARVIS` (`.env`, banco, logs) e sobrevivem a atualizações.

Cada merge na `main` publica um Release novo automaticamente (`.github/workflows/release.yml`).

### Gerar o instalador localmente

```powershell
powershell -File installer\build_runtime.ps1          # dist\runtime (Python + libs) e dist\app (código)
iscc /DVersao=0.0.0-dev installer\jarvis.iss          # dist\JARVIS-Setup.exe (Inno Setup 6)
powershell -File installer\test_setup.ps1             # instala, testa e desinstala em silêncio
```

---

## 🚀 Inicialização Rápida (a partir do código)

Para iniciar todos os serviços integrados do ecossistema a partir da raiz, basta executar o script de inicialização:

```cmd
boot.bat
```

A interface é uma TUI no terminal: `Shift+Tab` alterna entre **Chat** e **Copilot**, `/help` lista os comandos.

*(Nota: Certifique-se de que todos os pré-requisitos listados nas documentações dos sub-módulos foram atendidos antes da execução).*
