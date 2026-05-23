"""流式文本渲染组件 — 真正同行追加，不滚动堆叠。"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class StreamingOutput(VerticalScroll):
    """文本流缓冲到一个 Static 节点，update() 整体重绘。"""

    DEFAULT_CSS = """
    StreamingOutput {
        background: $surface;
        padding: 1 2;
    }
    StreamingOutput > Static {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._buf = ""
        self._body: Static | None = None

    def on_mount(self) -> None:
        self._body = Static("", id="streaming-body", markup=True)
        self.mount(self._body)

    def append_text(self, delta: str) -> None:
        if not delta:
            return
        self._buf += delta
        if self._body is not None:
            self._body.update(self._buf)
            self.scroll_end(animate=False)

    def clear(self) -> None:
        self._buf = ""
        if self._body is not None:
            self._body.update("")

    def show_result(self, result: dict) -> None:
        self._buf = ""
        kind = result.get("kind", "")
        backend = result.get("backend", "")
        tokens = result.get("tokens_used", 0)
        cached = result.get("cached", False)
        lines: list[str] = []

        if kind == "dialogue" and result.get("dialogue"):
            d = result["dialogue"]
            lines.append(f"[bold green]对话:[/] {d.get('text', '')}")
            mood = d.get("mood_change", 0)
            if mood:
                lines.append(f"  情绪变化: {mood:+d}")
            if d.get("unlock_hint"):
                lines.append(f"  [dim]解锁线索: {d['unlock_hint']}[/]")
        elif kind == "event" and result.get("event"):
            e = result["event"]
            lines.append(f"[bold yellow]事件: {e.get('title', '')}[/]")
            lines.append(f"  {e.get('description', '')}")
            choices = e.get("choices", [])
            if choices:
                lines.append("  选项:")
                for i, c in enumerate(choices, 1):
                    lines.append(f"    {i}. {c}")
        elif kind == "description" and result.get("description"):
            d = result["description"]
            lines.append(f"[bold blue]描述:[/] {d.get('text', '')}")
            if d.get("mood"):
                lines.append(f"  氛围: {d['mood']}")

        lines.append(f"[dim]backend={backend} | tokens={tokens} | cached={cached}[/]")
        text = "\n".join(lines)
        self._buf = text
        if self._body is not None:
            self._body.update(text)
            self.scroll_end(animate=False)
