- FORM_FILL: Preenche um formulário de um site com os dados que o JARVIS já conhece do usuário (nome, e-mail, cidade, LinkedIn, GitHub…), numa janela do Edge, e PARA antes de enviar: só envia com "sim".
  Use quando: o usuário pedir para preencher/completar um formulário, cadastro ou inscrição — "preenche esse formulário", "preenche o cadastro desse link …", "completa a inscrição pra mim".
  NÃO use para tarefas de leitura num site (HEADLESS_TASK), para responder e-mail (EMAIL_MANAGEMENT) nem para salvar dados na memória (MEMORY_WRITE).
  Entity: o link do formulário, se houver; senão null (usa a página aberta no navegador).
  Exemplos:
  - "preenche esse formulário" -> {"intent": "FORM_FILL", "entity": null, "confidence": 1.0}
  - "preenche a inscrição https://forms.example.com/evento" -> {"intent": "FORM_FILL", "entity": "https://forms.example.com/evento", "confidence": 1.0}
