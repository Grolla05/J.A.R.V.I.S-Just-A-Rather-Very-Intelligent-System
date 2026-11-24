- FOCUS_MODE: Pomodoro e modo Não Perturbe (silencia notificações do Windows e alertas do JARVIS).
  Use quando: Usuário pedir "pomodoro", "modo foco", "foco de N minutos", "não perturbe", "silencia as notificações", "pausa o foco", "pula a pausa", "quanto falta" (do foco) ou "encerra o foco".
  Entity: a duração em minutos, se citada (ex: "50").
  Exemplos:
  - "inicia um pomodoro de 50 minutos" -> {"intent": "FOCUS_MODE", "entity": "50", "confidence": 1.0}
  - "modo não perturbe por uma hora" -> {"intent": "FOCUS_MODE", "entity": "60", "confidence": 1.0}
