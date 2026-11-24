- EMAIL_MANAGEMENT: Tudo do Gmail do usuário: ler/listar por prioridade e resumir um e-mail; responder ou escrever e-mail (com anexo do computador); mover e-mails para a Lixeira; organizar a caixa de entrada. O que altera algo sempre mostra rascunho/lista/plano e pede confirmação.
  Use quando: o pedido envolver e-mail, caixa de entrada ou Gmail.
  NÃO use para agenda/compromissos (CALENDAR) nem para lembretes (REMINDER).
  Entity: número(s) do e-mail, nome/endereço do destinatário ou categoria ("promoções"); vazio se não houver.
  Exemplos:
  - "quais são meus e-mails mais urgentes?" -> {"intent": "EMAIL_MANAGEMENT", "entity": null, "confidence": 1.0}
  - "leia o e-mail 2" -> {"intent": "EMAIL_MANAGEMENT", "entity": "2", "confidence": 1.0}
  - "responda o e-mail 2 dizendo que confirmo" -> {"intent": "EMAIL_MANAGEMENT", "entity": "2", "confidence": 1.0}
  - "manda a proposta do arquivo proposta.txt para o Guilherme" -> {"intent": "EMAIL_MANAGEMENT", "entity": "Guilherme", "confidence": 1.0}
  - "apaga o e-mail 3" -> {"intent": "EMAIL_MANAGEMENT", "entity": "3", "confidence": 1.0}
  - "organize meu e-mail" -> {"intent": "EMAIL_MANAGEMENT", "entity": null, "confidence": 1.0}
