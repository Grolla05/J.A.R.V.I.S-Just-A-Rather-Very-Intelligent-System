- WEB_WATCH: Vigia uma página, o preço de um produto ou um repositório do GitHub e avisa sozinho quando muda (página nova, preço caiu, release ou commit novo). Também lista e para de vigiar.
  Use quando: o usuário pedir "vigia esse link", "me avisa quando o preço baixar", "monitora o preço dessa página abaixo de 300", "acompanha o repositório dono/repo", "me avisa quando sair release nova do X", "o que você está vigiando?", "para de vigiar o 2".
  NÃO use para lembrete com horário (isso é REMINDER), para pesquisar um preço agora (isso é WEB_SEARCH) nem para ver PRs/issues/CI na hora (isso é GITHUB).
  Entity: o link, o repositório (dono/repo) ou o número do item; senão null.
  Exemplos:
  - "me avisa quando o preço dessa página baixar de 300" -> {"intent": "WEB_WATCH", "entity": null, "confidence": 1.0}
  - "acompanha as releases do ollama/ollama" -> {"intent": "WEB_WATCH", "entity": "ollama/ollama", "confidence": 1.0}
  - "o que você está vigiando?" -> {"intent": "WEB_WATCH", "entity": null, "confidence": 1.0}
