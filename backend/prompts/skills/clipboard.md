- CLIPBOARD: Age sobre o que o usuário copiou (área de transferência): explicar código, traduzir texto, resumir link ou texto.
  Use quando: Usuário disser "explica o que eu copiei", "traduz o que copiei", "resume esse link que copiei", "o que tem no clipboard" ou "área de transferência".
  NÃO use para o que está aberto na tela/janela sem ter sido copiado — isso é SCREEN_READ.
  Entity: a ação pedida ("explicar", "traduzir" ou "resumir"), ou null.
  Exemplos:
  - "traduz o que eu copiei" -> {"intent": "CLIPBOARD", "entity": "traduzir", "confidence": 1.0}
