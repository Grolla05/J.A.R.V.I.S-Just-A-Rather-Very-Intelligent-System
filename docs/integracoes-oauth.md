# Integrações de conta — Google Agenda e Spotify

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

## 3. Conectar

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
| Porta 8888 ocupada | Feche o programa que usa a porta, ou mude `SPOTIFY_REDIRECT_URI` (e no app do Spotify) para outra porta. |

Nunca versione o `.env` nem compartilhe as chaves: elas são suas.
