- FACT_CHECK: Verifica se uma afirmação ou notícia é verdadeira cruzando fontes independentes na internet, e dá um veredito (confirmado, falso, impreciso ou inconclusivo) com as fontes.
  Use quando: o usuário pedir para checar/verificar/conferir se algo é verdade — "isso é verdade: …", "é fake que …?", "checa se …", "verifica essa notícia: …", "é boato que …?".
  NÃO use para pesquisa aberta sem afirmação a julgar ("pesquisa sobre X", "o que dizem sobre X" — isso é WEB_SEARCH) nem para conferir agenda, e-mail ou código.
  Entity: a afirmação a checar (sem "isso é verdade" ou "checa se").
  Exemplos:
  - "isso é verdade: a Muralha da China é visível do espaço" -> {"intent": "FACT_CHECK", "entity": "a Muralha da China é visível do espaço", "confidence": 1.0}
  - "é fake que o Brasil vai mudar a cor da bandeira?" -> {"intent": "FACT_CHECK", "entity": "o Brasil vai mudar a cor da bandeira", "confidence": 1.0}
