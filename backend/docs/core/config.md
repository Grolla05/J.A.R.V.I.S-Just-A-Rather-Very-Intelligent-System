# ⚙️ config.py (Configurações Core)

O arquivo `config.py` atua como o **Centro Nervoso de Configurações Globais** do J.A.R.V.I.S. Ele é a primeira peça estrutural do núcleo (`core`) a ser invocada por qualquer outro arquivo do sistema, tendo como missão principal eliminar hardcodes de caminhos, rotear variáveis de ambiente seguras e criar a infraestrutura básica do sistema de arquivos antes de qualquer lógica rodar.

## 🎯 Responsabilidades Principais

1. **Path Routing Dinâmico e Absoluto**: Impede definitivamente os comuns erros de "FileNotFoundError" que ocorrem no Python ao invocar o executável a partir de pastas de trabalho diferentes (`cwd`). Ele mapeia o projeto pela raiz estrutural.
2. **Environment Mapping Rigoroso (.env)**: Carrega dados sensíveis de credenciais (API Keys, Hosts, Senhas) de forma isolada do repositório público (utilizando a biblioteca `python-dotenv`).
3. **Bootstrapping de Pastas em Tempo Real**: Atua garantindo a infraestrutura do sistema. Na importação do arquivo, ele automaticamente "costura" os diretórios base como `/database`, `/logs` e `/assets/sounds` se eles não existirem nativamente no PC.
4. **Sanity Check (Modo Segurança Pré-Boot)**: Um método crítico manual (`perform_sanity_check()`) roda para confirmar a estabilidade de recursos essenciais antes do "Cérebro" e da TUI subirem.

---

## ⚙️ Arquitetura Interna e Variáveis

A classe principal de configuração se chama `Settings` e funciona guiada pelo Padrão de Projeto *Singleton*. Ao final do arquivo, a instância `settings = Settings()` é inicializada e exposta globalmente, executando automaticamente o método `create_dirs()`.

### 1. Resolução Reversa de Caminhos

O `config.py` se localiza fisicamente via o módulo *Pathlib*:

- `FILE_PATH = Path(__file__).resolve()` (Acha onde ele mesmo está: `backend/core/config.py`)
- `BACKEND_DIR = FILE_PATH.parent.parent` (Volta duas pastas, cravando o caminho exato do backend)
- `ROOT_DIR = BACKEND_DIR.parent` (Raiz do projeto inteiro)

Isso o permite localizar o arquivo `.env` perfeitamente em `ROOT_DIR / ".env"` (dev).

**Modo instalado:** se a variável de ambiente `JARVIS_DATA_DIR` existir (o `jarvis.cmd` do instalador define `%APPDATA%\JARVIS`), o `.env`, os logs, o banco, os uploads e o áudio do TTS vão para lá (`settings.DIR_DATA`, `IS_INSTALLED = True`), porque a pasta do programa pode ser só leitura. Por isso todo caminho gravável sai de `settings.DIR_*`/`settings.DB_PATH`, nunca de `Path(__file__)`.

### 2. Grupo de Parâmetros e Variáveis de Ambiente

Todas as chaves leem valores padrões via `os.getenv`, garantindo tolerância a falhas caso o usuário não declare variáveis genéricas:

- **Propriedades Base**: `PROJECT_NAME` e `VERSION`. O controle de verbosidade de *logs* responde estritamente a chave booleana de `DEBUG_MODE`.
- **Mecanismos de Cérebro (Ollama)**: Controla centralmente o endereço e modelo local (`OLLAMA_MODEL`, `OLLAMA_HOST`). Alterar o modelo aqui propaga instantaneamente a inteligência na inicialização do `brain.py`.
- **Credenciais do Cofre de Memória (Obsidian)**: Configura o acesso com `OBSIDIAN_HOST` e a porta criptografada pela `OBSIDIAN_API_KEY`.
- **Métricas de Rede e Resiliência (Timeouts)**:
  - `TIMEOUT_API (10s)`: Define o prazo de desistência da requisição do LLM.
  - `TIMEOUT_VOICE (5s)`: Interrupção segura do STT de reconhecimento para que o loop cognitivo não fique congelado caso o microfone trave.
