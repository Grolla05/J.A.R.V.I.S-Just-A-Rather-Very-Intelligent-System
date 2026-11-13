# 🗄️ database.py (Gerenciador de SQLite)

O arquivo `database.py` expõe a classe `DatabaseManager` e funciona puramente como o **Motor de Persistência** do J.A.R.V.I.S. Ele é responsável pela memória de curto, médio e longo prazo baseada em banco de dados relacional e não efêmera, sendo persistida em disco local através do motor SQLite3. Este módulo centraliza absolutamente toda a gravação e leitura de estado contínuo do assistente e da interface.

## 🎯 Responsabilidades Principais

1. **Auto-inicialização Robusta**: Garante que o banco `jarvis_memory.db` será criado integralmente no primeiro boot, caso não exista no computador do usuário, estabelecendo as quatro tabelas vitais: `config`, `history`, `hardware`, e `sessions`.
2. **Auto-Migração de Schemas (Sem Alembic)**: Diferente de sistemas complexos de backend, o JARVIS faz migrações invisíveis por conta própria. Ele roda queries introspectivas (`PRAGMA table_info`) para detectar colunas faltantes de versões antigas e faz o `ALTER TABLE` dinâmico caso encontre um banco desatualizado.
3. **Gerenciador de Estados (Tabela `config`)**: Armazena em formato Chave-Valor todas as configurações mutáveis pela TUI — *skills* desabilitadas, preferências do `/config` (`pref_*`), fontes de notícias, locais do `/rota` etc. —, serializando tudo em JSON. Lista completa de chaves em [`database/README.md`](../../database/README.md).
4. **Arquivo Vivo de Histórico (Tabelas `history` e `sessions`)**: Todo texto enviado por você e respondido pelo modelo é armazenado definitivamente. Esta dupla de tabelas alimenta os *save slots* da TUI (`Ctrl+O`: recarregar, fixar e apagar sessões) e a edição da última mensagem (`/edit`, `↑`).
5. **Inventário do Hospedeiro (Tabela `hardware`)**: Mapeia as entranhas da máquina rodando o LLM para que o modelo possa ser alimentado no Prompt Sistêmico ("Anti-Alucinação"), evitando que o assistente afirme que roda em nuvem.

---

## ⚙️ Arquitetura e Estruturas Internas

Assim como o restante do núcleo, a inicialização final exporta a instância `db = DatabaseManager()` em Padrão Singleton.

### 1. Sistema de Conexões e Threads Seguras

Para proteger contra a temida exceção de bloqueio simultâneo (*Database is Locked*) muito comum no SQLite executando em projetos assíncronos e multithread, cada operação (ler ou escrever) é estritamente encapsulada. O método `_get_connection()` entrega uma rota nova por requisição. Todas as funções seguem estritamente a lei: *Conecta -> Executa -> Dá Commit -> Fecha (bloco finally).*

### 2. Tratamento Avançado de UPSERT (`ON CONFLICT`)

Tanto em preferências (`save_config`) quanto em varreduras de máquina (`update_hardware_spec`), a instrução SQL empregada é a `ON CONFLICT(chave) DO UPDATE SET ...`.
Graças a este comportamento nativo de *UPSERT* (Update or Insert), o código dispensa consultas redundantes (Exemplo: *"Cheque primeiro se existe, se sim de Update, se não dê Insert"*). Isso corta pela metade o tempo de leitura do disco.

### 3. As Tabelas Estruturais

- **`config`**: Estrutura `[key, value, updated_at]`. A camada lógica do Python realiza a coerção dinâmica: Se mandarmos um dicionário ao chamar `save_config()`, o código intercepta a estrutura e roda um `json.dumps()` para enfiar a string inteira no DB. E ao puxar (`get_config`), roda `json.loads()`. Isso permite salvar *States* aninhados de UI num registro só.
- **`hardware`**: Estrutura `[component, description, detected_at]`. Contém métodos como `get_system_specs()` que puxam o texto formatado no formato de bala (bullet points) unicamente para alimentar diretamente o Prompt global da IA.
- **`sessions` e `history`**: A base completa de contexto do chat. O banco é automaticamente auto-otimizado através de índices velozes de busca (`CREATE INDEX IF NOT EXISTS idx_history_session`) gerados para agilizar o recorte de blocos quando a TUI só quer as mensagens da sessão X.

### 4. Edição Cirúrgica de Diálogos

Ao invés de tratar mensagens antigas como imutáveis, a interface necessita de funções profundas do SQLite:

- **`delete_history_from(session, message_id)`**: Ao apagar uma mensagem num bloco, tudo a partir daquele ponto adiante para baixo (`id >= message_id`) é dizimado para garantir consistência contextual se o usuário bifurcar uma conversa.
- **`update_history_message`**: Uma operação pura de `UPDATE history SET content...`, usada quando o usuário edita a última mensagem na TUI, sobrescrevendo ativamente as "Memórias" da IA.

### 5. RAG Nativas via SQL (`search_relevant_context`)

Se você pergunta algo ao Jarvis que escapa ao contexto explícito daquela sessão (e antes mesmo dele procurar na pasta do Obsidian), ele realiza uma requisição relacional. A engine:

1. Recebe a frase inteira de entrada.
2. Ignora *Stop Words* básicas de português (`como`, `quando`, `qual`, `jarvis`).
3. Elimina palavras menores que 3 caracteres.
4. Constrói um `LIKE` relacional com a condição `OR` dinamicamente entre todo o histórico passado.
5. Retorna as top 3 falas cruzadas.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Cuidado com Transações Zumbis**: É imperdoável utilizar o `cursor.execute` em qualquer lógica do backend *Jarvis* e não encadeá-lo através de um bloco `finally: conn.close()`. A arquitetura baseia-se em instanciar, modificar e finalizar o mais depressa possível. Omitir um `close()` vai travar fatalmente o loop principal do Webview na próxima iteração da thread.
- **Novas Tabelas e Migrações**: Como o projeto não utiliza bibliotecas inchadas como *Alembic* e *SQLAlchemy*, se você adicionar uma coluna nova na classe principal de inicialização `_initialize_tables`, **jamais esquecer** de fazer a diretiva de fallback para usuários com bancos de dados velhos (`PRAGMA table_info`), construindo manualmente o script de injeção `ALTER TABLE ADD COLUMN`. Caso contrário, os usuários das versões mais velhas darão tela azul quando a aplicação tentar inserir um dado numa tabela do passado.
- **Tipagem Não-Relacional Oculta**: Nunca declare uma chave na tabela `config` que possa ser salva ora como String limpa, ora como Objeto em JSON. Mantenha os padrões tipados fixos por cada chave. O bloco inteligente de `json.loads` faz *Try/Except*, e usar misturas causará comportamento corrompido no retorno.
