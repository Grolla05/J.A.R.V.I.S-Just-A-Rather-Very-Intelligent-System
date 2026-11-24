- SOFTWARE_INSTALL: Procura um programa no catálogo oficial do Windows (winget) e instala, ou só baixa o instalador. Sempre pede confirmação.
  Use quando: "instala o 7-zip", "baixa o instalador do vlc", "quero o discord no meu pc".
  NÃO use para abrir/fechar um programa já instalado (APP_CONTROL) nem para pesquisar na web (WEB_SEARCH).
  Entity: o nome do programa ("7-zip", "vlc").
  Exemplos:
  - "instala o 7-zip" -> {"intent": "SOFTWARE_INSTALL", "entity": "7-zip", "confidence": 1.0}
  - "baixa o instalador do vlc" -> {"intent": "SOFTWARE_INSTALL", "entity": "vlc", "confidence": 1.0}
