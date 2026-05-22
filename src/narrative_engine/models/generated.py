"""AI 总编剧生成器用的 schema。

LLM 输出后由 StoryGenerator._write_story_dir() 落盘为 stories/<name>/
目录下的 story.yaml / npcs.yaml / chapters/*.yaml 三件套；落盘后
StoryLoader 能直接读回来跑。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GeneratedNPC(BaseModel):
    id: str = Field(description="snake_case 唯一标识，如 bartender_kade")
    name: str
    mood: str = "neutral"
    traits: list[str] = Field(default_factory=list, max_length=5)
    relationship: float = 0.0
    preset_memories: list[dict[str, Any]] = Field(default_factory=list)


class GeneratedBeat(BaseModel):
    id: str = Field(description="snake_case 唯一标识")
    kind: Literal["dialogue", "event", "description", "all"] = "description"
    priority: int = 50
    trigger: dict[str, Any] = Field(
        description="触发条件，例如 {'world.area': 'cyber_bar'} 或 {'_npc_id': 'bartender_kade'}",
    )
    text: str = ""
    mood: str = "neutral"
    event_title: str = ""
    event_choices: list[str] = Field(default_factory=list)
    event_consequences: dict[str, str] = Field(default_factory=dict)


class GeneratedChapter(BaseModel):
    title: str
    world_setting: str = Field(description="章节级世界观，覆盖故事级 default_world")
    tone: str = "neutral"
    beats: list[GeneratedBeat] = Field(default_factory=list, min_length=3)


class GeneratedStory(BaseModel):
    """LLM 一次性产出整个故事所需的全部内容。"""

    title: str
    setting: str = Field(description="默认世界观一段话")
    tone: str = "neutral"
    era: str = ""
    fallback_dialogue: list[str] = Field(default_factory=list, min_length=2)
    fallback_event: list[str] = Field(default_factory=list, min_length=2)
    fallback_description: list[str] = Field(default_factory=list, min_length=2)
    npcs: list[GeneratedNPC] = Field(default_factory=list, min_length=1)
    chapters: list[GeneratedChapter] = Field(default_factory=list, min_length=1)
