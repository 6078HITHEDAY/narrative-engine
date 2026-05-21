"""Narrative Engine TUI — 主应用。"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, ListView, ListItem, Label, Static

from narrative_engine.tui.screens.api_config import APIConfigScreen
from narrative_engine.tui.screens.story_manager import StoryManagerScreen
from narrative_engine.tui.screens.npc_editor import NPCEditorScreen
from narrative_engine.tui.screens.playground import PlaygroundScreen
from narrative_engine.tui.screens.memory_viewer import MemoryViewerScreen
from narrative_engine.tui.state import get_state


class NavLabel(Static):
    """导航标签组件。"""


class ContentArea(Vertical):
    """右侧内容区域。"""


class StatusBar(Static):
    """底部状态栏。"""

    def update_status(self) -> None:
        state = get_state()
        story = state.current_story or "未加载"
        api = "Ready" if state.api_ready else "未配置"
        self.update(f"API: {api} | Story: {story} | Storage: {state.storage_mode}")


class NarrativeTUI(App):
    CSS = """
    Horizontal { height: 1fr; }
    #sidebar {
        width: 20;
        border: solid $primary;
        background: $surface;
    }
    #sidebar ListView {
        height: 1fr;
    }
    #content {
        width: 1fr;
        padding: 1 2;
    }
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    NavLabel {
        padding: 0 1;
        height: 1;
        background: $primary-darken-2;
        color: $text;
        text-style: bold;
    }
    """

    TITLE = "Narrative Engine TUI"
    SUB_TITLE = "v0.1.0"

    BINDINGS = [
        ("q", "quit", "退出"),
        ("1", "switch_to('api')", "API配置"),
        ("2", "switch_to('story')", "故事管理"),
        ("3", "switch_to('npc')", "NPC编辑"),
        ("4", "switch_to('play')", "交互测试"),
        ("5", "switch_to('memory')", "记忆查看"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatusBar("API: 未配置 | Story: 未加载 | Storage: memory")
        with Horizontal():
            with Vertical(id="sidebar"):
                yield NavLabel(" 导航")
                yield ListView(
                    ListItem(Label("  API 配置")),
                    ListItem(Label("  故事管理")),
                    ListItem(Label("  NPC 编辑")),
                    ListItem(Label("  交互测试")),
                    ListItem(Label("  记忆查看")),
                )
            yield ContentArea(id="content")

    def on_mount(self) -> None:
        self.install_screen(APIConfigScreen(), name="api_config")
        self.install_screen(StoryManagerScreen(), name="story_manager")
        self.install_screen(NPCEditorScreen(), name="npc_editor")
        self.install_screen(PlaygroundScreen(), name="playground")
        self.install_screen(MemoryViewerScreen(), name="memory_viewer")
        self.push_screen("api_config")

    def action_switch_to(self, screen: str) -> None:
        screens = {
            "api": "api_config",
            "story": "story_manager",
            "npc": "npc_editor",
            "play": "playground",
            "memory": "memory_viewer",
        }
        name = screens.get(screen)
        if name:
            self.switch_screen(name)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.item_index if hasattr(event, "item_index") else 0
        names = ["api_config", "story_manager", "npc_editor", "playground", "memory_viewer"]
        if 0 <= idx < len(names):
            self.switch_screen(names[idx])

    def update_status(self) -> None:
        bar = self.query_one(StatusBar)
        bar.update_status()
