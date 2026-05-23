"""交互测试面板 — 流式生成 + event apply_choice 闭环。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Input, Label, RichLog, Select, Static, Switch,
)

from narrative_engine import GameState, WorldState, NarrativeOutput, PlayerState
from narrative_engine.core.auto_narrator import AutoNarrator
from narrative_engine.tui.state import get_state
from narrative_engine.tui.widgets.streaming_output import StreamingOutput


class PlaygroundPanel(VerticalScroll):
    DEFAULT_CSS = """
    PlaygroundPanel { padding: 1; }
    #play-input {
        height: auto; border: solid $surface-lighten-1;
        padding: 1; margin-bottom: 1;
    }
    #play-input Label { margin-top: 0; }
    .row { height: 3; align: left middle; }
    .inline { width: auto; padding: 0 1; }
    #play-output { height: 12; border: solid $primary; }
    #choice-row { height: auto; min-height: 1; padding: 0 1; }
    #choice-row Button { margin: 0 1 0 0; }
    #history-log { height: 10; border: solid $surface-lighten-1; margin-top: 1; }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_state: GameState | None = None
        self._last_output: NarrativeOutput | None = None
        self._narrator: AutoNarrator | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="play-input"):
            yield Label("[bold]交互测试[/]")
            with Horizontal(classes="row"):
                yield Label("智能模式:", classes="inline")
                yield Switch(value=False, id="auto_mode")
                yield Label("[dim]开启后只用自然语言；关闭走手动 kind+npc[/]", classes="inline")
            with Horizontal(classes="row", id="auto_row"):
                yield Label("说点什么:", classes="inline")
                yield Input(placeholder="例如：我走进酒馆，找老板说话", id="auto_input")
                yield Button("发送", id="auto_send_btn", variant="primary")
            with Horizontal(classes="row"):
                yield Label("Area:", classes="inline")
                yield Input(placeholder="<area>", id="area")
                yield Label("Chapter:", classes="inline")
                yield Input(placeholder="<chapter>", id="chapter")
            with Horizontal(classes="row"):
                yield Label("NPC:", classes="inline")
                yield Select([("(无)", "")], id="npc_id", value="", allow_blank=False)
                yield Label("Inventory:", classes="inline")
                yield Input(placeholder="逗号分隔", id="inventory")
            with Horizontal(classes="row"):
                yield Label("Context:", classes="inline")
                yield Input(placeholder="<情境描述>", id="context")
            with Horizontal(classes="row"):
                yield Label("Kind:", classes="inline")
                yield Select(
                    [("Dialogue", "dialogue"), ("Event", "event"), ("Description", "description")],
                    id="kind", value="dialogue", allow_blank=False,
                )
                yield Label("Stream:", classes="inline")
                yield Switch(value=True, id="stream_mode")
                yield Button("生成", id="gen_btn", variant="primary")
                yield Button("清空输出", id="clear_btn")
                yield Button("新会话", id="new_session_btn")
            yield Static("", id="gen-status")
        yield StreamingOutput(id="play-output")
        yield Horizontal(id="choice-row")
        yield RichLog(id="history-log", highlight=True, markup=True)

    def on_show(self) -> None:
        state = get_state()
        sel = self.query_one("#npc_id", Select)
        options = [("(无)", "")]
        if state.engine and state.engine.npcs:
            options.extend((f"{n.name} ({n.id})", n.id) for n in state.engine.npcs.values())
        sel.set_options(options)
        self._sync_auto_mode(self.query_one("#auto_mode", Switch).value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "auto_mode":
            self._sync_auto_mode(event.value)

    def _sync_auto_mode(self, auto_on: bool) -> None:
        self.query_one("#auto_row", Horizontal).display = auto_on

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "auto_input":
            self._trigger_auto()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "gen_btn":
            self._do_generate()
        elif bid == "auto_send_btn":
            self._trigger_auto()
        elif bid == "clear_btn":
            self.query_one("#play-output", StreamingOutput).clear()
            self._clear_choices()
        elif bid == "new_session_btn":
            state = get_state()
            if state.engine.memory:
                state.engine.memory.new_session()
            state.session_history.clear()
            self.query_one("#history-log", RichLog).clear()
            self._last_state = None
            self._last_output = None
            self._narrator = None
            self._clear_choices()
            self.query_one("#gen-status", Static).update("[green]会话已重置[/]")
        elif bid.startswith("choice-"):
            self._on_choice_clicked(int(bid.removeprefix("choice-")))

    def _trigger_auto(self) -> None:
        text = self.query_one("#auto_input", Input).value.strip()
        if not text:
            return
        self.query_one("#auto_input", Input).value = ""
        self._do_auto_generate(text)

    def _build_state(self) -> GameState:
        area = self.query_one("#area", Input).value.strip()
        chapter = self.query_one("#chapter", Input).value.strip()
        inv_raw = self.query_one("#inventory", Input).value
        inventory = [x.strip() for x in inv_raw.split(",") if x.strip()]
        return GameState(
            world=WorldState(area=area, chapter=chapter),
            player=PlayerState(inventory=inventory),
        )

    @work(thread=False)
    async def _do_auto_generate(self, user_input: str) -> None:
        state = get_state()
        if not state.engine:
            return
        if self._narrator is None:
            self._narrator = AutoNarrator(state.engine, self._build_state())

        status = self.query_one("#gen-status", Static)
        output = self.query_one("#play-output", StreamingOutput)
        history = self.query_one("#history-log", RichLog)
        self._clear_choices()

        history.write(f"[dim]>[/] {user_input}")
        status.update("[yellow]智能模式生成中...[/]")
        output.clear()

        try:
            intent, result = await self._narrator.respond(user_input)
        except Exception as e:
            status.update(f"[red]错误: {e}[/]")
            return

        output.show_result(result.model_dump())
        tag = intent.kind
        if intent.npc_id:
            tag = f"{intent.npc_id}/{intent.kind}"
        if intent.new_area:
            history.write(f"  [bold cyan]→ 切到 {intent.new_area}[/]")
        status.update(
            f"[green]完成[/] {tag} backend={result.backend} tokens={result.tokens_used}"
        )
        self._record_result(self._narrator.state, result, history, intent.kind, user_input)

    @work(thread=False)
    async def _do_generate(self) -> None:
        state = get_state()
        npc_id = self.query_one("#npc_id", Select).value or ""
        if isinstance(npc_id, type) or npc_id is Select.BLANK:
            npc_id = ""
        context = self.query_one("#context", Input).value
        kind = self.query_one("#kind", Select).value
        stream = self.query_one("#stream_mode", Switch).value

        game_state = self._build_state()
        if npc_id and state.engine.npcs and npc_id in state.engine.npcs:
            game_state.npcs[npc_id] = state.engine.npcs[npc_id]

        status = self.query_one("#gen-status", Static)
        output = self.query_one("#play-output", StreamingOutput)
        history = self.query_one("#history-log", RichLog)
        self._clear_choices()

        history.write(f"[dim]> [{kind}][/] {context or '(无 context)'}")

        if stream:
            status.update("[yellow]流式生成中...[/]")
            output.clear()
            last_text = ""
            try:
                async for partial in state.engine.tell_stream_async(
                    game_state, kind=kind, context=context, npc_id=npc_id,
                ):
                    if isinstance(partial, NarrativeOutput):
                        output.show_result(partial.model_dump())
                        status.update(
                            f"[green]完成[/] backend={partial.backend} "
                            f"tokens={partial.tokens_used} cached={partial.cached}"
                        )
                        self._record_result(game_state, partial, history, kind, context)
                        return
                    text = self._extract_partial_text(partial, kind)
                    if text and text != last_text:
                        if text.startswith(last_text):
                            output.append_text(text[len(last_text):])
                        else:
                            output.clear()
                            output.append_text(text)
                        last_text = text
            except Exception as e:
                status.update(f"[red]错误: {e}[/]")
                return
            status.update("[green]流式完成[/]")
        else:
            status.update("[yellow]生成中...[/]")
            output.clear()
            try:
                result = await state.engine.tell_async(
                    game_state, kind=kind, context=context, npc_id=npc_id,
                )
                output.show_result(result.model_dump())
                status.update(
                    f"[green]完成[/] backend={result.backend} "
                    f"tokens={result.tokens_used} cached={result.cached}"
                )
                self._record_result(game_state, result, history, kind, context)
            except Exception as e:
                status.update(f"[red]错误: {e}[/]")

    @staticmethod
    def _extract_partial_text(partial, kind: str) -> str:
        if kind == "dialogue":
            return getattr(partial, "text", "") or ""
        if kind == "event":
            return getattr(partial, "description", "") or getattr(partial, "title", "") or ""
        if kind == "description":
            return getattr(partial, "text", "") or ""
        return ""

    def _record_result(
        self, state: GameState, result: NarrativeOutput, history: RichLog,
        kind: str, context: str,
    ) -> None:
        self._last_state = state
        self._last_output = result
        text = ""
        if result.dialogue:
            text = result.dialogue.text
        elif result.description:
            text = result.description.text
        elif result.event:
            text = f"{result.event.title}: {result.event.description}"
        history.write(f"  [italic]{text}[/]")
        get_state().session_history.append({"context": context, "response": text})

        if result.event and result.event.choices:
            self._render_choices(result.event.choices)

    def _render_choices(self, choices: list[str]) -> None:
        row = self.query_one("#choice-row", Horizontal)
        row.remove_children()
        for i, choice in enumerate(choices):
            row.mount(Button(f"{i + 1}. {choice}", id=f"choice-{i}", variant="warning"))

    def _clear_choices(self) -> None:
        self.query_one("#choice-row", Horizontal).remove_children()

    def _on_choice_clicked(self, idx: int) -> None:
        state = get_state()
        if not self._last_state or not self._last_output or not self._last_output.event:
            return
        choices = self._last_output.event.choices
        if idx >= len(choices):
            return
        try:
            state.engine.apply_choice(self._last_state, self._last_output.event, choices[idx])
        except Exception as e:
            self.query_one("#gen-status", Static).update(f"[red]apply_choice 失败: {e}[/]")
            return
        history = self.query_one("#history-log", RichLog)
        history.write(f"  [bold yellow]→ 选择: {choices[idx]}[/]")
        self._clear_choices()
        self.query_one("#gen-status", Static).update(
            f"[green]已记录选择「{choices[idx]}」，下次生成会基于新 state[/]"
        )
