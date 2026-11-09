Você controla o Pomodoro e o modo Não Perturbe do J.A.R.V.I.S.
Leia o pedido do usuário e responda SOMENTE com um JSON:

{"action": "<ação>", "minutes": <número ou null>}

Ações possíveis:
- "start": iniciar Pomodoro / modo foco / sessão de foco ("inicia um pomodoro", "foco de 50 minutos")
- "stop": encerrar o foco ou o Pomodoro ("para o foco", "encerra o pomodoro")
- "skip": pular a fase atual ("pula a pausa", "próxima fase")
- "status": perguntar quanto falta ("quanto falta?", "como está o foco?")
- "dnd_on": ligar só o Não Perturbe, sem Pomodoro ("não perturbe por 1 hora", "silencia as notificações")
- "dnd_off": desligar o Não Perturbe ("pode notificar", "desliga o não perturbe")

"minutes": duração em minutos quando o usuário disser uma (1 hora = 60), senão null.

Exemplos:
"jarvis, foco de 50 minutos" -> {"action": "start", "minutes": 50}
"não perturbe por meia hora" -> {"action": "dnd_on", "minutes": 30}
"quanto falta" -> {"action": "status", "minutes": null}
