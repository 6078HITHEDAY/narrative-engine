"""流式文本渲染组件。"""

from __future__ import annotations

from textual.widgets import RichLog


class StreamingOutput(RichLog):
    """支持流式追加文本的 RichLog 扩展。"""

    def append_text(self, text: str) -> None:
        self.write(text)

    def show_result(self, result: dict) -> None:
        self.clear()
        kind = result.get("kind", "")
        backend = result.get("backend", "")
        tokens = result.get("tokens_used", 0)
        cached = result.get("cached", False)

        if kind == "dialogue" and result.get("dialogue"):
            d = result["dialogue"]
            text = d.get("text", "")
            mood = d.get("mood_change", 0)
            self.write(f"[bold green]对话:[/] {text}")
            if mood:
                self.write(f"  情绪变化: {mood:+d}")
        elif kind == "event" and result.get("event"):
            e = result["event"]
            self.write(f"[bold yellow]事件: {e.get('title', '')}[/]")
            self.write(f"  {e.get('description', '')}")
            choices = e.get("choices", [])
            if choices:
                self.write("  选项:")
                for c in choices:
                    self.write(f"    - {c}")
        elif kind == "description" and result.get("description"):
            d = result["description"]
            self.write(f"[bold blue]描述:[/] {d.get('text', '')}")
            self.write(f"  氛围: {d.get('mood', '')}")

        meta = f"[dim]backend={backend} | tokens={tokens} | cached={cached}[/]"
        self.write(meta)
