# 📓 obsidian.py (Integração de Conhecimento e MCP)

O arquivo `obsidian.py` atua como a ponte profunda de integração entre o Cérebro do J.A.R.V.I.S. (LLM) e a sua **Base de Conhecimento Pessoal (Vault)** do Obsidian. Diferente do SQLite (que age primariamente como memória de curto/médio prazo em formato de banco tabular), o Obsidian funciona como o "Cofre" semântico de longo prazo, guardando anotações textuais ricas, identidades corporais da máquina e os documentos do usuário.

## 🎯 Responsabilidades Principais

1. **Cliente REST Simples (`ObsidianClient`)**: Classe pioneira que ataca a porta HTTP direta do plugin "Local REST API" do Obsidian. Usada para funções rápidas e leves como extração direta de metadados simples de notas específicas (Ex: Ler preferências numéricas e *flags*).
2. **Cliente MCP Híbrido (`ObsidianMCPClient`)**: Implementação avançada do *Model Context Protocol* via canal `stdio`. Ele sobe um subprocesso chamando a ferramenta de terminal `uvx mcp-obsidian`, injetando as chaves de API secretas e permitindo ao Jarvis usar *Tools* externas (como `obsidian_simple_search`) como se fossem funções nativas do Python.
3. **Mecanismo de RAG Nativo (Retrieval-Augmented Generation)**: Concentra a estrela de inteligência artificial do arquivo, a função `get_vault_context()`. Antes do cérebro dar qualquer resposta, esse método atua interceptando a pergunta e vasculhando as pastas do Obsidian para armar o LLM de contexto prévio.

---

## ⚙️ Arquitetura Interna e Lógicas

### 1. Sistema de Memória Dedicada (REST Client)

A constante global `MEMORY_NOTE_PATH = "🚀 Projetos/J.A.R.V.I.S/Memória/{key}.md"` dita onde memórias efêmeras criadas pela IA são salvas. **Regra**: o caminho tem emoji e acento, então sempre passa por `urllib.parse.quote(..., encoding="utf-8")` antes de ir para a REST API — sem isso, 404. Notas existentes nunca são sobrescritas (preserva edições manuais).

- O método `get_memory` ignora o bloco de "Frontmatter" (as propriedades com `---` no topo do arquivo Markdown) e pega estritamente a primeira linha de texto útil.
- O método `save_memory` tem bloqueio de segurança: Se a nota `.md` já existe, a IA cruza os braços e diz *"nota já existe, mantendo versão do vault"*, abstendo-se de sobrescrevê-la. O sistema assume que se a nota existe, o "Senhor" pode ter editado ela na mão e inserido formatações preciosas que um simples re-salvamento em texto plano destruiria.

### 2. Bypass Assíncrono do MCP (`ObsidianMCPClient._run`)

O protocolo MCP é massivamente baseado na biblioteca `asyncio`, porém o J.A.R.V.I.S chama o vault de dentro de threads síncronas (workers da TUI e skills), que não podem misturar corrotinas.
O método `_run(self, coro)` tenta usar `asyncio.run()`, mas possui um `except RuntimeError` vital. Se o Python reclamar que já existe um Event Loop rodando (como na tela do app), ele cria imediatamente um `concurrent.futures.ThreadPoolExecutor(max_workers=1)` para envelopar e rodar o MCP isoladamente de forma Síncrona, desengasgando o processo.

### 3. O Pipeline de RAG (`get_vault_context`)

Quando o usuário digita ou fala uma sentença, o método executa a varredura em "Duas Camadas":

- **Camada 1: Identidade Pessoal Direta (Hardcoded)**
  O sistema contém um gigantesco dicionário de atalhos em memória (`_PROFILE_KEYWORDS`), com palavras como: *nome, família, faculdade, stack, setup, objetivo, moro*.
  Se a pergunta do usuário casar com pelo menos uma dessas palavras, o sistema entra na Camada 1: aborta procuras custosas, usa o MCP e extrai agressivamente o arquivo matriz `⚙️ Configurações/🧠 Sobre mim.md` na íntegra.

- **Camada 2: Busca Semântica via MCP**
  Se a frase for específica (Ex: *"Me lembre como resolvemos o bug do Docker"*):
  1. A IA usa `_STOPWORDS` para limpar sujeira da frase ("o", "a", "como", "jarvis").
  2. Manda a busca limpa (top 4 keywords) para o `obsidian_simple_search`.
  3. **Filtro de Ruído**: Ele parseia o JSON de resposta e **exclui ativamente** arquivos que comecem com a pasta `_templates`, impedindo que a IA alucine tentando ler moldes vazios do Obsidian.
  4. Pega o arquivo de maior `score` do JSON e puxa o conteúdo absoluto via `obsidian_get_file_contents` para empacotar e mandar ao Cérebro.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Codificação de URL é Lei**: Jamais passe caminhos de arquivos diretamente para qualquer requisição dentro do `ObsidianClient`. É absolutamente obrigatório passar os textos pela conversão `urllib.parse.quote(..., safe="", encoding="utf-8")`. Sem isso, espaços em branco e acentos típicos de pastas (ex: "Configurações", "Memória") resultarão em Erro 404 instantâneo.
- **Portas Dinâmicas do MCP**: Ao configurar a `StdioServerParameters`, perceba que o ambiente Python quebra explicitamente a string do HOST (ex: `http://127.0.0.1:27123`) em host e porta, e as repassa debaixo dos panos para as variáveis de ambiente `OBSIDIAN_HOST` e `OBSIDIAN_PORT`. Caso adicione conexões externas (ex: HTTPS), certifique-se que esse string-splitter não corromperá a chave de conexão.
- **Ampliação do Perfil (Camada 1)**: Se você for colocar assuntos completamente novos sobre a sua vida pessoal no arquivo genérico `Sobre mim.md` (Ex: Comecei a colecionar relógios), lembre-se de vir manualmente no array de `_PROFILE_KEYWORDS` neste arquivo e acrescentar a palavra ("relógio", "relogios", "coleção"). Do contrário, a IA fará buscas na "Camada 2" (Busca Larga) e pode trazer anotações erradas perdidas pelo vault.
