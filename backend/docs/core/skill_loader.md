# 🧩 skill_loader.py (Injeção de Dependência Dinâmica)

O arquivo `skill_loader.py` implementa a classe `SkillManager`, operando como o motor base do **Sistema de Extensibilidade Plug-and-Play** do J.A.R.V.I.S. Em vez de criar um código inchado no `brain.py` adicionando dezenas de laços condissionais (`if intent == X: faz X else if intent == Y: faz Y`) para cada nova funcionalidade, este script automatiza inteiramente a expansão das capacidades da inteligência artificial. Ele varre a pasta `/skills`, compila e injeta as ações dinamicamente direto na memória do núcleo no exato momento da inicialização do servidor.

## 🎯 Responsabilidades Principais

1. **Auto-Discovery (Descoberta Automática)**: Utilizando a função varredora `os.walk`, o loader adentra recursivamente em todas as subpastas da raiz `skills/`. Ele prospecta estritamente arquivos terminados na extensão `.py`, sumariamente ignorando arquivos de empacotamento padrão (`__init__.py`).
2. **Dynamic Loading On-The-Fly**: Evita o uso de importações hardcoded. O motor realiza a magia de compilação em tempo de execução usando a biblioteca nativa `importlib.util` (através dos comandos `spec_from_file_location` e `exec_module`). Isso materializa o script num objeto Python acoplável.
3. **Validação Rigorosa de Contrato**: Para proteger a aplicação de arquivos espúrios na pasta ou scripts inacabados de desenvolvedores, o loader checa se a skill preenche os requisitos mínimos para existir. O módulo importado **obrigatoriamente** deve possuir expostos os atributos `INTENT` (String) e `execute(entity, command)` (Callable de 2 argumentos). `PROMPT_TEXT` alimenta o classificador.
4. **Alimentador Global de Prompt**: Todo o comportamento da IA necessita que ela saiba o que pode fazer. O loader procura agressivamente pela string descritiva opcional `PROMPT_TEXT` em cada arquivo. Ele aglutina todas as descrições descobertas na lista em memória viva `self.prompts`, que será descarregada crua no *Prompt de Sistema* do LLM no `brain.py`.

---

## ⚙️ Arquitetura e Estruturas Internas

Assim como outros arquivos do `core`, ele também orquestra Padrão Singleton, instanciando e trigando a execução imediatamente ao final do script via `manager = SkillManager(); manager.load_skills()`.

### 1. Injeção de Metadados e Metaprogramação

Se o arquivo Python passar pela varredura com sucesso, o loader não apenas empacota a função; ele modifica o módulo estruturalmente em runtime injetando duas variáveis vitais debaixo dos panos:

- `module.CATEGORY`: Ele executa o parseador nativo do SO (`os.path.basename(os.path.dirname(full_path))`) para assumir que a Categoria daquela Skill é idêntica à pasta mãe onde ela está alocada (Ex: salvar em `skills/IoT/luz.py` faz a skill herdar "IoT" automaticamente). A TUI usa essa tag para agrupar os cartuchos do `/skills` por categoria, e o `services/intent.py` para decidir o que roda no Chat (`automation` e `system` ficam só no Copilot/voz).
- `module.FILE_NAME`: Guarda o nome bruto para auditoria.

### 2. Dicionário de Invocação Mágica (O(1))

Toda *skill* validada é jogada num simples dicionário mutável no formato de pares chave/valor: `self.skills[intent_name] = module`.
Quando o processador central (LLM) analisa a fala do usuário e decide invocar um processo (retornando o JSON *`{"intent": "AUDIO_CONTROL", "entity": "30"}`*), a mágica de execução custa processamento mínimo à CPU (`O(1)` em Notação Big O).
O núcleo executa o equivalente lógico de `manager.skills["AUDIO_CONTROL"].execute("30", "aumenta o volume para 30")`. Sem interrupções, sem listas sequenciais ou cascatas condicionais pesadas.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Compartimentalização de Danos Severos (Sandboxing)**: Ao desenvolver uma nova automação, saiba que o método importador usa a cláusula de exceção genérica `except Exception`. Se você fizer *deploy* de uma *skill* que possui falha bruta de sintaxe (faltando dois-pontos, tabs quebrados) ou possua importação inatingível (`import pacote_nao_instalado`), a varredura ativamente engolirá a exceção, escreverá um modesto log de erro e prosseguirá para o próximo arquivo. Isso garante que sua automação defeituosa de ligar a luz jamais impeça o J.A.R.V.I.S de dar o boot para conversar normalmente com os usuários.
- **Nomenclatura Estrita (`INTENT`)**: O valor da constante `INTENT` é a pedra fundamental do ecossistema e atua como a única *Primary Key* indexada no dicionário global. **Nunca crie duas skills com o mesmo nome de `INTENT` em pastas diferentes**. A colisão de strings não travará o sistema; em vez disso, graças ao comportamento intrínseco de Dicionários em Python, a última skill que for varrida pela ordem alfabética de diretório do `os.walk` esmagará a habilidade e o código da *skill* anterior, deletando-a do bot.
- **Desligamento e Controle**: Se o usuário desativar a *skill* no `/skills` da TUI, é o motor cognitivo dentro do `brain.py` que fará a checagem no banco de dados SQLite para se abster de invocar o `execute()`. O *Skill Loader*, por si só, sempre sobe todas as *skills* para a memória RAM, independentemente delas terem sido ativas ou inativas no UI, garantindo que o módulo não precise reconstruir a memória a cada clique na TUI.
