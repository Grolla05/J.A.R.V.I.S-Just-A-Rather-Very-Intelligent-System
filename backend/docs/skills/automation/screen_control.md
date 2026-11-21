# 🖥️ Skill: screen_control.py

A skill `screen_control.py` atua na categoria **Automation** e é indiscutivelmente uma das mais complexas no nível de sistema do projeto. Ela abandona completamente atalhos de janela (como `Win + Shift + Seta`) e injeta comandos puramente matemáticos e de Hardware diretamente no **Windows Kernel (Ctypes / Win32 API)** para gerenciar Monitores, Coordenadas de Janelas, Geometria DPI e Proteção Ocular.

## 📝 Contrato

- **INTENT**: `SCREEN_CONTROL`
- **PROMPT_TEXT**: Carregado na IA global para capturar requisições espaciais (Ex: "Joga o Chrome pra outra tela", "Minimiza isso", "Tá muito claro, escurece", "Ativa o modo noturno").
- **Não lê conteúdo**: ler, explicar ou resumir o que está na tela é da skill [`SCREEN_READ`](../productivity/screen_read.md). O `PROMPT_TEXT` das duas tem um "NÃO use para…" e o `classify_intent.md` traz exemplos que separam uma da outra.

---

## ⚙️ Arquitetura e Engenharia Interna

### 1. Consciência de Escala (DPI Awareness)

No ecossistema Windows moderno, usuários misturam monitores 4K (com 150% de escala) e monitores 1080p (com 100%). Se você consultar a coordenada de uma janela sem tratar o DPI, o Windows mente os valores, gerando movimentos totalmente quebrados.

- Para consertar isso na raiz, o topo do arquivo injeta na DLL `shcore`: `SetProcessDpiAwareness(2)`. O número 2 representa *Process_Per_Monitor_DPI_Aware*, forçando o Sistema Operacional a entregar as resoluções brutas exatas em pixels de cada hardware espetado na placa de vídeo, garantindo cálculos milimétricos.

### 2. O Sub-Agente de Janelas (`_ask_ollama_screen`)

Para entender semântica espacial, a skill despacha o texto para a LLM dedicada usando o `SCREEN_EXPERT_PROMPT` com Temperatura `0.1`.

- **Injeção de Contexto Físico**: Diferente de outros prompts mortos, este prompt recebe "Auras". O código injeta a hora atual do sistema `{current_hour}` e a quantidade de telas físicas detectadas `{monitors_info}` na memória do agente, para que ele decida sabiamente se "Joga pra outra tela" significa monitor secundário ou terciário.
- **JSON de Saída**: O Ollama é forçado a extrair ações modulares como `brightness`, `move_window` ou `retina_mode`, além de detectar alinhamentos (`maximize`, `left`, `center`, `maintain`).

### 3. Motor Físico de Janelas (Ctypes Math)

Quando o Jarvis decide mover uma janela, ele opera de forma hiper-agressiva varrendo as posições via memória:

1. Ele busca o HWND (Handle) da Janela usando `GetForegroundWindow` ou rastreia as abas em background via `find_window_by_title`.
2. Mapeia a grade global rodando o Enumerador C `EnumDisplayMonitors`.
3. Calcula o **Centro Geométrico** (`cx`, `cy`) da janela desejada para descobrir em que monitor físico ela se encontra agora.
4. **O Algoritmo `maintain`**: Se a janela estiver ocupando 25% do canto inferior esquerdo de um monitor 1080p, e o Jarvis jogar para um monitor 4K, ele recalcula a porcentagem base do eixo X e Y (`rel_x`, `rel_y`) e interpola o tamanho absoluto. A janela nasce no Monitor 2 milimetricamente idêntica na sua posição visual relativa.
5. Injeta a movimentação silenciosa via `MoveWindow` e acorda a janela com `SetForegroundWindow`.

### 4. Gestão Termal e Ocular (Protocolo Retina)

A skill possui o controle vital sobre a emissão de luz do ambiente do usuário, gerida em duas camadas (Failover de Brilho):

- **Camada 1: Hardware Brightness (`_try_wmi_brightness`)**: Tenta primeiro comunicar-se com a BIOS via `WMI (Windows Management Instrumentation)` rodando um script injetado de PowerShell. Se for um Laptop/Notebook, a luz real da tela diminui fisicamente.
- **Camada 2: Software Brightness (Gamma Ramp)**: Se for um PC Desktop genérico sem WMI ou cabo DDC/CI, o código faz o fallback para redução matricial de Pixels. Ele captura o `Device Context (DC)` mestre de vídeo da máquina com `GetDC(None)` e edita a curva de cor do Windows via `SetDeviceGammaRamp`.

### 5. Modo Retina Automático (Night Light)

A função `apply_retina_protocol()` não simula cliques no aplicativo de "Luz Noturna" do Windows. Ela escreve sua própria tabela de cores no Kernel:

- O Jarvis corta agressivamente a curva de emissão do canal de luz Azul em `-65%` (`warmth_level * 0.65`) e do canal de luz Verde em `-25%` (`warmth_level * 0.25`).
- Além disso, ele analisa o relógio. Se o usuário mandar aplicar o protocolo "Auto", o código lê a hora atual. Se o horário for entre as 18:00 da noite e as 06:00 da manhã, ele aplica o filtro laranja maciço para salvar a retina do desenvolvedor, ignorando a ativação caso seja dia.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Crash de Gama Ctypes (`Error 87`)**: O Windows é paranóico com a manipulação do `GammaRamp`. O ponteiro C `RAMP` exige matrizes estritas de *unsigned short* que nunca, em hipótese alguma, podem passar o valor de `65535` ou serem números negativos. O loop no código usa _Clamping_ estrito (`max(0, min(65535, value))`). Se o você plugar um monitor com perfil ICC quebrado que rejeite a rampa, a aplicação acusará erro mas liberará o DC (`ReleaseDC`) para não travar o kernel de vídeo do usuário.
- **Rastreio Oculto (`IsWindowVisible`)**: Na função recursiva que varre as janelas buscando nomes (ex: `"Puxa o Spotify pra cá"`), foi injetado o validador `user32.IsWindowVisible(hwnd)`. O Spotify frequentemente roda com 3 instâncias fantasmas sem janela (processos de render do Electron/Chromium). Sem essa checagem, o Jarvis moveria um processo fantasma pro outro monitor, resultando num "Sucesso" falso.
- **Janelas Maximizadas e `MoveWindow`**: A API do Windows bloqueia mover fisicamente janelas que estão no modo Fullscreen/Maximizadas. A função do Jarvis desvia disso restaurando temporariamente a janela com `ShowWindow(hwnd, 9)` (Restore) em uma fração de milissegundo, movendo a coordenada para o centro do monitor número 2, e só então chamando `ShowWindow(hwnd, 3)` (Maximize) novamente.
