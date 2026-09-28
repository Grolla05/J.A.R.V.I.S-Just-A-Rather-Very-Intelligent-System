# Changelog

## [Não lançado]

### Corrigido
- **Chat de texto não acionava skills de automação (`APP_CONTROL`, `SCREEN_CONTROL`)**: `execute_command_stream()` classificava a intenção com `skip_skills=True`, excluindo todas as skills ativas das opções do classificador de intenção. Comandos digitados no chat (ex.: "foca no notepad", "joga o spotify pro monitor 2") sempre caíam em `CHAT` genérico em vez de executar a ação. O caminho de voz já funcionava corretamente. (`backend/services/brain.py`)
- **`SCREEN_CONTROL`: janela movida para outro monitor não ganhava foco**: `move_window()` chamava `SetForegroundWindow` sozinho, sem contornar a restrição de foreground-lock do Windows; a falha era engolida por um `except: pass` que nunca capturava o retorno `FALSE` da API (não é exceção em Python/ctypes). A janela mudava de monitor mas não vinha para frente, sem nenhum log indicando o motivo. (`backend/skills/automation/screen_control.py`)
- **`APP_CONTROL`: `focus_window()` falhava silenciosamente, e para janelas minimizadas o `AppActivate` mentia sucesso**: dependia só de `WScript.Shell.AppActivate` via PowerShell, sujeito à mesma restrição de foreground-lock, sem fallback e sem log de erro. Além disso, para janelas minimizadas o `AppActivate` retornava "sucesso" mesmo sem realmente restaurar/focar a janela (só piscava a taskbar), fazendo o código encerrar cedo sem tentar o fallback robusto. Corrigido invertendo a prioridade: agora tenta primeiro o foco via Win32 direto (`core/window_utils.py`, que trata `IsIconic`/`SW_RESTORE` corretamente), e só cai pro `AppActivate` como último recurso. Reproduzido e verificado manualmente minimizando o Spotify antes do teste. (`backend/skills/automation/app_control.py`)
- **Ordem dos monitores não batia com a posição física**: `get_monitors()` retornava os monitores na ordem bruta do `EnumDisplayMonitors` (não garantida), então "Monitor 1"/"Monitor 2" podiam não corresponder a esquerda/direita reais. Agora a lista é ordenada por coordenada X. (`backend/core/window_utils.py`)

### Adicionado
- `backend/core/window_utils.py`: módulo compartilhado com as operações Win32 de janela/monitor (antes duplicadas e divergentes entre `app_control.py` e `screen_control.py`), incluindo `force_foreground()`, que implementa o contorno padrão (via `AttachThreadInput`) para a restrição de foreground-lock do Windows.
