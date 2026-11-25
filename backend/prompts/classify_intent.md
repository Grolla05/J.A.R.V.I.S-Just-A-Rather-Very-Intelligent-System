Sua missão é classificar a intenção do comando do usuário e extrair a entidade principal.

# REGRAS CRÍTICAS:
1. Responda APENAS o JSON, sem texto adicional.
2. Se houver um nome de aplicativo ou objeto no comando, ele DEVE ir para o campo 'entity'.
3. Nunca use "null" para 'entity' se houver um substantivo alvo na frase.
4. Escolha uma SKILL só quando o pedido se encaixar no "Use quando" dela. Perguntas gerais, explicações, programação e qualquer pedido que nenhuma skill cobre são "CHAT".
5. Se o comando envolver uma AÇÃO (desligar, abrir, tocar, etc), ele NUNCA será MEMORY_WRITE ou MEMORY_READ.
6. Pedido de AÇÃO que nenhuma skill da lista abaixo faz (abrir programa ou site, tocar música, mexer no volume...) é "CHAT". Nunca escolha uma skill "parecida" só porque ela é a mais próxima.

# DEFINIÇÃO DE CATEGORIAS:
- HARDWARE: Perguntas EXCLUSIVAS e DIRETAS sobre especificações físicas do computador host (CPU, RAM, GPU, bateria, temperatura, velocidade do cooler, velocidade da internet, armazenamento). NUNCA use se o usuário estiver pedindo explicações, fórmulas matemáticas, programando/codando, ou escrevendo textos gerais.
- MEMORY_WRITE: Use APENAS quando o usuário fornecer uma informação pessoal para você memorizar (Ex: "Meu nome é...", "Eu moro em...", "Memorize que meu time é...").
- MEMORY_READ: Use quando o usuário perguntar algo sobre si mesmo ou da sua vida pessoal que você deveria saber (Ex: "Quem sou eu?", "Onde eu moro?", "Qual o nome do meu pai?").
- CHAT: Perguntas gerais, explicações intelectuais, fórmulas matemáticas, códigos, programação, tarefas acadêmicas, saudações, piadas, ou conversas casuais que não envolvam especificações físicas diretas de hardware.
- $options_str: Categorias dinâmicas disponíveis.

# SKILLS E SEUS OBJETIVOS (PRIORIDADE ALTA):
$skills_prompts

# EXEMPLOS (os de cada skill vêm no bloco dela, acima):
- "quem sou eu?" -> {"intent": "MEMORY_READ", "entity": null, "confidence": 1.0}
- "meu nome é felipe" -> {"intent": "MEMORY_WRITE", "entity": "felipe", "confidence": 1.0}

Comando do Usuário: "$text"
Schema de Resposta: 
$schema
