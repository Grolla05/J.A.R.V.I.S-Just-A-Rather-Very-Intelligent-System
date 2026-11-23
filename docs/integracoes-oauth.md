# Integrações de conta — Google Agenda, Gmail, Spotify, Telegram e Discord

> ⚠️ **Estas integrações exigem chaves PESSOAIS.** O JARVIS não vem com chaves de
> nenhum serviço: cada usuário cria o próprio app no Google Cloud e no Spotify
> Developer (grátis, ~10 min, uma vez só) e preenche as variáveis no `.env`.
> Sem elas, os cards de `/config → INTEGRAÇÕES` ficam em **CONFIGURAR**.

Depois de configurado: em `/config → INTEGRAÇÕES`, Enter no card abre o navegador
na tela de login do serviço, você escolhe a conta e autoriza. O acesso fica salvo
no Cofre de Credenciais do Windows (serviço `JARVIS`): conecta uma vez e segue
conectado entre reinícios. Só pede login de novo se você revogar o acesso no
serviço ou der **Del** no card (trocar de conta).

Onde fica o `.env`:
- Repositório clonado (dev): na raiz do projeto.
- Instalado pelo `JARVIS-Setup.exe`: `%APPDATA%\JARVIS\.env`.

---

## 1. Google Agenda

### 1.1 Projeto e API
1. Acesse [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate) e entre com a sua conta Google.
2. **Nome do projeto:** `JARVIS` → **Criar**. Confira no topo da página que o projeto `JARVIS` está selecionado.
3. Abra [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) → **Ativar**.

