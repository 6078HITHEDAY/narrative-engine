"""记忆查看面板。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Label, ListView, ListItem, Static,
)

from narrative_engine.tui.state import get_state


class MemoryViewerPanel(Vertical):
    DEFAULT_CSS = """
    MemoryViewerPanel { padding: 1; height: 1fr; }
    #mem-layout { height: 1fr; }
    #mem-sidebar { width: 35; border: solid $surface-lighten-1; margin-right: 1; }
    #mem-sidebar ListView { height: 1fr; }
    #mem-main { width: 1fr; }
    #long-display, #session-display {
        height: 1fr; border: solid $primary; padding: 0 1;
        overflow-y: auto;
    }
    .btn-row { height: 3; align: left middle; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]记忆查看[/]")
        with Horizontal(id="mem-layout"):
            with Vertical(id="mem-sidebar"):
                yield Label("[bold]NPC 列表[/]")
                yield ListView(id="mem_npc_list")
                with Horizontal(classes="btn-row"):
                    yield Button("刷新", id="refresh_mem_btn")
                    yield Button("清空记忆", id="clear_mem_btn", variant="error")
                    yield Button("导出", id="export_mem_btn")
            with Vertical(id="mem-main"):
                yield Label("[bold]长期记忆[/]")
                yield Static("(选择 NPC 查看)", id="long-display")
                yield Label("[bold]短期会话历史[/]")
                yield Static("(选择 NPC 查看)", id="session-display")

    async def on_show(self) -> None:
        await self._refresh_npc_list()

    @work(thread=False)
    async def _refresh_npc_list_worker(self) -> None:
        await self._refresh_npc_list()

    async def _refresh_npc_list(self) -> None:
        state = get_state()
        lst = self.query_one("#mem_npc_list", ListView)
        await lst.clear()
        if state.engine:
            for npc_id in sorted(state.engine.npcs):
                npc = state.engine.npcs[npc_id]
                lst.append(ListItem(Label(f"  {npc.name} ({npc.id})"), id=f"mem-{npc_id}"))
        if state.engine and state.engine.memory:
            lst.append(ListItem(Label("  ★ 全部记忆"), id="mem-__all__"))

    def _selected_npc_id(self) -> str | None:
        lst = self.query_one("#mem_npc_list", ListView)
        item = lst.highlighted_child
        if not item or not item.id or not item.id.startswith("mem-"):
            return None
        rest = item.id.removeprefix("mem-")
        return None if rest == "__all__" else rest

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        state = get_state()
        if not state.engine or not state.engine.memory:
            return
        mem = state.engine.memory
        npc_id = self._selected_npc_id()

        records = mem.list_records(npc_id)
        self.query_one("#long-display", Static).update(self._build_long_text(records))

        turns = mem.list_turns(npc_id)
        self.query_one("#session-display", Static).update(self._build_session_text(turns))

    @staticmethod
    def _build_long_text(records: list) -> str:
        if not records:
            return "[dim](无记录)[/]"
        lines = []
        for r in records:
            ts = datetime.fromtimestamp(r.timestamp).strftime("%m-%d %H:%M")
            stars = "★" * min(max(r.importance, 0), 5)
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
        if event.button.id == "refresh_mem_btn":
            self._refresh_npc_list_worker()
        elif event.button.id == "clear_mem_btn":
            self._clear_memories()
        elif event.button.id == "export_mem_btn":
            self._export_memories()

    def _clear_memories(self) -> None:
        state = get_state()
        if state.engine and state.engine.memory:
            state.engine.memory.clear()
            self.query_one("#long-display", Static).update("[green]记忆已清空[/]")
            self.query_one("#session-display", Static).update("[green]会话历史已清空[/]")

    def _export_memories(self) -> None:
        state = get_state()
        if not state.engine or not state.engine.memory:
            return
        mem = state.engine.memory
        data = {
            "exported_at": datetime.now().isoformat(),
            "long_term": {
                npc_id: [r.model_dump() for r in mem.list_records(npc_id)]
                for npc_id in mem.list_npc_ids()
            },
            "session_turns": [t.model_dump() for t in mem.list_turns()],
        }
        path = Path.home() / "narrative_engine_export.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.query_one("#long-display", Static).update(f"[green]已导出到 {path}[/]")
