import logging

from narrative_engine.core.engine import NarrativeEngine
from narrative_engine.core.director import AIDirector, DirectorError
from narrative_engine.core.auto_narrator import AutoIntent, AutoNarrator
from narrative_engine.core.beat_manager import BeatManager
from narrative_engine.core.interpreter import ConfigInterpreter
from narrative_engine.core.memory import MemoryManager
from narrative_engine.core.story_loader import StoryLoader
from narrative_engine.models.config import (
    ChapterConfig,
    EngineConfig,
    FallbackPool,
    LLMBackend,
    PromptTemplates,
    ProviderKind,
    RuntimeConfig,
    StoryMeta,
    TemperatureProfile,
    WorldConfig,
)
from narrative_engine.models.memory import MemoryRecord, SessionTurn
from narrative_engine.models.state import GameState, PlayerState, WorldState, NPCState
from narrative_engine.models.narrative import NarrativeOutput, StoryBeat, Dialogue, Event, Description

def enable_logging(level: int = logging.INFO) -> None:
    """配置引擎日志输出，方便排查 fallback 降级等问题。"""
    logging.basicConfig(
        format="[narrative_engine] %(levelname)s %(name)s: %(message)s",
        level=level,
    )


__all__ = [
    "enable_logging",
    "NarrativeEngine",
    "AIDirector",
    "DirectorError",
    "AutoNarrator",
    "AutoIntent",
    "BeatManager",
    "ConfigInterpreter",
    "MemoryManager",
    "StoryLoader",
    "ChapterConfig",
    "EngineConfig",
    "FallbackPool",
    "LLMBackend",
    "PromptTemplates",
    "ProviderKind",
    "RuntimeConfig",
    "StoryMeta",
    "TemperatureProfile",
    "WorldConfig",
    "MemoryRecord",
    "SessionTurn",
    "GameState",
    "PlayerState",
    "WorldState",
    "NPCState",
    "NarrativeOutput",
    "StoryBeat",
    "Dialogue",
    "Event",
    "Description",
]
