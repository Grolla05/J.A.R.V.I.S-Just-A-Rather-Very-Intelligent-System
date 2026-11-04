"""Orb pixel-art do Copilot (16×16) — lógica pura, sem Textual.

Cada pixel é um código de cor (ou None); quem pinta é o widget `JarvisOrb`,
que mapeia o código para uma component class do jarvis.tcss.

Estados (canvas "JARVIS TUI"):
- ouvindo     → bola azul com anel branco inteiro, parado (1 quadro);
- pensando    → tudo branco, pulsando em degraus (4 quadros: 0,1,2,1);
- respondendo → bola azul, uma falha de 2 oitavos percorre o anel (8 quadros).

No terminal, 2 linhas de pixel viram 1 linha de texto com meio-bloco (▀ ▄ █):
16 colunas × 8 linhas, com pixels quadrados.
"""
import math

STATES = ("ouvindo", "pensando", "respondendo")
STATE_LABEL = {"ouvindo": "ouvindo você", "pensando": "pensando…", "respondendo": "respondendo"}

SIZE = 16
OCTANTS = 8
GAP = 2  # oitavos apagados no anel enquanto responde

# Códigos de cor — cada um vira a component class "orb--<código>"
RING, RING_DIM, CORE, SHADE, HL, WHITE, WHITE_DIM = (
    "ring", "ring-dim", "core", "shade", "hl", "white", "white-dim",
)
CODES = (RING, RING_DIM, CORE, SHADE, HL, WHITE, WHITE_DIM)

# R anel · C bola · H reflexo (a sombra é derivada da posição)
_SPRITE = (
    ".....RRRRRR.....",
    "...RR......RR...",
    "..R..........R..",
    ".R....CCCC....R.",
    ".R...CCCCCC...R.",
    "R...CHHCCCCC...R",
    "R..CCHHCCCCCC..R",
    "R..CCCCCCCCCC..R",
    "R..CCCCCCCCCC..R",
    "R..CCCCCCCCCC..R",
    "R...CCCCCCCC...R",
    ".R...CCCCCC...R.",
    ".R....CCCC....R.",
    "..R..........R..",
    "...RR......RR...",
    ".....RRRRRR.....",
)


def _octant(x, y):
    """Oitavo do anel (0 = topo, sentido horário)."""
    c = SIZE / 2
    angle = (math.degrees(math.atan2(y + 0.5 - c, x + 0.5 - c)) + 90) % 360
    return int(angle // (360 / OCTANTS))


def _base():
    """Grade-base: cada célula é (código, oitavo|None) ou None."""
    c = SIZE / 2
    grid = []
    for y, row in enumerate(_SPRITE):
        line = []
        for x, ch in enumerate(row):
            if ch == "R":
                line.append((RING, _octant(x, y)))
            elif ch == "H":
                line.append((HL, None))
            elif ch == "C":
                # sombra na borda de baixo/direita da bola dá volume
                rim = math.hypot(x + 0.5 - c, y + 0.5 - c) > 3.2
                line.append((SHADE if x + y >= 19 and rim else CORE, None))
            else:
                line.append(None)
        grid.append(line)
    return grid


BASE = _base()


def frame_count(state):
    return {"ouvindo": 1, "pensando": 4, "respondendo": OCTANTS}.get(state, 1)


def dimmed_octants(n):
    """Oitavos apagados no quadro n do estado 'respondendo'."""
    return {(n + i) % OCTANTS for i in range(GAP)}


def frame(state, n=0):
    """Grade 16×16 de códigos (ou None) para o quadro n do estado."""
    n %= frame_count(state)
    if state == "respondendo":
        off = dimmed_octants(n)
        return [[None if cell is None else
                 (RING_DIM if cell[0] == RING and cell[1] in off else cell[0])
                 for cell in row] for row in BASE]
    if state == "pensando":
        step = (0, 1, 2, 1)[n]  # vai e volta, em degraus
        out = []
        for row in BASE:
            line = []
            for cell in row:
                if cell is None:
                    line.append(None)
                elif cell[0] == RING:
                    line.append((WHITE, WHITE_DIM, None)[step])
                else:
                    line.append(WHITE if step < 2 else WHITE_DIM)
            out.append(line)
        return out
    return [[None if cell is None else cell[0] for cell in row] for row in BASE]


def to_halfblocks(grid):
    """Junta pares de linhas: [(char, cor_de_cima, cor_de_baixo), ...] por linha.
    '▀' pinta a metade de cima com a cor da frente e a de baixo com o fundo."""
    rows = []
    for y in range(0, len(grid), 2):
        top_row, bottom_row = grid[y], grid[y + 1]
        line = []
        for top, bottom in zip(top_row, bottom_row):
            if top is None and bottom is None:
                line.append((" ", None, None))
            elif top == bottom:
                line.append(("█", top, None))
            elif bottom is None:
                line.append(("▀", top, None))
            elif top is None:
                line.append(("▄", bottom, None))
            else:
                line.append(("▀", top, bottom))
        rows.append(line)
    return rows
