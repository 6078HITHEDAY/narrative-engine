from pydantic import BaseModel, Field


class PlayerState(BaseModel):
    """调用方按需填充，字段均为可选。"""

    name: str = "player"
    attributes: dict[str, int] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)
    recent_actions: list[str] = Field(default_factory=list)


class WorldState(BaseModel):
    area: str = ""
    time: str = ""
    weather: str = ""
    chapter: str = ""
    extra: dict[str, str] = Field(default_factory=dict)


class NPCState(BaseModel):
    id: str
    name: str
    relationship: float = 0.0
    mood: str = "neutral"
    traits: list[str] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)
    preset_memories: list[dict] = Field(default_factory=list)


class GameState(BaseModel):
    player: PlayerState = Field(default_factory=PlayerState)
    world: WorldState = Field(default_factory=WorldState)
    npcs: dict[str, NPCState] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)
