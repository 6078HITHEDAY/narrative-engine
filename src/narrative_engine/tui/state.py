"""TUI 全局状态管理。"""

from __future__ import annotations

import os

from narrative_engine import (
    EngineConfig, LLMBackend, NarrativeEngine, ProviderKind,
)


class TuiState:
    def __init__(self) -> None:
        self.api_config: dict = {
            "provider": os.environ.get("NARRATIVE_BACKEND", "openai"),
            "api_key": os.environ.get("NARRATIVE_API_KEY", ""),
            "api_base": os.environ.get("NARRATIVE_API_BASE", ""),
            "model": os.environ.get("NARRATIVE_MODEL", ""),
            "temperature": 0.8,
        }
        self.storage_mode: str = "memory"
        self.current_story: str = ""
        self.session_history: list[dict] = []
        self.engine: NarrativeEngine = self._build_engine()

    def _build_engine(self) -> NarrativeEngine:
        try:
            provider = ProviderKind(self.api_config["provider"])
        except ValueError:
            provider = ProviderKind.openai
        backend = LLMBackend(
            provider=provider,
            api_key=self.api_config["api_key"],
            api_base=self.api_config["api_base"] or None,
            model=self.api_config["model"],
            temperature=float(self.api_config.get("temperature", 0.8)),
        )
        return NarrativeEngine(EngineConfig(backend=backend))

    def rebuild_engine(self) -> None:
        old_story = self.current_story
        self.engine = self._build_engine()
        if old_story:
            self.engine.load_story(old_story)

    @property
    def api_ready(self) -> bool:
        return bool(self.api_config.get("api_key"))


_state: TuiState | None = None


def get_state() -> TuiState:
    global _state
    if _state is None:
        _state = TuiState()
    return _state
