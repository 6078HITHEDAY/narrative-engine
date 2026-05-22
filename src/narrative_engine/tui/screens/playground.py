"""交互测试 Screen — 流式/非流式叙事生成。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Input, Label, Select, Static, Switch, RichLog,
)

from narrative_engine import GameState, WorldState, NPCState, NarrativeOutput
from narrative_engine.tui.state import get_state
from narrative_engine.tui.widgets.streaming_output import StreamingOutput


class PlaygroundScreen(Screen):
    name = "playground"

    CSS = """
    PlaygroundScreen { padding: 1; }
    #play-input {
        height: auto;
        border: solid $surface-lighten-1;
        padding: 1;
        margin-bottom: 1;
    }
    #play-input Label { margin-top: 1; }
    .row { height: 3; align: left middle; }
    #play-output {
        height: 1fr;
        border: solid $primary;
    }
    #history-log {
        height: 12;
        border: solid $surface-lighten-1;
        margin-top: 1;
    }
    StreamingOutput { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="play-input"):
            yield Label("[bold]交互测试 — 输入参数[/]")
            with Horizontal(classes="row"):
                yield Label("Area: ", classes="inline")
                yield Input(placeholder="<area>", id="area")
                yield Label("NPC ID: ", classes="inline")
                yield Input(placeholder="<npc_id>", id="npc_id")
            with Horizontal(classes="row"):
                yield Label("Context: ", classes="inline")
                yield Input(placeholder="<情境描述>", id="context")
            with Horizontal(classes="row"):
                yield Label("Kind: ")
                yield Select(
                    [("Dialogue", "dialogue"), ("Event", "event"), ("Description", "description")],
                    id="kind", value="dialogue",
                )
                yield Label("  Stream: ")
                yield Switch(value=True, id="stream_mode")
                yield Button("生成", id="gen_btn", variant="primary")
                yield Button("清空输出", id="clear_btn")
                yield Button("新会话", id="new_session_btn")
            yield Static("", id="gen-status")

        yield StreamingOutput(id="play-output")
        yield RichLog(id="history-log", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "gen_btn":
            self._do_generate()
        elif event.button.id == "clear_btn":
            self.query_one("#play-output", StreamingOutput).clear()
        elif event.button.id == "new_session_btn":
            state = get_state()
            if state.engine.memory:
                state.engine.memory.new_session()
            state.session_history.clear()
            self.query_one("#history-log", RichLog).clear()
            self.query_one("#gen-status", Static).update("[green]会话已重置[/]")

    @work(thread=False)
    async def _do_generate(self) -> None:
        state = get_state()
        if not state.api_ready:
            self.query_one("#gen-status", Static).update("[red]请先在 API 配置页填入 API Key[/]")
            return

        area = self.query_one("#area", Input).value
        npc_id = self.query_one("#npc_id", Input).value
        context = self.query_one("#context", Input).value
        kind = self.query_one("#kind", Select).value
        stream = self.query_one("#stream_mode", Switch).value

        game_state = GameState(world=WorldState(area=area))
        if npc_id and state.engine.npcs and npc_id in state.engine.npcs:
            game_state.npcs[npc_id] = state.engine.npcs[npc_id]

        status = self.query_one("#gen-status", Static)
        output = self.query_one("#play-output", StreamingOutput)
        history = self.query_one("#history-log", RichLog)

        history.write(f"[dim]> {context}[/]")

        if stream:
            status.update("[yellow]流式生成中...[/]")
            output.clear()
            last_partial = None
            last_len = 0
            try:
                async for partial in state.engine.tell_stream_async(
                    game_state, kind=kind, context=context, npc_id=npc_id,
                ):
                    if isinstance(partial, NarrativeOutput):
                        output.show_result(partial.model_dump())
                        status.update(f"[green]完成 | backend={partial.backend}[/]")
                        text = partial.dialogue.text if partial.dialogue else (
                            partial.description.text if partial.description else (
                                partial.event.title if partial.event else ""))
                        history.write(f"  {text}")
                        state.session_history.append({"context": context, "response": text})
                        return
                    last_partial = partial
                    t = getattr(partial, "text", "") or getattr(partial, "description", "") or ""
                    if isinstance(t, str) and len(t) > last_len:
                        output.append_text(t[last_len:])
                        last_len = len(t)
            except Exception as e:
                status.update(f"[red]错误: {e}[/]")
                return

            if last_partial is not None:
                final_text = getattr(last_partial, "text", "") or getattr(last_partial, "description", "") or getattr(last_partial, "title", "")
                history.write(f"  {final_text}")
                state.session_history.append({"context": context, "response": final_text})
            status.update("[green]完成[/]")
        else:
            status.update("[yellow]生成中...[/]")
            output.clear()
            try:
                result = await state.engine.tell_async(
                    game_state, kind=kind, context=context, npc_id=npc_id,
                )
                output.show_result(result.model_dump())
                status.update(f"[green]完成 | backend={result.backend} | tokens={result.tokens_used}[/]")
                text = result.dialogue.text if result.dialogue else ""
                history.write(f"  {text}")
                state.session_history.append({"context": context, "response": str(result.model_dump())})
            except Exception as e:
                status.update(f"[red]错误: {e}[/]")
