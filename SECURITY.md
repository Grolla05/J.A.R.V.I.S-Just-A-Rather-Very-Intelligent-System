# Política de Segurança

## Versões suportadas

| Branch | Suportada          |
| ------ | ------------------ |
| `main` | ✅ Sim              |
| `DEV`  | ⚠️ Ativa, pode ser instável |

## Reportando uma vulnerabilidade

**Não abra uma issue pública para vulnerabilidades de segurança.**

Use a aba **Security → Report a vulnerability** deste repositório
(Private Vulnerability Reporting do GitHub) para reportar de forma
privada. Se preferir, entre em contato diretamente pelo perfil
[@Grolla05](https://github.com/Grolla05).

Este é um projeto mantido por uma única pessoa — não há um SLA formal de
resposta, mas vulnerabilidades críticas (execução remota de código,
exposição de credenciais, escalonamento de privilégios) têm prioridade
máxima assim que identificadas.

Ao reportar, inclua:
- Descrição do problema e impacto potencial
- Passos para reproduzir (ou prova de conceito)
- Versão/commit afetado

## Riscos conhecidos e por design

O J.A.R.V.I.S. **não é um chatbot comum** — ele é um assistente com
acesso real ao sistema operacional. Isso é intencional, não uma falha a
ser corrigida, mas precisa ser dito com todas as letras para quem for
instalar ou contribuir:

- Controle de teclado e mouse (`Skill — Keyboard Control`)
- Captura e controle de tela (`Skill — Screen Control`)
- Abertura e encerramento de processos/aplicativos (`Skill — App Control`)
- Shutdown, suspend e "sentry mode" da máquina (`Skill — System Security`)
- Sistema de skills plugável (`skill_loader.py`) que **importa e executa
  qualquer arquivo `.py` dentro de `backend/skills/` via `importlib`, sem
  sandbox**

Quem instala o J.A.R.V.I.S. está dando a um assistente autônomo o mesmo
nível de acesso que o próprio usuário tem no computador. Recomendações:

- **Não instale skills de terceiros sem ler o código antes**
- Rode em uma conta de usuário sem privilégios administrativos quando
  possível
- Trate qualquer coisa em `backend/skills/` com a mesma cautela que você
  trataria a instalação de um programa desconhecido
- Toda skill nova passa por revisão manual antes do merge (ver
  [CONTRIBUTING.md](CONTRIBUTING.md))

## Segredos e credenciais

- Nunca commite o arquivo `.env` — use [`.env.example`](.env.example)
  como referência de quais variáveis existem
- O fluxo OAuth PKCE do Spotify salva o **refresh token** em
  `backend/database/spotify_token.json`. Confirme, antes de dar push, que
  esse caminho está coberto pelo seu `.gitignore` local — hoje o
  `.gitignore` do repositório ainda **não** ignora esse arquivo
  explicitamente (só `*.db`), então recomendamos adicionar a linha
  `backend/database/spotify_token.json` (ou `*.json` dentro de
  `backend/database/`) antes de rodar o projeto com uma conta real
- Chaves de API (Obsidian Local REST API, Spotify Client ID) devem ser
  tratadas como segredo mesmo em ambiente de desenvolvimento local

## Escopo

Esta política cobre o código deste repositório. Não cobre a segurança de
serviços de terceiros que você conecta ao J.A.R.V.I.S. (sua própria
instância do Ollama, o plugin Local REST API do Obsidian, sua conta do
Spotify) — a segurança desses serviços é responsabilidade de quem os
configura.
