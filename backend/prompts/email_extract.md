Extraia do pedido do usuário os dados para escrever um e-mail. Responda SOMENTE em JSON:
{"reply_to_index": <número do e-mail da lista a responder ou null>, "recipient": "<nome ou endereço do destinatário, ou null>", "file": "<nome ou caminho do arquivo a anexar, ou null>", "instruction": "<o que o e-mail deve dizer>"}

Exemplos:
- "responda o e-mail 2 dizendo que confirmo" → {"reply_to_index": 2, "recipient": null, "file": null, "instruction": "dizer que confirmo"}
- "manda a proposta do arquivo proposta.txt para o Guilherme" → {"reply_to_index": null, "recipient": "Guilherme", "file": "proposta.txt", "instruction": "enviar a proposta em anexo"}
- "escreve para ana@uni.br pedindo a lista de exercícios" → {"reply_to_index": null, "recipient": "ana@uni.br", "file": null, "instruction": "pedir a lista de exercícios"}

Pedido: $command
