"""NPC 编辑面板。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Input, Label, ListView, ListItem, Select, Static,
)

from narrative_engine.models.state import NPCState
from narrative_engine.tui.state import get_state


class _ConfirmDelete(ModalScreen[bool]):
    """删除 NPC 二次确认。"""

    DEFAULT_CSS = """
    _ConfirmDelete { align: center middle; }
    #confirm-box {
        width: 50; height: auto; padding: 1 2;
        border: thick $error; background: $surface;
    }
    #confirm-buttons { height: 3; align: center middle; margin-top: 1; }
    Button { margin: 0 1; }
    """

    def __init__(self, npc_id: str) -> None:
        super().__init__()
        self.npc_id = npc_id

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(f"[bold red]确认删除 NPC '{self.npc_id}'？[/]")
            yield Label("[dim]仅从内存删除，写入文件后才会持久化。[/]")
            with Horizontal(id="confirm-buttons"):
                yield Button("确认删除", id="ok_btn", variant="error")
                yield Button("取消", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok_btn")


class NPCEditorPanel(Horizontal):
    DEFAULT_CSS = """
    NPCEditorPanel { padding: 1; height: 1fr; }
    #npc-list { width: 30; border: solid $surface-lighten-1; margin-right: 1; }
    #npc-list ListView { height: 1fr; }
    #npc-form { width: 1fr; border: solid $primary; padding: 1; }
    #npc-form Label { margin-top: 1; }
    #npc-form Input { margin-bottom: 0; }
    #npc-form Select { margin-bottom: 0; height: 3; }
    .btn-row { height: 3; align: left middle; margin-top: 1; }
    #npc-list .btn-row Button { width: 1fr; min-width: 0; margin: 0 1 0 0; }
    """

    MOODS = [
        ("neutral", "neutral"), ("happy", "happy"), ("sad", "sad"),
        ("angry", "angry"), ("excited", "excited"), ("calm", "calm"),
        ("peaceful", "peaceful"), ("grumpy", "grumpy"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dirty: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="npc-list"):
            yield Label("[bold]NPC 列表[/] [dim](* = 未持久化)[/]")
            yield ListView(id="npc_items")
            with Horizontal(classes="btn-row"):
                yield Button("新增", id="add_npc_btn", variant="primary")
                yield Button("删除", id="del_npc_btn", variant="error")
        with Vertical(id="npc-form"):
            yield Label("[bold]NPC 属性[/]")
            yield Label("ID")
            yield Input(id="npc_id_field", placeholder="snake_case_id")
            yield Label("名称")
            yield Input(id="npc_name_field", placeholder="NPC 名称")
            yield Label("情绪 (Mood)")
            yield Select(self.MOODS, id="npc_mood_field", value="neutral")
            yield Label("特性 (Traits, 逗号分隔)")
            yield Input(id="npc_traits_field", placeholder="勇敢, 狡猾, 善良")
            yield Label("关系值 (Relationship)")
            yield Input(id="npc_rel_field", placeholder="0", value="0")
            yield Label("预设记忆 (用 ; 分隔多条; 每条 content|importance)")
            yield Input(id="npc_memories_field", placeholder="记得玩家的帮助|5; 不信任陌生人|3")
            with Horizontal(classes="btn-row"):
                yield Button("保存到内存", id="save_npc_btn", variant="success")
                yield Button("写入文件", id="write_file_btn", variant="primary")
                yield Button("热重载", id="reload_btn")
            yield Static("", id="npc-status")

    async def on_show(self) -> None:
        await self._refresh_list()

    @work(thread=False)
    async def _refresh_list_worker(self) -> None:
        await self._refresh_list()

    async def _refresh_list(self) -> None:
        state = get_state()
        lst = self.query_one("#npc_items", ListView)
        await lst.clear()
        if state.engine:
            for npc_id in sorted(state.engine.npcs):
                npc = state.engine.npcs[npc_id]
                mark = "*" if npc_id in self._dirty else " "
                lst.append(ListItem(Label(f"{mark} {npc.name} ({npc.id})"), id=f"npc-{npc_id}"))

    def _selected_id(self) -> str | None:
        lst = self.query_one("#npc_items", ListView)
        item = lst.highlighted_child
        if item and item.id and item.id.startswith("npc-"):
            return item.id.removeprefix("npc-")
        return None

    def _load_npc_to_form(self, npc: NPCState) -> None:
        self.query_one("#npc_id_field", Input).value = npc.id
        self.query_one("#npc_name_field", Input).value = npc.name
        try:
            self.query_one("#npc_mood_field", Select).value = npc.mood
        except Exception:
            pass
        self.query_one("#npc_traits_field", Input).value = ", ".join(npc.traits)
        self.query_one("#npc_rel_field", Input).value = str(npc.relationship)
        memories = [f"{m.get('content', '')}|{m.get('importance', 0)}" for m in npc.preset_memories]
        self.query_one("#npc_memories_field", Input).value = "; ".join(memories)

    def _read_form(self) -> dict:
        try:
            relationship = float(self.query_one("#npc_rel_field", Input).value or 0)
        except ValueError:
            relationship = 0.0
        return {
            "id": self.query_one("#npc_id_field", Input).value.strip(),
            "name": self.query_one("#npc_name_field", Input).value.strip(),
            "mood": self.query_one("#npc_mood_field", Select).value,
            "traits": [t.strip() for t in self.query_one("#npc_traits_field", Input).value.split(",") if t.strip()],
            "relationship": relationship,
            "preset_memories": self._parse_memories(),
        }

    def _parse_memories(self) -> list[dict]:
        raw = self.query_one("#npc_memories_field", Input).value
        result = []
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            if "|" in part:
                content, imp = part.rsplit("|", 1)
                try:
                    importance = int(imp.strip())
                except ValueError:
                    importance = 0
            else:
                content, importance = part, 0
            result.append({"content": content.strip(), "importance": importance})
        return result

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        npc_id = self._selected_id()
        if npc_id:
            state = get_state()
            if npc_id in state.engine.npcs:
                self._load_npc_to_form(state.engine.npcs[npc_id])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add_npc_btn":
            self._save_npc(announce_added=True)
        elif event.button.id == "del_npc_btn":
            self._delete_npc()
        elif event.button.id == "save_npc_btn":
            self._save_npc()
        elif event.button.id == "write_file_btn":
            self._write_to_file()
        elif event.button.id == "reload_btn":
            self._reload_npcs()

    def _save_npc(self, announce_added: bool = False) -> None:
        state = get_state()
        data = self._read_form()
        if not data["id"]:
            self._set_status("[red]NPC ID 不能为空[/]")
            return
        npc = NPCState(**data)
        was_new = npc.id not in state.engine.npcs
        state.engine.set_npc(npc.id, npc)
        self._dirty.add(npc.id)
        self._refresh_list_worker()
        verb = "新增" if (announce_added or was_new) else "更新"
        self._set_status(f"[green]NPC '{npc.name}' 已{verb}（内存中，需写入文件）[/]")

    def _delete_npc(self) -> None:
        npc_id = self._selected_id()
        if not npc_id:
            self._set_status("[yellow]请先选择 NPC[/]")
            return

        def after(confirmed: bool | None) -> None:
            if not confirmed:
                return
            state = get_state()
            if state.engine.delete_npc(npc_id):
                self._dirty.add(npc_id)
                self._refresh_list_worker()
                self._set_status(f"[green]NPC '{npc_id}' 已删除（需写入文件持久化）[/]")

        self.app.push_screen(_ConfirmDelete(npc_id), after)

    def _write_to_file(self) -> None:
        state = get_state()
        if not state.current_story:
            self._set_status("[red]请先加载故事[/]")
            return
        import yaml
        from pathlib import Path

        npcs_dict = {}
        for npc in state.engine.npcs.values():
            npcs_dict[npc.id] = {
                "id": npc.id, "name": npc.name, "mood": npc.mood,
                "traits": npc.traits, "relationship": npc.relationship,
                "preset_memories": npc.preset_memories,
            }
        path = Path(state.current_story) / "npcs.yaml"
        content = yaml.dump({"npcs": npcs_dict}, allow_unicode=True, default_flow_style=False, sort_keys=False)
        path.write_text(content, encoding="utf-8")
        self._dirty.clear()
        self._refresh_list_worker()
        self._set_status(f"[green]已写入 {path}[/]")

    def _reload_npcs(self) -> None:
        state = get_state()
        if state.engine:
            state.engine.reload_npcs()
            self._dirty.clear()
            self._refresh_list_worker()
            self._set_status("[green]NPC 已从文件热重载[/]")

    def _set_status(self, msg: str) -> None:
        self.query_one("#npc-status", Static).update(msg)
