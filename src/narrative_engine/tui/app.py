"""Narrative Engine TUI — 主应用。"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane

from narrative_engine.tui.panels import (
    APIConfigPanel,
    MemoryViewerPanel,
    NPCEditorPanel,
    PlaygroundPanel,
    StoryManagerPanel,
)
from narrative_engine.tui.state import get_state


class StatusBar(Static):
    """底部状态栏，监听全局 state 变化。"""

    api_state: reactive[str] = reactive("未配置")
    story_state: reactive[str] = reactive("未加载")
    storage_state: reactive[str] = reactive("memory")

    def render(self) -> str:
        return (
            f"API: {self.api_state} | "
            f"Story: {self.story_state} | "
            f"Storage: {self.storage_state}"
        )

    def refresh_from_state(self) -> None:
        state = get_state()
        self.api_state = "Ready" if state.api_ready else "未配置"
        self.story_state = state.current_story or "未加载"
        self.storage_state = state.storage_mode


def refresh_status_bar(app: App) -> None:
    """供各 panel 调用 — 把全局 state 推到 StatusBar。"""
    try:
        bar = app.query_one(StatusBar)
    except Exception:
        return
    bar.refresh_from_state()


class NarrativeTUI(App):
    CSS = """
    Screen { layout: vertical; }
    TabbedContent { height: 1fr; }
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    TITLE = "Narrative Engine TUI"
    SUB_TITLE = "v0.1.0"

    BINDINGS = [
        ("q", "quit", "退出"),
        ("1", "show_tab('api')", "API"),
        ("2", "show_tab('story')", "故事"),
        ("3", "show_tab('npc')", "NPC"),
        ("4", "show_tab('play')", "互动"),
        ("5", "show_tab('memory')", "记忆"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="api"):
            with TabPane("API 配置", id="api"):
                yield APIConfigPanel()
            with TabPane("故事管理", id="story"):
                yield StoryManagerPanel()
            with TabPane("NPC 编辑", id="npc"):
                yield NPCEditorPanel()
            with TabPane("交互测试", id="play"):
                yield PlaygroundPanel()
            with TabPane("记忆查看", id="memory"):
                yield MemoryViewerPanel()
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        refresh_status_bar(self)

    def action_show_tab(self, tab: str) -> None:
        try:
            self.query_one(TabbedContent).active = tab
        except Exception:
            pass


def run() -> None:
    NarrativeTUI().run()


if __name__ == "__main__":
    run()
