Você decide se a mensagem do usuário contém um INSIGHT que vale guardar no caderno de ideias dele.

É insight (insight = true) quando o USUÁRIO:
- propõe uma ideia própria (produto, projeto, feature, texto, negócio, estudo);
- toma uma decisão ou define um plano ("vou fazer X", "decidi que Y");
- faz um brainstorm ou chega a uma conclusão/aprendizado que ele mesmo formulou.

NÃO é insight (insight = false):
- pergunta, pedido de explicação ou de ajuda, comando ou tarefa para o assistente;
- conversa casual, saudação, desabafo, opinião solta sem proposta;
- dado pessoal simples (nome, cidade, preferências);
- ideia que veio só da resposta do assistente, e não do usuário.

Na dúvida, responda false.

Se for insight:
- "title": título curto (até 8 palavras), sem aspas e sem ponto final.
- "summary": de 1 a 4 frases, em português, fiéis ao que o usuário disse. Use a resposta do assistente só para dar contexto; não acrescente ideias que o usuário não trouxe.

Mensagem do usuário:
"""
$message
"""

Resposta do assistente (contexto):
"""
$reply
"""

Responda APENAS o JSON:
{"insight": true ou false, "title": "...", "summary": "..."}
