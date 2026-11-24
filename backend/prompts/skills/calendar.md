- CALENDAR: Consulta a agenda do Google do usuário (compromissos, reuniões, eventos).
  Use quando: Usuário perguntar "o que tenho hoje/amanhã", "minha agenda", "próxima reunião", "tenho compromisso na sexta", "estou livre à tarde", "o que tenho essa semana", "compromissos do fim de semana", "agenda do mês", "eventos do próximo mês", "o que tenho marcado este ano".
  Entity: o dia ou período citado ("hoje", "amanhã", "sexta", "semana", "próxima semana", "mês", "ano", "próxima") ou vazio.
  Exemplos:
  - "qual compromisso eu tenho essa semana?" -> {"intent": "CALENDAR", "entity": "semana", "confidence": 1.0}
  - "o que tenho marcado no próximo mês?" -> {"intent": "CALENDAR", "entity": "próximo mês", "confidence": 1.0}
