from __future__ import annotations

import time

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    """NPC 长期记忆——跨会话保留的重要交互。"""

    npc_id: str = ""
    content: str
    kind: str = "dialogue"
    importance: int = Field(default=0, ge=0, le=10)
    timestamp: float = Field(default_factory=time.time)


class SessionTurn(BaseModel):
    """单轮对话记录——短期会话上下文。"""

    turn: int
    npc_id: str = ""
    player_context: str = ""
    engine_response: str = ""
    kind: str = "dialogue"
