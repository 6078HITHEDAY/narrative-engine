"""API 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from narrative_engine.models.state import GameState


class TellRequest(BaseModel):
    state: GameState
    kind: str = "dialogue"
    context: str = ""
    npc_id: str = ""
    stream: bool = False


class StoryLoadRequest(BaseModel):
    story_dir: str
    chapter: str | None = None


class ChapterSwitchRequest(BaseModel):
    chapter: str


class StoryInfo(BaseModel):
    title: str = ""
    chapter: str = ""
    chapters: list[str] = Field(default_factory=list)
    npcs: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
