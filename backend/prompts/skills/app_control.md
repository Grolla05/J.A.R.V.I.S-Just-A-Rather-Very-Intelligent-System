- APP_CONTROL: Abrir, fechar ou focar programas.
  Use quando: Usuário citar nomes de software (Chrome, Spotify, Code, etc) com a ação de abrir, fechar ou focar.
  NÃO use para abas do navegador ("fecha a aba do YouTube", "abre uma aba nova") — isso é BROWSER_TABS — nem para tocar vídeo no YouTube (YOUTUBE_CONTROL).
  Exemplos:
  - "fechar o spotify" -> {"intent": "APP_CONTROL", "entity": "spotify", "confidence": 1.0}
  - "fecha o chrome" -> {"intent": "APP_CONTROL", "entity": "chrome", "confidence": 1.0}
