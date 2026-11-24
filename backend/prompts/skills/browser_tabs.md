- BROWSER_TABS: Controlar as ABAS do navegador (Opera GX, Chrome, Edge, Brave) — abrir aba nova (vazia, num site ou com uma busca), fechar a aba atual ou uma aba pelo nome/número, fechar as outras abas, ir para uma aba, próxima/anterior, reabrir a aba fechada, listar as abas, recarregar, voltar/avançar página, duplicar aba e abrir janela anônima.
  Use quando: o usuário falar de "aba", "guia", "página" do navegador ou "janela anônima" — "abre uma aba nova no github", "fecha a aba do YouTube", "vai para a terceira aba", "quais abas estão abertas?", "reabre a aba que eu fechei", "recarrega a página", "fecha as outras abas".
  NÃO use para abrir, fechar ou focar o PROGRAMA navegador inteiro ("abre o chrome", "fecha o opera") — isso é APP_CONTROL. NÃO use para tocar ou controlar vídeo do YouTube — isso é YOUTUBE_CONTROL. NÃO use para resumir/ler o conteúdo da página — isso é SCREEN_READ. NÃO use para pesquisar e responder uma pergunta — isso é WEB_SEARCH.
  Entity: a aba ou o site citado ("youtube", "3", "github"); null se não houver.
  Exemplos:
  - "fecha a aba do youtube" -> {"intent": "BROWSER_TABS", "entity": "youtube", "confidence": 1.0}
  - "abre uma aba nova no github" -> {"intent": "BROWSER_TABS", "entity": "github", "confidence": 1.0}
