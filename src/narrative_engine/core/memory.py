from __future__ import annotations

import asyncio
import json
from pathlib import Path

from narrative_engine.models.memory import MemoryRecord, SessionTurn


class MemoryManager:
    """统一管理短期会话上下文和长期 NPC 记忆。"""

    def __init__(
        self,
        memory_size: int = 20,
        session_turns: int = 5,
        memory_path: str = "",
    ) -> None:
        self._memories: dict[str, list[MemoryRecord]] = {}  # npc_id -> records
        self._turns: list[SessionTurn] = []
        self._turn_counter = 0
        self._max_memories = memory_size
        self._max_session_turns = session_turns
        self._path = Path(memory_path) if memory_path else None
        if self._path and self._path.exists():
            self.load()

    # ---- Session (短期) ----

    def record_turn(
        self, npc_id: str, player_context: str, engine_response: str, kind: str = "dialogue"
    ) -> None:
        self._turn_counter += 1
        turn = SessionTurn(
            turn=self._turn_counter,
            npc_id=npc_id,
            player_context=player_context,
            engine_response=engine_response,
            kind=kind,
        )
        self._turns.append(turn)
        if len(self._turns) > self._max_session_turns * 2:
            self._turns = self._turns[-self._max_session_turns :]

    def session_context(self) -> str:
        if not self._turns:
            return ""
        recent = self._turns[-self._max_session_turns :]
        lines = []
        for t in recent:
            tag = f"[{t.npc_id}]" if t.npc_id else ""
            lines.append(f"玩家: {t.player_context}")
            lines.append(f"引擎{tag}: {t.engine_response}")
        return "\n".join(lines)

    def new_session(self) -> None:
        self._turns.clear()
        self._turn_counter = 0

    # ---- Memory (长期) ----

    def remember(self, npc_id: str, content: str, kind: str = "dialogue", importance: int = 0) -> None:
        if not npc_id or not content.strip():
            return
        content = content.strip()

        if npc_id not in self._memories:
            self._memories[npc_id] = []

        # 去重：完全相同内容跳过
        for existing in self._memories[npc_id]:
            if existing.content.strip() == content:
                return

        record = MemoryRecord(npc_id=npc_id, content=content, kind=kind, importance=importance)
        self._memories[npc_id].append(record)

        # 淘汰：按 importance 降序、timestamp 降序，保留前 memory_size
        if len(self._memories[npc_id]) > self._max_memories:
            self._memories[npc_id].sort(
                key=lambda r: (r.importance, r.timestamp), reverse=True,
            )
            self._memories[npc_id] = self._memories[npc_id][:self._max_memories]

    def recall(self, npc_id: str, limit: int = 10) -> list[MemoryRecord]:
        if not npc_id or npc_id not in self._memories:
            return []
        records = self._memories[npc_id]
        records.sort(key=lambda r: (r.importance, r.timestamp), reverse=True)
        return records[:limit]

    def memory_context(self, npc_id: str) -> str:
        records = self.recall(npc_id, limit=5)
        if not records:
            return ""
        lines = [f"- [{r.kind}] {r.content}" for r in records]
        return "\n".join(lines)

    # ---- 持久化 ----

    def save(self, path: str | None = None) -> None:
        p = Path(path) if path else self._path
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            npc_id: [r.model_dump() for r in records]
            for npc_id, records in self._memories.items()
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str | None = None) -> None:
        p = Path(path) if path else self._path
        if not p or not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        for npc_id, records in data.items():
            self._memories[npc_id] = [MemoryRecord(**r) for r in records]

    def clear(self) -> None:
        self._memories.clear()
        self._turns.clear()
        self._turn_counter = 0

    async def asave(self, path: str | None = None) -> None:
        p = Path(path) if path else self._path
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            npc_id: [r.model_dump() for r in records]
            for npc_id, records in self._memories.items()
        }
        await asyncio.to_thread(
            p.write_text,
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def aload(self, path: str | None = None) -> None:
        p = Path(path) if path else self._path
        if not p or not p.exists():
            return
        text = await asyncio.to_thread(p.read_text, encoding="utf-8")
        data = json.loads(text)
        for npc_id, records in data.items():
            self._memories[npc_id] = [MemoryRecord(**r) for r in records]
