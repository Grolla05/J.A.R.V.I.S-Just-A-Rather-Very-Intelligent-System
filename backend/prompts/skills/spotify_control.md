- SPOTIFY_CONTROL: Controlar a música no Spotify — buscar e tocar faixas, tocar playlists, pausar, retomar, pular, voltar, ver o que está tocando e adicionar à fila.
  Use quando: O usuário pedir para tocar/colocar uma música, artista ou playlist; mandar pausar, parar, retomar, continuar, pular, próxima, anterior ou voltar a música; perguntar que música está tocando; ou pedir para adicionar algo na fila.
  NÃO use quando: O usuário quiser apenas abrir ou fechar o aplicativo Spotify (isso é APP_CONTROL), mudar o volume do sistema (isso é AUDIO_CONTROL) ou tocar/controlar algo no YouTube ou um vídeo (isso é YOUTUBE_CONTROL).
  Exemplos:
  - "toca Coldplay" -> {"intent": "SPOTIFY_CONTROL", "entity": "Coldplay", "confidence": 1.0}
