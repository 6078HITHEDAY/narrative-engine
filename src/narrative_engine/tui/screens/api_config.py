"""API 配置 Screen。"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Input, Label, Select, Static, Switch,
)

from narrative_engine.tui.config_store import save_to_file, load_from_file
from narrative_engine.tui.state import get_state


class APIConfigScreen(Screen):
    name = "api_config"

    CSS = """
    APIConfigScreen {
        align: center middle;
    }
    #api-form {
        width: 60;
        height: auto;
        border: solid $primary;
        padding: 1 2;
    }
    #api-form Label {
        margin-top: 1;
    }
    #api-form Input {
        margin-bottom: 1;
    }
    #api-form Select {
        margin-bottom: 1;
        height:3;
    }
    #api-status {
        height: auto;
        min-height: 3;
        margin-top: 1;
        padding: 0 1;
    }
    #config-summary {
        height: auto;
        min-height: 2;
        padding: 0 1;
        background: $surface-lighten-1;
        border: dashed $primary;
    }
    .row {
        height: auto;
    }
    """

    PROVIDER_HINTS = {
        "openai": "OpenAI 兼容 — DeepSeek / Ollama / vLLM 等",
        "anthropic": "Anthropic 兼容 — Claude 系列",
    }

    def compose(self) -> ComposeResult:
        state = get_state()
        with Vertical(id="api-form"):
            yield Label("Narrative Engine — API 配置", classes="title")
            yield Label("API 格式")
            yield Select(
                [("OpenAI 兼容 (DeepSeek/Ollama/vLLM)", "openai"),
                 ("Anthropic 兼容 (Claude)", "anthropic")],
                id="provider", value=state.api_config.get("provider", "openai"),
            )
            yield Label("API Key")
            yield Input(
                value=state.api_config.get("api_key", ""),
                password=True, id="api_key",
            )
            yield Label("Base URL")
            yield Input(
                value=state.api_config.get("api_base", ""),
                id="api_base", placeholder="https://api.deepseek.com",
            )
            yield Label("Model")
            yield Input(
                value=state.api_config.get("model", ""),
                id="model", placeholder="deepseek-v4-pro",
            )
            yield Label(f"Temperature: {state.api_config.get('temperature', 0.8)}")
            yield Input(
                value=str(state.api_config.get("temperature", 0.8)),
                id="temperature",
            )
            yield Label("存储模式")
            with Horizontal(classes="row"):
                yield Switch(value=state.storage_mode == "file", id="storage_mode")
                yield Label("本地文件 (~/.narrative_engine/config.json)", id="storage_label")
            yield Label("当前设置")
            yield Static("Provider: — | Model: 默认 | Temp: 0.8 | 存储: 内存", id="config-summary")
            with Horizontal(classes="row"):
                yield Button("测试连接", id="test_btn", variant="primary")
                yield Button("保存配置", id="save_btn", variant="success")
            yield Static("", id="api-status")

    def on_mount(self) -> None:
        state = get_state()
        saved = load_from_file()
        if saved:
            for field in ("provider", "api_base", "model", "temperature"):
                if field in saved:
                    inp = self.query_one(f"#{field}")
                    if isinstance(inp, Input):
                        inp.value = str(saved[field])
                    elif isinstance(inp, Select):
                        inp.value = saved[field]
            state.api_config.update(saved)
        self._update_status_line()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider":
            provider = str(event.value)
            hint = self.PROVIDER_HINTS.get(provider, "")
            status = self.query_one("#api-status", Static)
            status.update(f"[bold green]已选择: {event.select.selection}[/]\n[dim]{hint}[/]")
            self._update_status_line()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        state = get_state()
        state.storage_mode = "file" if event.value else "memory"
        self._update_status_line()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "test_btn":
            self._test_connection()
        elif event.button.id == "save_btn":
            self._save_config()

    def _update_status_line(self) -> None:
        provider = self.query_one("#provider", Select).value
        model = self.query_one("#model", Input).value or "默认"
        temp = self.query_one("#temperature", Input).value or "0.8"
        storage = "文件" if get_state().storage_mode == "file" else "内存"
        self.query_one("#config-summary", Static).update(
            f"Provider: [bold]{provider}[/] | Model: [bold]{model}[/] | Temp: [bold]{temp}[/] | 存储: [bold]{storage}[/]"
        )

    def _read_form(self) -> dict:
        return {
            "provider": self.query_one("#provider", Select).value,
            "api_key": self.query_one("#api_key", Input).value,
            "api_base": self.query_one("#api_base", Input).value,
            "model": self.query_one("#model", Input).value,
            "temperature": float(self.query_one("#temperature", Input).value or 0.8),
        }

    @work(thread=False)
    async def _test_connection(self) -> None:
        import litellm
        from narrative_engine import LLMBackend, ProviderKind

        config = self._read_form()
        status = self.query_one("#api-status", Static)

        if not config["api_key"]:
            status.update("[red]请输入 API Key[/]")
            return

        status.update("[yellow]正在测试连接...[/]")

        try:
            backend = LLMBackend(
                provider=ProviderKind(config["provider"]),
                api_key=config["api_key"],
                api_base=config["api_base"] or None,
                model=config["model"] or "",
                temperature=config["temperature"],
            )
            model = backend.resolve_model()
            kwargs: dict = dict(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
                timeout=backend.timeout,
            )
            if backend.api_key:
                kwargs["api_key"] = backend.api_key
            if backend.api_base:
                kwargs["api_base"] = backend.api_base

            response = await litellm.acompletion(**kwargs)
            actual_model = getattr(response, "model", model)
            content = response.choices[0].message.content if response.choices else ""
            status.update(f"[green]连接成功！model={actual_model} response=\"{content.strip()}\"[/]")
        except Exception as e:
            status.update(f"[red]连接失败: {e}[/]")

    def _save_config(self) -> None:
        config = self._read_form()
        state = get_state()
        state.api_config = config
        state.rebuild_engine()

        status = self.query_one("#api-status", Static)
        if state.storage_mode == "file":
            save_to_file(config)
            status.update("[green]配置已保存到本地文件，引擎已应用新配置[/]")
        else:
            status.update("[green]配置已保存到内存，引擎已应用新配置[/]")

        self._update_status_line()
        if hasattr(self.app, "update_status"):
            self.app.update_status()
