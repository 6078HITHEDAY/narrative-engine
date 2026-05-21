"""TUI 全局状态管理。"""

from __future__ import annotations

from narrative_engine import NarrativeEngine


class TuiState:
    """TUI 全局状态单例。"""

    def __init__(self) -> None:
        self.engine: NarrativeEngine | None = None
        self.api_config: dict = {
            "provider": "openai",
            "api_key": "",
            "api_base": "",
            "model": "",
            "temperature": 0.8,
        }
        self.storage_mode: str = "memory"
        self.current_story: str = ""
        self.session_history: list[dict] = []  # 对话历史

    @property
    def api_ready(self) -> bool:
        return bool(self.api_config.get("api_key"))


_state: TuiState | None = None


def get_state() -> TuiState:
    global _state
    if _state is None:
        _state = TuiState()
    return _state
