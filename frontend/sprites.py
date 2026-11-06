"""Sprites pixel-art e efeitos 16-bit da TUI — lógica pura, sem Textual.

Mesmo formato do `orb.py`: um sprite é uma grade de códigos de cor (ou None).
Quem pinta é o widget `PixelSprite`, que mapeia cada código para a component
class "px--<código>" do jarvis.tcss e usa `orb.to_halfblocks` (2 linhas de
pixel = 1 linha de texto).

Também ficam aqui os "efeitos" de texto reutilizados pelas telas: barras de
bloco (▰▱), sparklines (▁…█), quadros do desligamento CRT e o revelar por
scanline do boot. Tudo determinístico e testável.
"""

# Códigos de cor — cada um vira a component class "px--<código>"
NEON, OCEAN, DEEP, PALE, WHITE, DANGER, WARN, OK, INK, MUTED = (
    "neon", "ocean", "deep", "pale", "white", "danger", "warn", "ok", "ink", "muted",
)
CODES = (NEON, OCEAN, DEEP, PALE, WHITE, DANGER, WARN, OK, INK, MUTED)

# Letra do desenho ASCII → código de cor ('.' = transparente)
_LEGEND = {
    "N": NEON, "O": OCEAN, "D": DEEP, "P": PALE, "W": WHITE,
    "R": DANGER, "Y": WARN, "G": OK, "K": INK, "M": MUTED,
}

_ART = {
    # Alerta do protocolo crítico (ConfirmScreen)
    "alert": (
        ".......RR.......",
        "......RRRR......",
        "......RKKR......",
        ".....RRKKRR.....",
        ".....RRKKRR.....",
        "....RRRKKRRR....",
        "....RRRKKRRR....",
        "...RRRRKKRRRR...",
        "...RRRRRRRRRR...",
        "..RRRRRKKRRRRR..",
        "..RRRRRKKRRRRR..",
        ".RRRRRRRRRRRRRR.",
    ),
    # Mini-orb do dashboard (cor do miolo muda com a carga)
    "mini_orb": (
        "....DDDD....",
        "..DDOOOODD..",
        ".DOONNNNOOD.",
        ".DONNPPNNOD.",
        "DOONPPPPNOOD",
        "DONNPPPPNNOD",
        "DONNPPPPNNOD",
        "DOONNPPNNOOD",
        ".DONNNNNNOD.",
        ".DDOONNOODD.",
        "..DDOOOODD..",
        "....DDDD....",
    ),
    # Núcleo do dashboard /status (16×16, mesma paleta da mini-orb)
    "core_orb": (
        ".....DDDDDD.....",
        "...DDOOOOOODD...",
        "..DOOONNNNOOOD..",
        ".DOONNNNNNNNOOD.",
        ".DONNNPPPPNNNOD.",
        "DOONNPPPPPPNNOOD",
        "DONNPPPPPPPPNNOD",
        "DONNPPPPPPPPNNOD",
        "DONNPPPPPPPPNNOD",
        "DONNPPPPPPPPNNOD",
        "DOONNPPPPPPNNOOD",
        ".DONNNPPPPNNNOD.",
        ".DOONNNNNNNNOOD.",
        "..DOOONNNNOOOD..",
        "...DDOOOOOODD...",
        ".....DDDDDD.....",
    ),
    # Rosto do JARVIS nas caixas de diálogo (Configurações)
    "face": (
        "..DDDD..",
        ".DOOOOD.",
        "DOPOOPOD",
        "DOOOOOOD",
        "DOPPPPOD",
        ".DOOOOD.",
        "..DDDD..",
        "........",
    ),
    # Armadura genérica do easter egg (trim = W, corpo = R)
    "armor": (
        "...WWWW...",
        "..WWWWWW..",
        "..WPPWWP..",
        "..WWWWWW..",
        "...WWWW...",
        ".RRRRRRRR.",
        "RRRRNNRRRR",
        "RR.RNNR.RR",
        "RR.RRRR.RR",
        "RR.RRRR.RR",
        "WW.RRRR.WW",
        "...RR.RR..",
        "...RR.RR..",
        "...RR.RR..",
        "..WWW.WWW.",
        "..WWW.WWW.",
    ),
}

RADAR_SIZE = 11
RADAR_FRAMES = 8


def _parse(rows):
    grid = [[_LEGEND.get(ch) for ch in row] for row in rows]
    if len(grid) % 2:  # meio-bloco junta pares de linhas
        grid.append([None] * len(grid[0]))
    return grid


def sprite(name, recolor=None):
    """Grade do sprite `name`; `recolor` troca códigos ({'neon': 'warn'})."""
    grid = _parse(_ART[name])
    if recolor:
        grid = [[recolor.get(c, c) if c else c for c in row] for row in grid]
    return grid


