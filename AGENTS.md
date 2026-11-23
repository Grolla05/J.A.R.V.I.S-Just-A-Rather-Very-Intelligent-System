# J.A.R.V.I.S — Instruções para o Codex Project

## O que é este projeto

O **J.A.R.V.I.S.** é um assistente virtual 100% autônomo inspirado no JARVIS do Iron Man. É um **app de terminal (TUI) para Windows**, 100% Python: a interface é feita em [Textual](https://textual.textualize.io) e roda no próprio terminal, sem browser, sem WebView e sem Node.js. A TUI consome o backend (o cérebro cognitivo) por chamadas Python diretas — não existe IPC, REST nem HTTP.

- **Cérebro:** LLM local via Ollama, memória em SQLite e no vault do Obsidian
- **Dois modos:** `chat` (texto, só skills de consulta) e `copilot` (voz, todas as skills)
- **Repositório:** `github.com/Jarvis-Project-2026/J.A.R.V.I.S`
- **Dev:** Felipe Grolla Freitas

## Mapa da documentação (`docs/`)

O que não é essencial para rodar, testar e desenvolver mora em `docs/`. **Antes de alterar código, leia o arquivo do assunto.**

| Assunto | Arquivo |
|---------|---------|
| Visão ponta a ponta, módulo a módulo | [`docs/arquitetura.md`](docs/arquitetura.md) |
| Árvore de pastas e arquivos, modo instalado (`JARVIS_DATA_DIR`) | [`docs/estrutura.md`](docs/estrutura.md) |
| Regras do backend: logging, Ollama, prompts, threads, voz, estado global, configurações | [`docs/regras-backend.md`](docs/regras-backend.md) |
| SQLite e Obsidian (RAG, memória de longo prazo) | [`docs/banco-de-dados.md`](docs/banco-de-dados.md) |
| Contrato das skills e como criar uma nova | [`docs/skills.md`](docs/skills.md) |
| TUI: modos, atalhos, comandos `/`, telas, visual, badge de skill | [`docs/tui.md`](docs/tui.md) |
| Alertas de sistema, vigia de rede, Não Perturbe | [`docs/alertas.md`](docs/alertas.md) |
| Agente residente e atualização automática | [`docs/agente-residente.md`](docs/agente-residente.md) |
| Fluxo de um comando de voz e de uma mensagem no Chat | [`docs/fluxos.md`](docs/fluxos.md) |
| Variáveis do `.env` | [`docs/variaveis-ambiente.md`](docs/variaveis-ambiente.md) |
| Chaves OAuth pessoais (Google, Gmail, Spotify) | [`docs/integracoes-oauth.md`](docs/integracoes-oauth.md) |
| Tom e personalidade do JARVIS | [`docs/personalidade.md`](docs/personalidade.md) |
| Termos de uso | [`docs/termos-de-uso.md`](docs/termos-de-uso.md) |
| Política de privacidade (o que fica no PC e o que sai dele) | [`docs/politica-de-privacidade.md`](docs/politica-de-privacidade.md) |
| Por que o projeto é assim (decisões) | [`docs/decisoes-arquiteturais.md`](docs/decisoes-arquiteturais.md) |

## Instalação de dependências

O Ollama deve estar instalado e rodando separadamente ([ollama.ai](https://ollama.ai)), com o modelo baixado (ex.: `ollama pull llama3`).

```powershell
cd backend

# Criar e ativar ambiente virtual (recomendado)
python -m venv venv
venv\Scripts\activate

# Dependências do app + ferramentas de desenvolvimento (pytest, pytest-xdist, ruff)
pip install -r requirements.txt -r requirements-dev.txt
```

- O `.env` fica na **raiz** do repositório (modelo comentado: [`env.example`](env.example)). Variáveis em [`docs/variaveis-ambiente.md`](docs/variaveis-ambiente.md)
- Para o RAG, instale o plugin **"Local REST API"** no Obsidian e configure no `.env`: `OBSIDIAN_HOST=http://127.0.0.1:27123` e `OBSIDIAN_API_KEY=<chave gerada pelo plugin>`

## Como rodar o projeto

```powershell
cd backend
python main.py                # TUI (prefira o Windows Terminal: o conhost antigo renderiza mal cores e Unicode)
python main.py --copilot      # abre já no modo voz
python -m services.brain      # modo voz standalone, sem interface (liga a voz)
```

## Como rodar os testes

```powershell
cd backend
python -m pytest tests -q -n auto                 # suíte inteira, em paralelo
python -m pytest tests/test_<feature>.py -q       # só os testes da feature
ruff check .                                      # lint; rode também em frontend/
```

Os testes ficam em `backend/tests/` e usam fakes (sem Ollama, microfone nem hardware). Os da TUI usam `App.run_test()` + Pilot, com `stream_fn` fake, `voice=FakeVoice(...)` e `start_services=False`; o `tearDown` zera `state.voice_enabled`. Com `NO_COLOR` definido o Textual desenha em cinza.

## Workflow obrigatório de desenvolvimento

1 -> A partir do prompt gere os testes para verificação da feature antes mesmo de começar a desenvolver, todos os testes unitários tem que ser criados dentro da pasta tests na raiz da frente do projeto ou seja dentro de backend ou frontend, caso a pasta não exista crie ela no respectivo lugar.
2 -> Com os testes escritos explore as opções e caminhos nos quais podem ser seguidos para o desenvolvimento
3 -> Escreva o plano de ação para implementar a feature
4 -> Desenvolva o plano proposto, dividindo a atividade do plano em task's
5 -> Após o desenvolvimento execute os testes escritos no passo 1, para validar oque foi gerado, não é necessário rodar a suite inteira de testes e sim somente os testes relacionado a feature implementada, se não passar em algum teste propostos para feature, identifique oque deu problema e conserte e rode o teste novamente
6 -> Após ter ocorrido tudo corretamente por favor crie, edite caso já exista, o arquivo CHANGES.md na raiz do projeto, no qual este por sua vez deve documentar tudo nos mínimos detalhes do que foi feito
7 -> Após ter ter documentado tudo no CHANGES.md busque no repositório toda a documentação do projeto e atulize-as com todas as alterções que foram realizadas, de maneira na qual a documentação reflita exatamente como o projeto está funcionando, caso seja possível atualize também a documentação relativa do projeto na vault do obsidian.
8 -> Após ter ter atualizado toda a documentação do projeto prepare para gerar o commit, baseado nas alterações documentadas no CHANGES.md, ou seja deve ser feito baseado neste arquivo o commit mensage, mas espere a validação e comando do usuário
9 -> Com a validação do usuário siga o processo de commit -> push (sync changes) -> Pull Request. Não é necessário abrir uma branch nova para cada feature, apenas utilize a branch Grolla para realizar este processo.
10 -> Após o commit feito por favor limpe o arquivo CHANGES.md, ou seja apague, o conteúdo dele.

### Boas práticas

Sempre que for responder ou realizar qualquer prompt é obrigatório que utilize a skill caveman no desenvolvimento da task
também na hora de fazer/abrir o PR e commit, ccoloque sempre a tag de Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>.

### Contexto: Obsidian primeiro

Claude sempre que for realizar qualquer atividade relacionada a este projeto deve ser consultado no obsidian primeiro com os arquivos existentes na vault, e também se basear no repositório apresentado como contexto
