"""/vault — memória de longo prazo no Obsidian (canvas: "7 · Memória / Vault").

Árvore do vault (carregada pasta a pasta via REST), busca com o radar
pixel-art girando SÓ enquanto a busca roda, prévia em Markdown da nota e o
botão "usar no chat", que devolve a nota para ir junto da próxima mensagem.
Toda I/O com o Obsidian roda em worker de thread.
"""
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, OptionList, Tree
from textual.widgets.option_list import Option

from core import log
from frontend import sprites
from frontend.screens.base import JarvisScreen
from frontend.widgets import JarvisMarkdown, PixelSprite

PREVIEW_MAX = 6000  # caracteres da nota na prévia


def _client():
    from core.obsidian import obsidian
    return obsidian


class VaultScreen(JarvisScreen):
    BADGE = "MEMÓRIA"
    HEADLINE = "Vault Obsidian"

    BINDINGS = [
        Binding("escape", "close", "Voltar"),
        Binding("ctrl+f", "focus_search", "Buscar"),
        Binding("ctrl+u", "use", "Usar no chat"),
    ]

    def __init__(self, query="", **kwargs):
        super().__init__(**kwargs)
        self._initial_query = query
        self._note = None  # (caminho, conteúdo) em prévia

    def body(self) -> ComposeResult:
        with Horizontal(id="vault-search"):
            yield Label("busca ›", id="vault-search-label")
            yield Input(value=self._initial_query, placeholder="termo para buscar no vault…", id="vault-q")
            yield Label("", id="vault-count", classes="hint")
        with Horizontal(id="vault-body"):
            tree = Tree("vault", id="vault-tree", data="")
            tree.show_root = False
            yield tree
            with Vertical(id="vault-preview"):
                yield Label("selecione uma nota", id="vault-path", classes="hint")
                yield JarvisMarkdown("", id="vault-md")
                with Horizontal(id="vault-actions"):
                    yield Button("▶ usar no chat", id="vault-use", disabled=True)
            with Vertical(id="vault-radar"):
                yield Label("radar RAG", classes="hint")
                yield PixelSprite([sprites.radar(n) for n in range(sprites.RADAR_FRAMES)], id="radar")
                yield Label("parado", id="radar-state", classes="hint")
                yield OptionList(id="vault-results")

    def on_mount(self):
        super().on_mount()
        self._load_dir(self.query_one("#vault-tree", Tree).root, "")
        if self._initial_query:
            self._search(self._initial_query)
        else:
            self.query_one("#vault-q", Input).focus()

    # ---------------------------------------------------------------- árvore
    @work(thread=True, group="vault-tree")
    def _load_dir(self, node, path):
        try:
            items = _client().list_dir(path)
        except Exception as e:
            log.warning(f"Vault: falha ao listar '{path}': {e}")
            items = None
        self.app.call_from_thread(self._fill_dir, node, path, items)

    def _fill_dir(self, node, path, items):
        node.remove_children()
        if items is None:
            node.add_leaf("⚠ Obsidian inacessível (plugin Local REST API?)", data=None)
            self.set_info("vault offline")
            return
        for name in items:
            full = f"{path}{name}"
            if name.endswith("/"):
                node.add(name, data=full, allow_expand=True)  # a Tree já desenha a seta
            elif name.lower().endswith(".md"):
                node.add_leaf(name, data=full)
        if node.is_root:
            self.set_info(f"{len(items)} itens na raiz")

    def on_tree_node_expanded(self, event: Tree.NodeExpanded):
        path = event.node.data
        if path and path.endswith("/") and not event.node.children:
            event.node.add_leaf("carregando…", data=None)
            self._load_dir(event.node, path)

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        path = event.node.data
        if path and not path.endswith("/"):
            self._open(path)

    # ----------------------------------------------------------------- busca
    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "vault-q" and event.value.strip():
            self._search(event.value.strip())

    def _set_radar(self, searching):
        self.query_one("#radar", PixelSprite).animated = searching
        self.query_one("#radar-state", Label).update("varrendo…" if searching else "parado")

    def _search(self, query):
        self._set_radar(True)
        self._run_search(query)

    @work(thread=True, exclusive=True, group="vault-search")
    def _run_search(self, query):
        try:
            results = _client().search_results(query)
        except Exception as e:
            log.warning(f"Vault: busca falhou: {e}")
            results = []
        self.app.call_from_thread(self._show_results, results)

    def _show_results(self, results):
        self._set_radar(False)
        options = self.query_one("#vault-results", OptionList)
        options.clear_options()
        for r in results:
            name = r["filename"].rsplit("/", 1)[-1].removesuffix(".md")
            options.add_option(Option(f"{r['score']:.2f} {name[:22]}", id=r["filename"]))
        self.query_one("#vault-count", Label).update(f"{len(results)} resultados")
        if results:
            self._open(results[0]["filename"])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if event.option.id:
            self._open(event.option.id)

    # ---------------------------------------------------------------- prévia
    def _open(self, path):
        self.query_one("#vault-path", Label).update(path)
        self._read_note(path)

    @work(thread=True, exclusive=True, group="vault-read")
    def _read_note(self, path):
        try:
            content = _client().get_file(path)
        except Exception as e:
            log.warning(f"Vault: falha ao ler '{path}': {e}")
            content = None
        self.app.call_from_thread(self._show_note, path, content)

    def _show_note(self, path, content):
        md = self.query_one("#vault-md", JarvisMarkdown)
        if content is None:
            self._note = None
            md.update("_Não consegui ler esta nota._")
        else:
            self._note = (path, content)
            md.update(content[:PREVIEW_MAX] + ("\n\n_(prévia cortada)_" if len(content) > PREVIEW_MAX else ""))
        self.query_one("#vault-use", Button).disabled = self._note is None

    # ---------------------------------------------------------------- ações
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "vault-use":
            event.stop()
            self.action_use()

    def action_use(self):
        if self._note:
            path, content = self._note
            self.dismiss({"path": path, "content": content})

    def action_focus_search(self):
        self.query_one("#vault-q", Input).focus()
