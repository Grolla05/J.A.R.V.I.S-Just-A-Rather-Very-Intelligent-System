- WEB_SEARCH: Pesquisa na internet e resume o resultado com fontes.
  Use quando: Usuário pedir para "pesquisar", "buscar na internet", "procurar no Google", "o que dizem sobre", ou perguntar algo atual (notícias, preços, versões, resultados) que exige a web.
  NÃO use para conhecimento geral que não muda (capital de um país, definições, contas, história, explicações, programação) — isso é CHAT, mesmo em forma de pergunta. Use só quando a resposta depende de algo atual ou quando o usuário pedir para pesquisar.
  Entity: a pergunta/termo a pesquisar (sem "pesquisa" ou "Jarvis").
  Exemplos:
  - "pesquisa a última versão do python" -> {"intent": "WEB_SEARCH", "entity": "última versão do python", "confidence": 1.0}
  - "qual a capital da França?" -> {"intent": "CHAT", "entity": null, "confidence": 1.0}
