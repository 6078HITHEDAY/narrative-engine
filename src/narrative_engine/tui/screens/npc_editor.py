"""NPC 编辑 Screen。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Input, Label, ListView, ListItem, Select, Static,
)

from narrative_engine.models.state import NPCState
from narrative_engine.tui.state import get_state


class NPCEditorScreen(Screen):
    name = "npc_editor"

    CSS = """
    NPCEditorScreen { padding: 1; }
    #npc-layout { height: 1fr; }
    #npc-list {
        width: 25;
        border: solid $surface-lighten-1;
        margin-right: 1;
    }
    #npc-list ListView { height: 1fr; }
    #npc-form {
        width: 1fr;
        border: solid $primary;
        padding: 1;
    }
    #npc-form Label { margin-top: 1; }
    #npc-form Input { margin-bottom: 1; }
    #npc-form Select { margin-bottom: 1; }
    .btn-row { height: 3; align: left middle; margin-top: 1; }
    """

    MOODS = [
        ("neutral", "neutral"),
        ("happy", "happy"),
        ("sad", "sad"),
        ("angry", "angry"),
        ("excited", "excited"),
        ("calm", "calm"),
        ("peaceful", "peaceful"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("[bold]NPC 编辑[/]", classes="title")
        with Horizontal(id="npc-layout"):
            with Vertical(id="npc-list"):
                yield Label("[bold]NPC 列表[/]")
                yield ListView(id="npc_items")
                with Horizontal(classes="btn-row"):
                    yield Button("添加", id="add_npc_btn", variant="primary")
                    yield Button("删除", id="del_npc_btn")
            with Vertical(id="npc-form"):
                yield Label("[bold]NPC 属性[/]")
                yield Label("ID")
                yield Input(id="npc_id_field", placeholder="npc_id")
                yield Label("名称")
                yield Input(id="npc_name_field", placeholder="NPC 名称")
                yield Label("情绪 (Mood)")
                yield Select(self.MOODS, id="npc_mood_field", value="neutral")
                yield Label("特性 (Traits, 逗号分隔)")
                yield Input(id="npc_traits_field", placeholder="勇敢, 狡猾, 善良")
                yield Label("关系值 (Relationship)")
                yield Input(id="npc_rel_field", placeholder="0", value="0")
                yield Label("预设记忆 (每行一条: content|importance)")
                yield Input(id="npc_memories_field", placeholder="记得玩家的帮助|5")
                with Horizontal(classes="btn-row"):
                    yield Button("保存 NPC", id="save_npc_btn", variant="success")
                    yield Button("写入文件", id="write_file_btn")
                    yield Button("热重载", id="reload_btn")
                yield Static(id="npc-status")

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        state = get_state()
        lst = self.query_one("#npc_items", ListView)
        lst.clear()
        if state.engine:
            for npc_id in sorted(state.engine.npcs):
                npc = state.engine.npcs[npc_id]
                lst.append(ListItem(Label(f"  {npc.name} ({npc.id})")))

    def _get_selected_npc_id(self) -> str | None:
        lst = self.query_one("#npc_items", ListView)
        if lst.index is not None and lst.index < len(lst.children):
            item = lst.children[lst.index]
            if hasattr(item, "get_child"):
                label = item.get_child(Label)
                if label:
                    text = str(label.renderable).strip()
                    return text.split("(")[-1].rstrip(")")
        return None

    def _load_npc_to_form(self, npc: NPCState) -> None:
        self.query_one("#npc_id_field", Input).value = npc.id
        self.query_one("#npc_name_field", Input).value = npc.name
        self.query_one("#npc_mood_field", Select).value = npc.mood
        self.query_one("#npc_traits_field", Input).value = ", ".join(npc.traits)
        self.query_one("#npc_rel_field", Input).value = str(npc.relationship)
        memories = [f"{m.get('content', '')}|{m.get('importance', 0)}" for m in npc.preset_memories]
        self.query_one("#npc_memories_field", Input).value = "; ".join(memories)

    def _read_form(self) -> dict:
        return {
            "id": self.query_one("#npc_id_field", Input).value.strip(),
            "name": self.query_one("#npc_name_field", Input).value.strip(),
            "mood": self.query_one("#npc_mood_field", Select).value,
            "traits": [t.strip() for t in self.query_one("#npc_traits_field", Input).value.split(",") if t.strip()],
            "relationship": float(self.query_one("#npc_rel_field", Input).value or 0),
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
                content = part
                importance = 0
            result.append({"content": content.strip(), "importance": importance})
        return result

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        npc_id = self._get_selected_npc_id()
        if npc_id:
            state = get_state()
            if state.engine and npc_id in state.engine.npcs:
                self._load_npc_to_form(state.engine.npcs[npc_id])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add_npc_btn":
            self._add_npc()
        elif event.button.id == "del_npc_btn":
            self._delete_npc()
        elif event.button.id == "save_npc_btn":
            self._save_npc()
        elif event.button.id == "write_file_btn":
            self._write_to_file()
        elif event.button.id == "reload_btn":
            self._reload_npcs()

    def _add_npc(self) -> None:
        state = get_state()
        if not state.engine:
            self.query_one("#npc-status", Static).update("[red]请先加载故事[/]")
            return
        data = self._read_form()
        if not data["id"]:
            self.query_one("#npc-status", Static).update("[red]NPC ID 不能为空[/]")
            return
        npc = NPCState(**data)
        state.engine._npcs[npc.id] = npc
        self._refresh_list()
        self._load_npc_to_form(npc)
        self.query_one("#npc-status", Static).update(f"[green]NPC '{npc.name}' 已添加（内存中，需写入文件持久化）[/]")

    def _delete_npc(self) -> None:
        npc_id = self._get_selected_npc_id()
        if not npc_id:
            return
        state = get_state()
        if state.engine and npc_id in state.engine._npcs:
            del state.engine._npcs[npc_id]
            self._refresh_list()
            self.query_one("#npc-status", Static).update(f"[green]NPC '{npc_id}' 已删除（需写入文件持久化）[/]")

    def _save_npc(self) -> None:
        state = get_state()
        if not state.engine:
            self.query_one("#npc-status", Static).update("[red]请先加载故事[/]")
            return
        data = self._read_form()
        if not data["id"]:
            self.query_one("#npc-status", Static).update("[red]NPC ID 不能为空[/]")
            return
        npc = NPCState(**data)
        state.engine._npcs[npc.id] = npc
        self._refresh_list()
        self.query_one("#npc-status", Static).update(f"[green]NPC '{npc.name}' 已更新（内存中）[/]")

    def _write_to_file(self) -> None:
        state = get_state()
        if not state.engine or not state.current_story:
            self.query_one("#npc-status", Static).update("[red]请先加载故事[/]")
            return

        import yaml
        from pathlib import Path

        npcs_dict = {}
        for npc in state.engine._npcs.values():
            npcs_dict[npc.id] = {
                "id": npc.id,
                "name": npc.name,
                "mood": npc.mood,
                "traits": npc.traits,
                "relationship": npc.relationship,
                "preset_memories": npc.preset_memories,
            }

        path = Path(state.current_story) / "npcs.yaml"
        content = yaml.dump({"npcs": npcs_dict}, allow_unicode=True, default_flow_style=False, sort_keys=False)
        path.write_text(content, encoding="utf-8")
        self.query_one("#npc-status", Static).update(f"[green]已写入 {path}[/]")

    def _reload_npcs(self) -> None:
        state = get_state()
        if state.engine:
            state.engine.reload_npcs()
            self._refresh_list()
            self.query_one("#npc-status", Static).update("[green]NPC 已从文件热重载[/]")
