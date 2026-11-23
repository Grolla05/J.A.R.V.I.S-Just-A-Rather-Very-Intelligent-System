# Política de Privacidade

**Última atualização:** 23/11/2026

Esta política explica **o que o J.A.R.V.I.S. guarda no seu computador, o que ele envia para fora e como você controla isso**. Ela faz parte dos [Termos de Uso](termos-de-uso.md).

## Em resumo

- O JARVIS roda **no seu PC**. O desenvolvedor **não recebe nenhum dado seu**: não há servidor, conta, telemetria, analytics nem anúncios. "Telemetria" no código é só a leitura local de CPU, RAM e disco.
- A **IA é local** (Ollama). O JARVIS não usa nenhuma API de IA na nuvem: suas conversas, e-mails, agenda, vault e arquivos não são enviados a um provedor de IA.
- Alguns recursos falam com **terceiros** (voz, clima, trânsito, busca, notícias, Google, Spotify, GitHub, Telegram/Discord, winget, atualizações). A [seção 4](#4-o-que-sai-do-seu-computador-terceiros) lista cada um.
- **Atenção à voz:** com a voz ligada, o áudio de **toda fala captada** vai ao Google para ser transcrito, inclusive antes da palavra "Jarvis". A voz começa **desligada**.
- Você controla: voz, monitor de clipboard, pontes e manchetes vêm **desligados**; o resto você liga e desliga em `/config`.

## 1. Quem é responsável pelos dados

Como o JARVIS é um software local, **você é quem decide e controla** os dados dele: você é o controlador, nos termos da Lei Geral de Proteção de Dados (LGPD, Lei 13.709/2018). O desenvolvedor, Felipe Grolla Freitas, **não tem acesso** ao que fica no seu computador e **não opera serviço** que receba seus dados. Os terceiros da seção 4 são controladores independentes dos dados que recebem de você.

## 2. O que fica no seu computador

A pasta de dados é `%APPDATA%\JARVIS` na versão instalada. No código-fonte (dev) fica em `backend/`, e o `.env` na raiz.

| Dado | Onde | Para quê | Observação |
|------|------|----------|------------|
| Conversas, sessões e histórico | SQLite `database/jarvis_memory.db` | Continuar conversas, *save slots*, regenerar | Texto das mensagens; sem prazo para apagar |
| Preferências | SQLite (tabela `config`) | `/config` | |
| Especificações do computador | SQLite (tabela `hardware`) | `/status`, alertas | Lidas localmente (CPU, GPU, RAM, disco) |
| Lembretes | SQLite (tabela `reminders`) | Avisos | |
| Contatos de e-mail (apelido → endereço) | SQLite (tabela `email_contacts`) | "Manda para o Guilherme" | Também consulta o histórico do Gmail ao procurar |
| Softwares mantidos no Vigia de rede | SQLite (tabela `net_trusted_apps`) | Não alertar de novo | Nome e caminho do executável |
| Histórico do clipboard | SQLite (tabela `clipboard_history`) | `/clip` | **Só com o Monitor de clipboard ligado** (desligado por padrão). Não guarda o que parece senha ou token |
| Linha de base da rede | SQLite (tabela `config`, chave `net_baseline`) | Detectar novidades | Portas, processos e aparelhos da rede local (IP e MAC) |
| Memórias e insights | Seu vault do Obsidian (`Memória/`, `🧠 Brainstorms/`) | Memória de longo prazo e RAG | O **Registro de insights** (ligado por padrão) grava ideias da conversa no vault |
| Localização aproximada | Cache e nota no Obsidian | Clima | Obtida pelo IP (seção 4) |
| Anexos (`/attach`) | `uploads/` | Descrever imagem (modelo local) e transcrever áudio (Whisper local) | Ficam salvos até você apagar |
| Logs | `logs/` | Diagnóstico | Podem conter comandos, nomes de programas e erros. **Não são enviados**; sem expurgo automático |
| Tokens das integrações (Google, Gmail, Spotify) | Cofre de Credenciais do Windows (serviço `JARVIS`) | Manter a conexão | Se o cofre falhar, cai num JSON em `database/integrations_secrets.json` |
| Chaves e tokens do `.env` | Arquivo `.env` | Configuração | **Texto puro** (ex.: `OBSIDIAN_API_KEY`, `GITHUB_TOKEN`, tokens dos bots) |
| Estado de atualização | `updates/` | Cache da versão e adiamento | |

**Só em memória (não gravados em disco):** a captura de tela usada na leitura de tela, o texto do OCR (com senhas e tokens mascarados antes de ir ao modelo) e a lista de e-mails vista. Os e-mails são lidos e resumidos pelo Ollama **local**.

## 3. O que é processado localmente

Modelo de linguagem (Ollama), classificação de intenção, OCR do Windows, transcrição de áudio anexado (Whisper), descrição de imagem anexada (modelo de visão), busca no vault e todo o banco de dados. Se você apontar `OLLAMA_HOST` para **outra máquina**, o texto das conversas vai para ela, e a responsabilidade passa a ser sua.

## 4. O que sai do seu computador (terceiros)

| Recurso | Destino | O que é enviado | Quando |
|---------|---------|-----------------|--------|
| **Voz (Copilot)** | Google (reconhecimento de fala) | O **áudio de cada trecho de fala** captado pelo microfone, inclusive antes da palavra de ativação, porque a detecção dela depende da transcrição | Só com a voz ligada (começa desligada). O Modo Apresentação fecha o microfone |
| **Fala do JARVIS** | Microsoft (serviço de voz neural do Edge) | O texto da resposta que será falada. Sem esse serviço, usa a voz offline do Windows | Voz ligada |
| **Clima** | `ip-api.com` e Open-Meteo | Seu **IP** (para achar a cidade; essa consulta é feita por **HTTP, sem criptografia**) e as coordenadas | Briefing e skill de clima; as coordenadas ficam em cache |
| **Trânsito** | Nominatim/OpenStreetMap, OSRM público ou TomTom (se você configurar a chave) | Os endereços e as coordenadas das rotas | `/rota`, skill de trânsito e avisos de saída |
| **Pesquisa na web** | Buscadores acessados pela biblioteca `ddgs` (DuckDuckGo, Bing, Brave, conforme o sorteio) e os sites lidos | Os termos da busca e as requisições às páginas (seu IP) | Skill de pesquisa. O resumo é feito pelo Ollama local |
| **Notícias** | Feeds RSS dos portais (ex.: G1, CNN Brasil, BBC, NYT, WSJ) e Crossref | Apenas a requisição de leitura (seu IP); nada seu | Só com "Manchetes no briefing" ligado (padrão desligado) |
| **Google Agenda e Gmail** | APIs do Google (OAuth) | Os pedidos de leitura da agenda; e-mails lidos, rascunhos, envios, marcadores e Lixeira, conforme o que você mandar | Só depois de você conectar o card em `/config` → INTEGRAÇÕES |
| **Spotify** | API do Spotify | Busca e controle do player | Depois de conectar |
| **GitHub** | API do GitHub (com o seu token) | Consultas de repositórios, PRs, issues e CI; criação de issue só com confirmação | Skill de GitHub e briefing |
| **Ponte Telegram / Discord** | Servidores do Telegram e do Discord | Suas mensagens e as respostas do JARVIS passam pela plataforma (bots do Telegram **não** têm criptografia ponta a ponta) | Só se você ligar a ponte e configurar o token. Padrão desligado; só IDs na lista de permitidos |
| **Instalar e baixar programas** | Catálogo e fontes do winget | O nome do programa buscado | Só com a sua confirmação |
| **Atualização** | GitHub (Releases) | A consulta de versão e o download do instalador; o GitHub vê o seu IP | Versão instalada com atualização automática ligada. Só instala com a sua confirmação |
| **Baixar modelos** | Ollama (registro de modelos) | O nome do modelo | `ollama pull` e o instalador |

Esses terceiros têm **as próprias políticas de privacidade**, que valem para o que recebem de você.

## 5. Recursos sensíveis

- **Microfone:** só com a voz ligada, e é fechado no Modo Apresentação.
- **Leitura de tela:** captura a janela-alvo ou o monitor **só em memória**, faz OCR no Windows e mascara senhas e tokens. O texto vai ao Ollama local.
- **Clipboard:** monitor desligado por padrão; o histórico ignora o que parece segredo.
- **E-mail:** o conteúdo é lido e resumido localmente. Envio, Lixeira e organização sempre mostram o que vão fazer e pedem confirmação.
- **Vigia de rede:** registra aparelhos da sua rede local (IP e MAC) e processos com conexão à internet. Isso inclui **dados de outras pessoas** que usam a sua rede. Tudo fica local.
- **Teclado, mouse e janelas:** só no Copilot.
- **Localização:** aproximada, pelo IP, para o clima.

Avise as pessoas no ambiente quando o microfone ou a tela estiverem em uso.

## 6. Seus controles

| O que | Como |
|-------|------|
| Voz | Começa desligada; liga com `/voice` ou `Ctrl+T` |
| Monitor de clipboard, pontes Telegram/Discord, manchetes | Desligados por padrão; ligam em `/config` → ROTINAS |
| Registro de insights, briefing automático, e-mails no briefing, Vigia de rede | Ligados por padrão; desligam em `/config` |
| Atualização automática | `/config` → SISTEMA |
| Integrações | `/config` → INTEGRAÇÕES: `Del` desconecta o card. Revogue também o acesso na conta do Google ou do Spotify |
| Skills | `/skills` liga e desliga cada uma ou categorias inteiras |
| Apagar dados | `/clip limpar` (histórico do clipboard), `/lembrete rm <n>`, `/rede reset`, ou apague a pasta de dados e as notas do vault |

## 7. Por quanto tempo os dados ficam

**No seu computador**, até você apagar: o JARVIS não tem prazo automático e **não faz expurgo de logs**. Para remover tudo, apague a pasta de dados e as notas que ele criou no vault (`Memória/` e `🧠 Brainstorms/J.A.R.V.I.S — Insights`). **Nos terceiros**, vale a política de cada um.

## 8. Segurança

- Tokens das integrações no Cofre de Credenciais do Windows; o `.env` não é versionado.
- Ações críticas só com confirmação explícita; nenhum texto do modelo vai para um shell.
- Senhas e tokens mascarados na leitura de tela e filtrados do histórico do clipboard.
- Ponte remota só para IDs liberados (lista vazia = ninguém) e com a confirmação presa a quem pediu.
- Anexos de e-mail bloqueiam arquivos sensíveis (`.env`, chaves, `.ssh`), pastas fora do seu perfil e arquivos maiores que 25 MB.
- O instalador de atualização tem o SHA-256 conferido.

**Limites:** o `.env` e o JSON de reserva dos tokens são texto; quem acessa a sua conta do Windows acessa o JARVIS. Considere criptografar o disco (BitLocker). Vulnerabilidades: [`SECURITY.md`](../SECURITY.md).

## 9. Seus direitos (LGPD)

Como o desenvolvedor não trata os seus dados, você exerce os direitos de acesso, correção, eliminação e portabilidade **diretamente nos seus arquivos**, que estão em formatos abertos (SQLite e Markdown). Para dados que um terceiro recebeu, fale com o terceiro. Dúvidas sobre esta política: abra uma issue no repositório.

## 10. Crianças e adolescentes

O JARVIS não é voltado a menores de idade. Se for usado por um menor, que seja com o acompanhamento de um responsável, que decide quais integrações conectar.

## 11. Mudanças nesta política

A versão vigente é a deste arquivo, com a data no topo; o histórico fica no git. Mudanças relevantes (nova integração ou novo dado guardado) entram também no `CHANGES.md`.

## 12. Contato

Dúvidas: issue no repositório do projeto. Segurança: [`SECURITY.md`](../SECURITY.md). Mantenedor: Felipe Grolla Freitas ([@Grolla05](https://github.com/Grolla05)). Veja também as variáveis de configuração em [`variaveis-ambiente.md`](variaveis-ambiente.md) e as chaves pessoais em [`integracoes-oauth.md`](integracoes-oauth.md).
