- HEADLESS_TASK: Executa uma tarefa num site em segundo plano (navegador sem janela): abre o site, busca, clica e traz a informação pedida; avisa quando terminar.
  Use quando: o usuário pedir para entrar/acessar/navegar num site específico e trazer algo de lá ou fazer algo nele — "entra no site da kabum e vê o preço da rtx 5060", "acessa o site da receita e me traz…", "faz em segundo plano: abre … e …", "navega até … e copia …".
  NÃO use para pesquisa aberta sem site definido ("pesquisa sobre X" — isso é WEB_SEARCH), para checar se algo é verdade (FACT_CHECK), para vigiar preço/página ao longo do tempo (WEB_WATCH) nem para abrir um site na tela do usuário.
  Entity: o pedido inteiro (site + o que fazer).
  Exemplos:
  - "entra no site da kabum e vê o preço da rtx 5060" -> {"intent": "HEADLESS_TASK", "entity": "site da kabum, preço da rtx 5060", "confidence": 1.0}
  - "em segundo plano, abre a wikipedia e me traz a data de nascimento do Tesla" -> {"intent": "HEADLESS_TASK", "entity": "wikipedia, data de nascimento do Tesla", "confidence": 1.0}
