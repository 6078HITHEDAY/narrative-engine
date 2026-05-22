"""故事管理 Screen。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Input, Label, ListView, ListItem, Static,
)

from narrative_engine.tui.state import get_state


class StoryManagerScreen(Screen):
    name = "story_manager"

    CSS = """
    StoryManagerScreen { padding: 1; }
    #story-list {
        height: 12;
        border: solid $surface-lighten-1;
        margin-bottom: 1;
    }
    #story-info {
        height: auto;
        margin-bottom: 1;
    }
    .row { height: 3; align: left middle; }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold]故事管理[/]", classes="title")
        with Horizontal(classes="row"):
            yield Input(placeholder="stories/seaside_town", id="story_path")
            yield Button("加载故事", id="load_btn", variant="primary")
            yield Button("新建故事", id="new_btn")
        yield Static("", id="story-info")
        yield Label("章节列表:")
        yield ListView(id="chapter_list")
        with Horizontal(classes="row"):
            yield Button("刷新信息", id="refresh_btn")
            yield Button("热重载 NPC", id="reload_npc_btn")

    @work(thread=False)
    async def _load_story(self, path: str) -> None:
        state = get_state()
        try:
            await state.engine.load_story_async(path)
            state.current_story = path
            self._refresh_info()
            if hasattr(self.app, "update_status"):
                self.app.update_status()
        except Exception as e:
            self.query_one("#story-info", Static).update(f"[red]加载失败: {e}[/]")

    def _refresh_info(self) -> None:
        state = get_state()
        engine = state.engine
        if not engine or not state.current_story:
            return

        info = self.query_one("#story-info", Static)
        info.update(
            f"标题: [bold]{engine.story_title}[/] | "
            f"当前章节: [bold]{engine.current_chapter}[/] | "
            f"NPC 数: {len(engine.npcs)}"
        )

        chapter_list = self.query_one("#chapter_list", ListView)
        chapter_list.clear()
        for ch in engine.list_chapters():
            mark = " *" if ch == engine.current_chapter else ""
            chapter_list.append(ListItem(Label(f"  {ch}{mark}")))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "load_btn":
            path = self.query_one("#story_path", Input).value.strip()
            if path:
                self._load_story(path)
        elif event.button.id == "refresh_btn":
            self._refresh_info()
        elif event.button.id == "reload_npc_btn":
            self._reload_npcs()
        elif event.button.id == "new_btn":
            self._new_story()

    @work(thread=False)
    async def _reload_npcs(self) -> None:
        state = get_state()
        if state.engine:
            state.engine.reload_npcs()
            self._refresh_info()

    def _new_story(self) -> None:
        from pathlib import Path
        import yaml

        path = self.query_one("#story_path", Input).value.strip()
        if not path:
            path = "stories/new_story"
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        (p / "chapters").mkdir(exist_ok=True)

        story_yaml = p / "story.yaml"
        if not story_yaml.exists():
            story_yaml.write_text(
                "title: 新故事\n"
                "default_world:\n  setting: 一个新的世界\n  tone: neutral\n"
                "default_fallback:\n  dialogue:\n    - ……\n"
                "  event:\n    - 什么都没有发生\n"
                "  description:\n    - 一切如常\n",
                encoding="utf-8",
            )

        npcs_yaml = p / "npcs.yaml"
        if not npcs_yaml.exists():
            npcs_yaml.write_text(
                "npcs:\n  narrator:\n    id: narrator\n    name: 旁白\n"
                "    mood: neutral\n    traits: []\n    relationship: 0\n"
                "    preset_memories: []\n",
                encoding="utf-8",
            )

        chapter_yaml = p / "chapters" / "chapter_1.yaml"
        if not chapter_yaml.exists():
            chapter_yaml.write_text(
                "title: 第一章\n"
                "world:\n  setting: 一个新的世界\n  tone: neutral\n"
                "beats: []\n"
                "fallback:\n  dialogue:\n    - ……\n"
                "  event:\n    - 什么都没有发生\n"
                "  description:\n    - 一切如常\n",
                encoding="utf-8",
            )

        self._load_story(str(p))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        state = get_state()
        item = event.item
        if item and hasattr(item, "get_child"):
            label = item.get_child(Label)
            if label:
                ch = str(label.renderable).strip().rstrip(" *")
                if ch in state.engine.list_chapters():
                    state.engine.switch_chapter(ch)
                    self._refresh_info()