def names():
    return tuple(_ART)


def radar(n):
    """Quadro n do radar (11×11, 8 quadros): anel fixo + ponteiro girando."""
    n %= RADAR_FRAMES
    c = RADAR_SIZE // 2
    grid = [[None] * RADAR_SIZE for _ in range(RADAR_SIZE)]
    for y in range(RADAR_SIZE):
        for x in range(RADAR_SIZE):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if 4.5 <= d <= 5.4:
                grid[y][x] = DEEP
    # ponteiro: 8 direções (0 = norte, sentido horário)
    dx, dy = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))[n]
    for step in range(1, 5):
        grid[c + dy * step][c + dx * step] = NEON if step == 4 else OCEAN
    grid[c][c] = PALE
    grid.append([None] * RADAR_SIZE)  # par de linhas p/ o meio-bloco
    return grid


# ------------------------------------------------------------------ efeitos

def block_bar(value, width=5, full="▰", empty="▱"):
    """Barra de blocos para 0–100 (ex.: 41 → '▰▰▱▱▱')."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    value = max(0.0, min(100.0, value))
    filled = int(round(value / 100 * width))
    return full * filled + empty * (width - filled)


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values, width=None, top=100.0):
    """Sparkline de uma linha (▁…█). Usa os últimos `width` valores."""
    values = list(values)[-width:] if width else list(values)
    out = []
    for v in values:
        try:
            v = max(0.0, min(float(top), float(v)))
        except (TypeError, ValueError):
            v = 0.0
        out.append(SPARK[min(len(SPARK) - 1, int(v / top * len(SPARK)))])
    if width and len(out) < width:
        out = [" "] * (width - len(out)) + out
    return "".join(out)


def bar_chart(values, width, height, top=100.0):
    """Gráfico de barras de várias linhas (oitavos de bloco), de cima p/ baixo.
    Usa os últimos `width` valores, alinhados à direita."""
    values = list(values)[-width:]
    cols = [0.0] * (width - len(values)) + values
    eighths = []
    for v in cols:
        try:
            v = max(0.0, min(float(top), float(v)))
        except (TypeError, ValueError):
            v = 0.0
        eighths.append(round(v / top * height * 8) if top else 0)
    lines = []
    for row in range(height - 1, -1, -1):  # linha de cima primeiro
        line = []
        for e in eighths:
            fill = e - row * 8
            line.append(" " if fill <= 0 else "█" if fill >= 8 else SPARK[fill - 1])
        lines.append("".join(line))
    return lines


def bar_slots(width, gap=1):
    """Quantas barras de 1 coluna cabem em `width` com `gap` colunas entre elas."""
    return max(1, (max(width, 1) + gap) // (1 + gap))


def spaced_bar_chart(values, width, height, top=100.0, gap=1):
    """Como bar_chart, mas com `gap` colunas vazias entre as barras (visual do
    canvas). Retorna (linhas, valores_mostrados) — os valores alinhados às
    barras (None = barra vazia à esquerda), p/ quem colore barra a barra."""
    slots = bar_slots(width, gap)
    shown = list(values)[-slots:]
    padded = [None] * (slots - len(shown)) + shown
    lines = bar_chart([0 if v is None else v for v in padded], slots, height, top)
    spacer = " " * gap
    return [spacer.join(line) for line in lines], padded


def load_level(value):
    """Faixa de carga p/ cor/rótulo: 'baixa' (<65), 'moderada' (<85), 'alta'."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "baixa"
    return "baixa" if value < 65 else "moderada" if value < 85 else "alta"


CRT_FRAMES = 5


def crt_frames(width, height):
    """Desligamento estilo CRT: 5 quadros (listas de linhas de texto).
    Tela cheia → faixa → linha → linha curta → ponto."""
    width, height = max(width, 3), max(height, 3)
    mid = height // 2
    blank = " " * width

    def canvas(rows):
        lines = [blank] * height
        for y, text in rows.items():
            lines[y] = text.center(width)[:width]
        return lines

    band = max(1, height // 8)
    return [
        ["█" * width] * height,
        canvas({y: "█" * width for y in range(mid - band, mid + band + 1)}),
        canvas({mid: "▀" * width}),
        canvas({mid: "▀" * max(1, width // 6)}),
        canvas({mid: "▪"}),
    ]


def scanline_reveal(lines, n):
    """Primeiras n linhas visíveis; o resto em branco (mesmo tamanho)."""
    n = max(0, min(n, len(lines)))
    return list(lines[:n]) + [" " * len(line) for line in lines[n:]]
