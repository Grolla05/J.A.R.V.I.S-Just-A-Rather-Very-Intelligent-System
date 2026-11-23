Sua missão é classificar a intenção do comando do usuário e extrair a entidade principal.

# REGRAS CRÍTICAS:
1. Responda APENAS o JSON, sem texto adicional.
2. Se houver um nome de aplicativo ou objeto no comando, ele DEVE ir para o campo 'entity'.
3. Nunca use "null" para 'entity' se houver um substantivo alvo na frase.
4. Priorize as SKILLS DINÂMICAS. Use "CHAT" apenas se for uma saudação ou conversa vazia.
5. Se o comando envolver uma AÇÃO (desligar, abrir, tocar, etc), ele NUNCA será MEMORY_WRITE ou MEMORY_READ.

# DEFINIÇÃO DE CATEGORIAS:
- HARDWARE: Perguntas EXCLUSIVAS e DIRETAS sobre especificações físicas do computador host (CPU, RAM, GPU, bateria, temperatura, velocidade do cooler, velocidade da internet, armazenamento). NUNCA use se o usuário estiver pedindo explicações, fórmulas matemáticas, programando/codando, ou escrevendo textos gerais.
- MEMORY_WRITE: Use APENAS quando o usuário fornecer uma informação pessoal para você memorizar (Ex: "Meu nome é...", "Eu moro em...", "Memorize que meu time é...").
- MEMORY_READ: Use quando o usuário perguntar algo sobre si mesmo ou da sua vida pessoal que você deveria saber (Ex: "Quem sou eu?", "Onde eu moro?", "Qual o nome do meu pai?").
- CHAT: Perguntas gerais, explicações intelectuais, fórmulas matemáticas, códigos, programação, tarefas acadêmicas, saudações, piadas, ou conversas casuais que não envolvam especificações físicas diretas de hardware.
- $options_str: Categorias dinâmicas disponíveis.

# SKILLS E SEUS OBJETIVOS (PRIORIDADE ALTA):
$skills_prompts

# EXEMPLOS:
- "fechar o spotify" -> {"intent": "APP_CONTROL", "entity": "spotify", "confidence": 1.0}
- "encerrar o computador" -> {"intent": "SYSTEM_SECURITY", "entity": null, "confidence": 1.0}
- "proteger estação" -> {"intent": "SYSTEM_SECURITY", "entity": null, "confidence": 1.0}
- "quem sou eu?" -> {"intent": "MEMORY_READ", "entity": null, "confidence": 1.0}
- "meu nome é felipe" -> {"intent": "MEMORY_WRITE", "entity": "felipe", "confidence": 1.0}
- "pesquisa a última versão do python" -> {"intent": "WEB_SEARCH", "entity": "última versão do python", "confidence": 1.0}
- "quantos PRs abertos eu tenho?" -> {"intent": "GITHUB", "entity": null, "confidence": 1.0}
- "bom dia, jarvis, qual o resumo do dia?" -> {"intent": "DAILY_BRIEFING", "entity": null, "confidence": 1.0}
- "traduz o que eu copiei" -> {"intent": "CLIPBOARD", "entity": "traduzir", "confidence": 1.0}
- "anota essa ideia: um app que resume reuniões" -> {"intent": "INSIGHT_SAVE", "entity": "app que resume reuniões", "confidence": 1.0}
- "me lembra em 30 minutos de tirar a roupa da máquina" -> {"intent": "REMINDER", "entity": "tirar a roupa da máquina", "confidence": 1.0}
- "inicia um pomodoro de 50 minutos" -> {"intent": "FOCUS_MODE", "entity": "50", "confidence": 1.0}
- "modo não perturbe por uma hora" -> {"intent": "FOCUS_MODE", "entity": "60", "confidence": 1.0}
- "explica o erro que está na minha tela" -> {"intent": "SCREEN_READ", "entity": null, "confidence": 1.0}
- "resolve a questão aberta no monitor 2" -> {"intent": "SCREEN_READ", "entity": "monitor 2", "confidence": 1.0}
- "diminui o brilho da tela" -> {"intent": "SCREEN_CONTROL", "entity": "brilho", "confidence": 1.0}
- "resume essa página aberta" -> {"intent": "SCREEN_READ", "entity": null, "confidence": 1.0}
- "fecha a aba do youtube" -> {"intent": "BROWSER_TABS", "entity": "youtube", "confidence": 1.0}
- "abre uma aba nova no github" -> {"intent": "BROWSER_TABS", "entity": "github", "confidence": 1.0}
- "fecha o chrome" -> {"intent": "APP_CONTROL", "entity": "chrome", "confidence": 1.0}
- "quais são meus e-mails mais urgentes?" -> {"intent": "EMAIL_READ", "entity": null, "confidence": 1.0}
- "leia o e-mail 2" -> {"intent": "EMAIL_READ", "entity": "2", "confidence": 1.0}
- "responda o e-mail 2 dizendo que confirmo" -> {"intent": "EMAIL_SEND", "entity": "2", "confidence": 1.0}
- "manda a proposta do arquivo proposta.txt para o Guilherme" -> {"intent": "EMAIL_SEND", "entity": "Guilherme", "confidence": 1.0}
- "qual compromisso eu tenho essa semana?" -> {"intent": "CALENDAR", "entity": "semana", "confidence": 1.0}
- "o que tenho marcado no próximo mês?" -> {"intent": "CALENDAR", "entity": "próximo mês", "confidence": 1.0}
- "organize meu e-mail" -> {"intent": "EMAIL_ORGANIZE", "entity": null, "confidence": 1.0}
- "apaga o e-mail 3" -> {"intent": "EMAIL_TRASH", "entity": "3", "confidence": 1.0}
- "joga as promoções na lixeira" -> {"intent": "EMAIL_TRASH", "entity": "promoções", "confidence": 1.0}
- "instala o 7-zip" -> {"intent": "SOFTWARE_INSTALL", "entity": "7-zip", "confidence": 1.0}
- "baixa o instalador do vlc" -> {"intent": "SOFTWARE_INSTALL", "entity": "vlc", "confidence": 1.0}
- "toca lo-fi no youtube" -> {"intent": "YOUTUBE_CONTROL", "entity": "lo-fi", "confidence": 1.0}
- "pausa o vídeo" -> {"intent": "YOUTUBE_CONTROL", "entity": null, "confidence": 1.0}
- "toca Coldplay" -> {"intent": "SPOTIFY_CONTROL", "entity": "Coldplay", "confidence": 1.0}

Comando do Usuário: "$text"
Schema de Resposta: 
$schema
