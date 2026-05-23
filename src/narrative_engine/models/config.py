from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from narrative_engine.models.narrative import StoryBeat
from narrative_engine.models.state import NPCState


class ProviderKind(str, Enum):
    openai = "openai"           # OpenAI 兼容 (DeepSeek, Ollama 等)
    anthropic = "anthropic"    # Anthropic 兼容


class TemperatureProfile(BaseModel):
    """动态 temperature 调整策略。"""
    enabled: bool = True
    kind_adjustments: dict[str, float] = Field(default_factory=lambda: {
        "dialogue": -0.05,
        "event": 0.1,
        "description": 0.0,
    })
    mood_adjustments: dict[str, float] = Field(default_factory=lambda: {
        "angry": 0.15,
        "excited": 0.1,
        "calm": -0.1,
        "peaceful": -0.1,
        "sad": -0.05,
        "neutral": 0.0,
    })

    def resolve(self, base_temp: float, kind: str = "", npc_mood: str = "") -> float:
        if not self.enabled:
            return base_temp
        kind_adj = self.kind_adjustments.get(kind, 0.0)
        mood_adj = self.mood_adjustments.get(npc_mood, 0.0)
        return max(0.1, min(2.0, base_temp + kind_adj + mood_adj))


class LLMBackend(BaseModel):
    provider: ProviderKind = ProviderKind.openai
    model: str = ""
    api_key: str = ""
    api_base: str | None = None
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    max_tokens: int = 512
    timeout: float = 30.0
    temperature_profile: TemperatureProfile = Field(default_factory=TemperatureProfile)
    structured_output_mode: Literal["auto", "tools", "json"] = "auto"
    reasoning_model: bool = False
    reasoning_max_tokens: int = 2048

    def resolve_model(self) -> str:
        if self.model:
            if "/" in self.model:
                return self.model
            return f"{self.provider.value}/{self.model}"
        defaults = {
            ProviderKind.openai: "openai/deepseek-v4-pro",
            ProviderKind.anthropic: "anthropic/claude-sonnet-4-6",
        }
        return defaults[self.provider]


class EngineConfig(BaseModel):
    backend: LLMBackend = Field(default_factory=LLMBackend)
    cache_enabled: bool = True
    cache_dir: str = ".cache/narrative_engine"
    filter_enabled: bool = True
    filter_blacklist: list[str] = Field(default_factory=lambda: [
        "CPU", "GPU", "你好我是AI", "作为一个人工智能",
        "according to my training", "as an AI language model",
    ])
    world_setting: str = ""
    fallback_pool: dict[str, list[str]] = Field(default_factory=dict)
    beats: list[StoryBeat] = Field(default_factory=list)
    state_path: str = ""  # BeatManager 持久化文件路径，留空则不做持久化
    memory_enabled: bool = True
    memory_size: int = 20  # 每个 NPC 最多记忆条数
    session_turns: int = 5  # prompt 中包含的最近轮数
    memory_path: str = ""  # 长期记忆持久化文件路径


# ======== 配置解释器用的子模型 ========

class WorldConfig(BaseModel):
    """世界观设定 + 章节起始状态。

    setting/tone/era 描述世界观，注入 prompt；
    area/time/weather/chapter 是章节起点，由调用方读出来填进 GameState.world。
    """
    setting: str = ""
    tone: str = "neutral"
    era: str = ""
    area: str = ""
    time: str = ""
    weather: str = ""
    chapter: str = ""
    extra: dict[str, str] = Field(default_factory=dict)


class PromptTemplates(BaseModel):
    """AI 生成 prompt 模板（覆盖内置 .j2）。留空则使用内置模板。"""
    dialogue: str = ""
    event: str = ""
    description: str = ""


class FallbackPool(BaseModel):
    """保底文案池。"""
    dialogue: list[str] = Field(default_factory=list)
    event: list[str] = Field(default_factory=list)
    description: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "dialogue": self.dialogue,
            "event": self.event,
            "description": self.description,
        }


class RuntimeConfig(BaseModel):
    """解释器从 config/ 目录产出的统一运行时配置。"""
    world: WorldConfig = Field(default_factory=WorldConfig)
    beats: list[StoryBeat] = Field(default_factory=list)
    npcs: dict[str, NPCState] = Field(default_factory=dict)
    templates: PromptTemplates = Field(default_factory=PromptTemplates)
    fallback: FallbackPool = Field(default_factory=FallbackPool)
    state_path: str = ".cache/narrative_engine/story_state.json"

    def to_engine_config(self, backend: LLMBackend | None = None) -> EngineConfig:
        """转换为向后兼容的 EngineConfig。"""
        return EngineConfig(
            backend=backend or LLMBackend(),
            world_setting=self.world.setting,
            beats=self.beats,
            fallback_pool=self.fallback.to_dict(),
            state_path=self.state_path,
        )


class StoryMeta(BaseModel):
    """故事级元信息 — story.yaml 顶层结构。"""
    title: str = ""
    default_world: WorldConfig = Field(default_factory=WorldConfig)
    default_fallback: FallbackPool = Field(default_factory=FallbackPool)


class ChapterConfig(BaseModel):
    """单个章节的完整配置。"""
    title: str = ""
    world: WorldConfig = Field(default_factory=WorldConfig)
    beats: list[StoryBeat] = Field(default_factory=list)
    fallback: FallbackPool = Field(default_factory=FallbackPool)
