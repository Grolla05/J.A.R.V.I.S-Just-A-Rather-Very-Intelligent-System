O usuário pediu um lembrete. Extraia daqui a quantos minutos ele deve disparar e o assunto.

Responda APENAS o JSON:
{"minutes": <número de minutos a partir de agora>, "text": "<assunto do lembrete, sem o horário e sem 'me lembra'>"}

Regras:
- "daqui a pouco" = 15; "mais tarde" = 120; "em uma hora e meia" = 90.
- Se a frase não disser quando, responda {"minutes": null, "text": "<assunto>"}. Não invente um horário.