- **Acústica e STT (Microfone/Falas)**: Define `DEFAULT_LANGUAGE` (nativamente pt-BR), velocidade de processamento vocal (`SPEECH_RATE`), o índice local de placa de som (`MIC_INDEX`), `MIC_ENERGY_THRESHOLD` e as `WAKE_WORDS`.
- **Demais grupos**: Ollama avançado (`OLLAMA_KEEP_ALIVE`, `OLLAMA_NUM_CTX`, `OLLAMA_NUM_GPU`, `OLLAMA_AUTOSTART`, `OLLAMA_VISION_MODEL`), Whisper (`WHISPER_*`), anexos (`MAX_UPLOAD_SIZE_MB`), integrações (`GOOGLE_CLIENT_ID/SECRET`, `SPOTIFY_CLIENT_ID`, `GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO`, `TOMTOM_API_KEY`), agente (`GLOBAL_HOTKEY`, `TRANSLATE_HOTKEY`), atualização (`AUTO_UPDATE`, `UPDATE_REPO`) e Pomodoro (`POMODORO_*`). A lista comentada fica no `env.example`.
- **Intervalos da TUI**: `TELEMETRY_INTERVAL` (3 s) e `HEALTH_INTERVAL` (15 s); cache do classificador `INTENT_CACHE_TTL`/`INTENT_CACHE_SIZE`.

> Variável nova do `.env` precisa de **padrão** no `Settings`: `.env` antigos (de instalações anteriores) não ganham a chave sozinhos.

### 3. Gerenciamento Temporal do Logger (`get_current_log_path`)

O sistema foi concebido para não colapsar o HD ao longo dos anos. O método atrelado aos diretórios de logs avalia a data de hoje via `datetime.now()` e cria on-the-fly *subpastas* para o Ano e Mês (`logs/2026/06/...`). Isso estilhaça os arquivos textuais pesados, garantindo legibilidade extrema e segurança contra exaustão de tamanho máximo de I/O em arquivos únicos em texto plano.

### 4. Checklist de Sanidade (`perform_sanity_check`)

Esta função é chamada no início do `main.py`, antes da TUI subir:

- Dispara uma validação na própria pasta de backend.
- Lança um log proeminente de `CRITICAL` e engatilha um `sys.exit(1)` em vez de deixar o programa explodir sozinho à frente por falha de diretório.
- Se a *flag* de DEBUG estiver `True`, alerta ao desenvolvedor sobre a emissão densa de logs no terminal, para controle de performance.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Criação de Variáveis Seguras**: Jamais injete e puxe uma chamada pura `os.getenv("MINHA_NOVA_API_KEY")` no meio de um arquivo como `brain.py`, uma skill ou a TUI. Todo e qualquer `.env` deve ser importado unicamente e primeiramente dentro do `config.py` sendo roteado estaticamente para um atributo da classe `Settings`. Isso centraliza a documentação e mapeamento de chaves exigidas no repositório.
- **Novas Rotas e Caminhos Absolutos**: Quando criar uma nova pasta obrigatória no software (exemplo: `backend/models`), registre ela no corpo de variáveis de diretório (ex: `DIR_MODELS = BACKEND_DIR / "models"`) e não se esqueça de adicionar a execução de criação física no método genérico da classe `create_dirs()` com o parâmetro de segurança de HD `exist_ok=True`.
- **Expansão de Verificação**: Se o projeto acoplar, por exemplo, um banco de dados hospedado em nuvem externa no futuro, é estritamente na função `perform_sanity_check()` que se deve arquitetar um ping inicial. Caso a nuvem demore mais do que o Timeout, abortar o software.
