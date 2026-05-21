from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class StoryBeat(BaseModel):
    """剧情锚点——手写内容，AI 完全不碰。

    两种定义方式：
      1. 完整：hand_written = NarrativeOutput(...)
      2. 简写：text / dialogue_text / event_title 等字段，自动构建 NarrativeOutput

    trigger 支持：
      - 精确匹配：{"world.area": "old_dock"}
      - 比较操作：{"player.attributes.san": "<=50"}
      - $or 条件组：{"$or": [{...}, {...}]}
      - 正则匹配：{"world.area": "/码头|港口/"}
    """

    id: str
    title: str = ""
    kind: str = "all"
    trigger: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    once: bool = True
    unlocks: list[str] = Field(default_factory=list)
    chapter: str = ""

    # ---- 完整模式（优先级最高） ----
    hand_written: NarrativeOutput | None = None

    # ---- 简写模式 ----
    text: str = ""
    dialogue_text: str = ""
    mood: str = "neutral"
    mood_change: int = 0
    unlock_hint: str | None = None
    event_title: str = ""
    event_description: str = ""
    event_choices: list[str] = Field(default_factory=list)
    event_consequences: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _build_hand_written(self) -> StoryBeat:
        if self.hand_written is not None:
            return self

        kind = self.kind

        if kind == "dialogue":
            self.hand_written = NarrativeOutput(
                kind="dialogue",
                dialogue=Dialogue(
                    text=self.text or self.dialogue_text,
                    mood_change=self.mood_change,
                    unlock_hint=self.unlock_hint,
                ),
            )

        elif kind == "event":
            self.hand_written = NarrativeOutput(
                kind="event",
                event=Event(
                    title=self.event_title or self.title,
                    description=self.text or self.event_description,
                    choices=self.event_choices,
                    consequences=self.event_consequences,
                ),
            )

        elif kind == "description":
            self.hand_written = NarrativeOutput(
                kind="description",
                description=Description(
                    text=self.text,
                    mood=self.mood,
                ),
            )

        else:  # "all": 填充三种类型
            self.hand_written = NarrativeOutput(
                kind="all",
                dialogue=Dialogue(text=self.text or self.dialogue_text, mood_change=self.mood_change, unlock_hint=self.unlock_hint),
                event=Event(title=self.event_title or self.title, description=self.text or self.event_description,
                           choices=self.event_choices, consequences=self.event_consequences),
                description=Description(text=self.text, mood=self.mood),
            )

        return self


class Dialogue(BaseModel):
    text: str = Field(default="", max_length=200)
    mood_change: int = Field(default=0, ge=-10, le=10)
    unlock_hint: str | None = None


class Event(BaseModel):
    title: str = Field(default="", max_length=60)
    description: str = Field(default="", max_length=500)
    choices: list[str] = Field(default_factory=list)
    consequences: dict[str, str] = Field(default_factory=dict)


class Description(BaseModel):
    text: str = Field(default="", max_length=200)
    mood: str = Field(default="neutral")
    detail: str | None = None


class NarrativeOutput(BaseModel):
    kind: str
    dialogue: Dialogue | None = None
    event: Event | None = None
    description: Description | None = None
    tokens_used: int = 0
    cached: bool = False
    backend: str = ""
    raw: str = ""
