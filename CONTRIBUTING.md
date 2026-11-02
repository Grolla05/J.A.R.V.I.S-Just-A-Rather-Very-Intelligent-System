# Contribuindo com o J.A.R.V.I.S.

Obrigado pelo interesse em contribuir! Este é um projeto pessoal de código
aberto, mantido por um único desenvolvedor ([@Grolla05](https://github.com/Grolla05)),
que tem a palavra final sobre o que entra em `main`. Isso não significa que
contribuições externas não sejam bem-vindas — muito pelo contrário — apenas
que o processo de revisão é o de um mantenedor solo, não o de uma equipe.

Ao contribuir, você concorda em seguir o [Código de Conduta](CODE_OF_CONDUCT.md)
deste projeto.

## Antes de começar

- **Branches:** `DEV` é a branch de integração ativa; `main` reflete o
  estado estável. Abra pull requests contra `DEV`, salvo indicação
  contrária do mantenedor.
- **Escopo:** dê uma olhada nas issues abertas antes de começar algo grande,
  para evitar trabalho duplicado ou esforço em uma direção que não será
  aceita.
- **PRs grandes:** para mudanças estruturais (nova arquitetura, nova
  dependência pesada, mudança de linguagem/framework), abra uma issue de
  discussão antes de escrever código.

## Configurando o ambiente local

### Backend (Python 3.11)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
copy ..\.env.example ..\.env  # Windows — preencha com seus próprios valores
```

### Frontend (Node 20)

```bash
cd frontend
npm i --legacy-peer-deps
npm run dev
```

### Subindo tudo de uma vez (Windows)

```cmd
boot.bat
```

> O projeto foi desenvolvido primariamente para Windows (`boot.bat`,
> `pyautogui`, controle de teclado/tela). Se você contribuir a partir de
> Linux/Mac, teste com atenção redobrada os módulos que tocam o sistema
> operacional — eles podem não ter um caminho equivalente ainda.

## Antes de abrir um Pull Request

Rode localmente os mesmos checks que o CI (`.github/workflows/main.yml`)
vai rodar:

```bash
# Backend
cd backend
ruff check .
python -m compileall .

# Frontend
cd frontend
npm run lint
npm run build
```

Confira também:

- [ ] Nenhum arquivo `.env`, token ou credencial foi commitado
- [ ] A documentação do módulo afetado (`README.md` da pasta) foi atualizada
- [ ] O PR está focado em uma única mudança lógica (PRs pequenos são
      revisados mais rápido)

## Convenção de commits

Este projeto usa [Conventional Commits](https://www.conventionalcommits.org/pt-br/):

- `feat:` nova funcionalidade
- `fix:` correção de bug
- `docs:` documentação
- `refactor:` mudança de código sem alterar comportamento
- `chore:` tarefas de manutenção, dependências, CI
- `skill:` adição ou alteração de uma skill em `backend/skills/`

## Contribuindo com uma nova Skill

O sistema de skills é o coração da extensibilidade do J.A.R.V.I.S., mas
também é o ponto de maior risco de segurança do projeto: `skill_loader.py`
varre `backend/skills/` recursivamente e **importa e executa qualquer
arquivo `.py` encontrado**, sem sandbox. Por isso, toda contribuição de
skill segue regras extras:

1. **Contrato obrigatório** — o módulo precisa expor:
   - `INTENT` (string única, não pode colidir com uma skill existente)
   - `execute(...)` (função de entrada chamada pelo roteador de intenção)
   - `PROMPT_TEXT` (opcional) — texto usado pelo classificador de intenção

2. **Declare acesso sensível explicitamente** — se a skill toca em
   qualquer um destes pontos, adicione um comentário no topo do arquivo:

   ```python
   # ⚠️ ACESSO SENSÍVEL: controla teclado do usuário via `pyautogui`
   ```

   Isso inclui: sistema de arquivos, teclado/mouse, tela (captura ou
   controle), abertura/encerramento de processos, shutdown/suspend/sentry
   mode, ou qualquer chamada de rede para um serviço externo.

3. **Abra uma issue antes de codificar** — use o template
   *"Proposta de Nova Skill"* para alinhar escopo e necessidade de acesso
   com o mantenedor antes de investir tempo na implementação.

4. **Revisão obrigatória** — PRs que tocam `backend/skills/` ou
   `backend/core/skill_loader.py` exigem aprovação explícita do
   mantenedor antes do merge. Não é burocracia: uma skill maliciosa tem
   o mesmo poder que o usuário tem sobre a própria máquina.

## Reportando bugs e sugerindo features

Use os templates de Issue disponíveis no repositório. **Para
vulnerabilidades de segurança, não abra uma issue pública** — siga o
processo descrito em [SECURITY.md](SECURITY.md).

## Processo de revisão

Como é um projeto mantido por uma única pessoa, não há SLA formal de
resposta. PRs pequenos, focados e com testes/checks passando tendem a ser
revisados mais rápido. Fique à vontade para comentar no PR pedindo um
retorno se ele ficar parado por muito tempo.