### 1.2 Tela de consentimento (Google Auth Platform)
1. Abra [console.cloud.google.com/auth/overview](https://console.cloud.google.com/auth/overview) → **Começar**.
2. **Informações do app:** nome `J.A.R.V.I.S`, e-mail de suporte = o seu → Próximo.
3. **Público:** **Externo** → Próximo.
4. **Dados de contato:** o seu e-mail → Próximo → aceite a política → **Criar**.
5. Menu **Acesso a dados** → **Adicionar ou remover escopos** → filtre `calendar.readonly` →
   marque `https://www.googleapis.com/auth/calendar.readonly` → **Atualizar** → **Salvar**.
6. Menu **Público** → **Publicar app** → Confirmar (status **Em produção**).
   - ⚠️ Não deixe em **Teste**: nesse modo o Google invalida o login a cada **7 dias**.
   - Em produção sem verificação, o login mostra "O Google não verificou este app" →
     **Avançado** → **Acessar J.A.R.V.I.S (não seguro)**. É esperado: o app é seu.

### 1.3 Client "App para computador"
1. Menu **Clientes** ([link](https://console.cloud.google.com/auth/clients)) → **Criar cliente**.
2. **Tipo de aplicativo:** **App para computador** · Nome: `JARVIS Desktop` → **Criar**.
3. Copie o **ID do cliente** e a **Chave secreta do cliente** (botão de baixar JSON também serve).
   Não há redirect para cadastrar: apps Desktop aceitam `http://127.0.0.1:<qualquer porta>`.
4. No `.env`:
   ```bash
   GOOGLE_CLIENT_ID=123456789-xxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
   ```

### 1.4 Gmail (mesmo projeto e mesmo client)
O Gmail usa o **mesmo** `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, mas tem card e login próprios
(conectar o Gmail não mexe na Agenda).
1. Abra [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) → **Ativar**.
2. **Acesso a dados** → **Adicionar ou remover escopos** → marque
   `https://www.googleapis.com/auth/gmail.modify` → **Atualizar** → **Salvar**.
   - `gmail.modify` permite ler, criar rascunho, enviar, mover/etiquetar e mandar para a Lixeira. **Não**
     permite apagar de vez — e o JARVIS não tem código de exclusão permanente.
   - ⚠️ **Não** marque `https://mail.google.com/` (acesso total, inclui excluir para sempre).
   - É um escopo "restrito": o login mostra o aviso de app não verificado (esperado, o app é seu).
3. `/config` → **INTEGRAÇÕES** → **Gmail** → Enter.

O que o JARVIS faz com ele: `/email` (prioridades), ler e resumir, responder, escrever com anexo do
computador, mover para a **Lixeira** ("apaga o e-mail 3", recuperável por 30 dias) e organizar a caixa.
**Enviar, apagar e organizar sempre mostram o rascunho/lista/plano e esperam o seu "sim".**

---

## 2. Spotify

1. Acesse [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), entre e aceite os termos de desenvolvedor.
2. **Create app**:
   - **App name:** `JARVIS` · **App description:** `Assistente pessoal`
   - **Redirect URIs:** `http://127.0.0.1:8888/callback` → **Add** (exatamente assim; `localhost` é recusado)
   - **Which API/SDKs are you planning to use?** marque **Web API**
   - Aceite os termos → **Save**.
3. Na página do app → **Settings** → copie o **Client ID** (não precisa do Client secret: o JARVIS usa PKCE).
4. **User Management** → adicione o nome e o e-mail da sua conta Spotify (apps em modo
   de desenvolvimento só aceitam contas cadastradas aqui).
5. No `.env`:
   ```bash
   SPOTIFY_CLIENT_ID=0123456789abcdef0123456789abcdef
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```
   Controle de reprodução (play, pausa, próxima) exige conta **Premium**.

---

## 3. Ponte Telegram / Discord (conversar pelo celular)

A plataforma é só o fio: o bot "JARVIS" não pensa nada. A ponte (`backend/messenger.py`) roda **no seu
computador**, busca as mensagens por conexão de saída (sem abrir porta no roteador, sem servidor) e
responde com o cérebro local, em **modo Chat** (nada de automação do PC pelo celular). Computador
desligado = sem resposta (o Telegram guarda as mensagens até a ponte voltar).

**Segurança:** só os IDs em `*_ALLOWED_IDS` conversam; lista vazia = ninguém. Ações que mexem em algo
(enviar e-mail, organizar a caixa) pedem um "sim" seu no próprio chat — e só o seu "sim" vale.

### 3.1 Telegram
1. No Telegram, fale com **@BotFather** → `/newbot` → escolha nome e usuário → copie o **token**.
2. No `.env`: `TELEGRAM_BOT_TOKEN=<token>`. Reinicie o JARVIS.
3. Ainda sem o seu ID? Ligue a ponte (passo 5), mande `/id` ao seu bot: ele responde o número.
4. No `.env`: `TELEGRAM_ALLOWED_IDS=<seu id>` (vários separados por vírgula). Reinicie.
5. `/config` → **INTEGRAÇÕES** → **Telegram** → Enter (**Ligar ponte**). Del desliga.

### 3.2 Discord
1. [Developer Portal](https://discord.com/developers/applications) → **New Application** → **Bot** →
   **Reset Token** → copie. Na mesma página ligue **Message Content Intent**.
2. **OAuth2 → URL Generator**: escopo `bot`, permissões `Send Messages` e `Read Message History` →
   abra a URL e adicione o bot a um servidor seu (necessário para mandar DM a ele).
3. No `.env`: `DISCORD_BOT_TOKEN=<token>` e `DISCORD_ALLOWED_IDS=<seu id>` (Discord → Configurações →
   Avançado → Modo desenvolvedor → clique no seu nome → **Copiar ID do usuário**).
4. `/config` → **INTEGRAÇÕES** → **Discord** → Enter. O bot responde DM e menção (`@JARVIS ...`).

---

## 4. Conectar

1. Salve o `.env` e **reinicie o JARVIS** (as variáveis são lidas no boot).
2. `/config` → **INTEGRAÇÕES** → selecione o card → **Enter**.
3. O navegador abre: escolha a conta, autorize, feche a aba. O card fica **CONECTADO** com a conta.

## Problemas comuns

| Sintoma | Causa / solução |
|---|---|
| Card continua em CONFIGURAR | Variável vazia ou JARVIS não reiniciado. Confira o `.env` certo (dev × instalado). |
| Google: `Error 400: redirect_uri_mismatch` | Client criado como "Aplicativo da Web". Crie de novo como **App para computador**. |
| Google: `access_denied` / "app em teste" | Sua conta não está em Usuários de teste — publique o app (1.2, passo 6). |
| Google pede login toda semana | App ficou em **Teste**. Publique em produção. |
| Spotify: `INVALID_CLIENT: Invalid redirect URI` | Redirect cadastrado diferente de `http://127.0.0.1:8888/callback`. |
| Spotify: "User not registered in the Developer Dashboard" | Adicione sua conta em **User Management** (passo 2.4). |
| Gmail: "precisa de permissão nova" | Escopo `gmail.modify` não marcado (1.4) ou login antigo. Del e Enter no card do Gmail. |
| Bot do Telegram não responde | Card **Telegram** desligado, `TELEGRAM_ALLOWED_IDS` sem o seu ID (mande `/id`) ou computador dormindo. |
| Discord: bot online mas mudo | **Message Content Intent** desligado no Developer Portal. |
| Porta 8888 ocupada | Feche o programa que usa a porta, ou mude `SPOTIFY_REDIRECT_URI` (e no app do Spotify) para outra porta. |

Nunca versione o `.env` nem compartilhe as chaves: elas são suas.
