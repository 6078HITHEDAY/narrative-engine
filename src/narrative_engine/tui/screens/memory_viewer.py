"""记忆查看 Screen。"""

from __future__ import annotations

import json
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Label, ListView, ListItem, Select, Static,
)

from narrative_engine.tui.state import get_state


class MemoryViewerScreen(Screen):
    name = "memory_viewer"

    CSS = """
    MemoryViewerScreen { padding: 1; }
    #mem-layout { height: 1fr; }
    #mem-sidebar {
        width: 35;
        border: solid $surface-lighten-1;
        margin-right: 1;
    }
    #mem-sidebar ListView { height: 1fr; }
    #mem-main {
        width: 1fr;
    }
    #mem-main RichLog {
        height: 1fr;
        border: solid $primary;
    }
    #mem-detail {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
        overflow-y: auto;
    }
    .btn-row { height: 3; align: left middle; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]记忆查看[/]", classes="title")
        with Horizontal(id="mem-layout"):
            with Vertical(id="mem-sidebar"):
                yield Label("[bold]NPC 列表[/]")
                yield ListView(id="mem_npc_list")
                with Horizontal(classes="btn-row"):
                    yield Button("清空记忆", id="clear_mem_btn")
                    yield Button("导出记忆", id="export_mem_btn")
            with Vertical(id="mem-main"):
                yield Label("[bold]长期记忆[/]")
                yield Static("(选择 NPC 查看)", id="long_term_display")
                yield Label("[bold]短期会话历史[/]")
                yield Static("(选择 NPC 查看)", id="session_display")

    def on_mount(self) -> None:
        self._refresh_npc_list()

    def _refresh_npc_list(self) -> None:
        state = get_state()
        lst = self.query_one("#mem_npc_list", ListView)
        lst.clear()
        for npc_id in sorted(state.engine.npcs):
            npc = state.engine.npcs[npc_id]
            lst.append(ListItem(Label(f"  {npc.name} ({npc.id})")))
        if state.engine.memory:
            lst.append(ListItem(Label("  [全部记忆]")))

    def _get_selected_npc_id(self) -> str | None:
        lst = self.query_one("#mem_npc_list", ListView)
        if lst.index is not None and lst.index < len(lst.children):
            item = lst.children[lst.index]
            if hasattr(item, "get_child"):
                label = item.get_child(Label)
                if label:
                    text = str(label.renderable).strip()
                    if text == "[全部记忆]":
                        return None
                    return text.split("(")[-1].rstrip(")")
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        state = get_state()
        if not state.engine.memory:
            return

        npc_id = self._get_selected_npc_id()

        # 长期记忆
        mem = state.engine.memory
        if npc_id:
            records = mem.recall(npc_id, limit=50)
        else:
            records = []
            for rlist in mem._memories.values():
                records.extend(rlist)
            records.sort(key=lambda r: (r.importance, r.timestamp), reverse=True)

        long_text = self._build_long_term_text(records)
        self.query_one("#long_term_display", Static).update(long_text)

        # 短期会话
        if npc_id:
            turns = [t for t in mem._turns if t.npc_id == npc_id]
        else:
            turns = list(mem._turns)
        session_text = self._build_session_text(turns)
        self.query_one("#session_display", Static).update(session_text)

    @staticmethod
    def _build_long_term_text(records: list) -> str:
        if not records:
            return "[dim](无记录)[/]"
        lines = []
        for r in records:
            ts = datetime.fromtimestamp(r.timestamp).strftime("%m-%d %H:%M")
            stars = "★" * min(r.importance, 5)
            lines.append(f"[bold]{r.npc_id}[/] [{r.kind}] {stars} [dim]{ts}[/]")
            lines.append(f"  {r.content}")
        return "\n".join(lines)

    @staticmethod
    def _build_session_text(turns: list) -> str:
        if not turns:
            return "[dim](无记录)[/]"
        lines = []
        for t in turns[-20:]:
            lines.append(f"[bold]#{t.turn}[/] [{t.npc_id or '-'}] [dim]{t.kind}[/]")
            lines.append(f"  玩家: {t.player_context[:80]}")
            lines.append(f"  引擎: {t.engine_response[:120]}")
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "clear_mem_btn":
            self._clear_memories()
        elif event.button.id == "export_mem_btn":
            self._export_memories()

    def _clear_memories(self) -> None:
        state = get_state()
        if state.engine.memory:
            state.engine.memory.clear()
            self.query_one("#long_term_display", Static).update("[green]记忆已清空[/]")
            self.query_one("#session_display", Static).update("[green]会话历史已清空[/]")

    def _export_memories(self) -> None:
        state = get_state()
        if not state.engine.memory:
            return

        mem = state.engine.memory
        data = {
            "exported_at": datetime.now().isoformat(),
            "long_term": {
                npc_id: [r.model_dump() for r in records]
                for npc_id, records in mem._memories.items()
            },
            "session_turns": [t.model_dump() for t in mem._turns],
        }

        path = "/tmp/narrative_memories_export.json"
        import json
        path_obj = __import__("pathlib").Path(path)
        path_obj.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.query_one("#long_term_display", Static).update(f"[green]已导出到 {path}[/]")
