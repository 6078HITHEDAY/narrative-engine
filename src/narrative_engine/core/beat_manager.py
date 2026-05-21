from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from narrative_engine.models.narrative import StoryBeat
from narrative_engine.models.state import GameState


class BeatManager:
    def __init__(self, beats: list[StoryBeat] | None = None, state_path: str = "") -> None:
        self._beats: dict[str, StoryBeat] = {}
        self._fired: set[str] = set()
        self._state_path = Path(state_path) if state_path else None
        if beats:
            self.register_many(beats)
        if self._state_path and self._state_path.exists():
            self.load()

    @property
    def fired(self) -> set[str]:
        return self._fired

    @property
    def pending(self) -> list[StoryBeat]:
        return [b for b in self._beats.values() if b.id not in self._fired]

    def register(self, beat: StoryBeat) -> None:
        self._beats[beat.id] = beat

    def register_many(self, beats: list[StoryBeat]) -> None:
        for b in beats:
            self.register(b)

    def replace_beats(self, beats: list[StoryBeat]) -> None:
        """替换全部 beats，保留 fired 集合。"""
        self._beats = {b.id: b for b in beats}

    def reset(self) -> None:
        self._fired.clear()

    def mark_fired(self, beat_id: str) -> None:
        self._fired.add(beat_id)

    def save(self, path: str | None = None) -> None:
        p = Path(path) if path else self._state_path
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"fired": sorted(self._fired)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, path: str | None = None) -> None:
        p = Path(path) if path else self._state_path
        if not p or not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        self._fired = set(data.get("fired", []))

    def check(self, state: GameState, kind: str = "", npc_id: str = "") -> StoryBeat | None:
        candidates = []
        for beat in self._beats.values():
            if beat.once and beat.id in self._fired:
                continue
            if beat.kind != "all" and kind and beat.kind != kind:
                continue
            if not self._evaluate(state, beat.trigger, npc_id):
                continue
            candidates.append(beat)

        candidates.sort(key=lambda b: b.priority, reverse=True)
        return candidates[0] if candidates else None

    def _evaluate(self, state: GameState, trigger: dict[str, Any], npc_id: str = "") -> bool:
        if not trigger:
            return False

        # --- $or: 任一条件组满足即可 ---
        or_groups = trigger.get("$or")
        if or_groups is not None:
            if not isinstance(or_groups, list):
                return False
            if not any(self._evaluate(state, group, npc_id) for group in or_groups):
                return False

        # --- $not: 取反 ---
        not_expr = trigger.get("$not")
        if not_expr is not None:
            if isinstance(not_expr, dict):
                inner = self._evaluate(state, not_expr, npc_id)
            elif isinstance(not_expr, list):
                # NOT (OR of groups) — all groups must fail
                inner = any(self._evaluate(state, g, npc_id) for g in not_expr)
            else:
                return False
            if inner:
                return False

        # --- AND 条件 ---
        for key, expected in trigger.items():
            if key.startswith("$"):
                continue
            value = self._resolve(state, key, npc_id)
            if not self._match(value, expected):
                return False
        return True

    def _resolve(self, state: GameState, key: str, npc_id: str = "") -> Any:
        """解析触发键。支持:
        - 普通路径: "player.attributes.san", "world.area"
        - _ 前缀虚拟字段: "_inventory_count", "_photos_count", "_npc_id"
        """
        # 虚拟字段
        virtual: dict[str, Any] = {
            "_inventory_count": len(state.player.inventory),
            "_photos_count": len(state.player.recent_actions),
            "_history_count": len(state.history),
            "_npc_count": len(state.npcs),
            "_npc_id": npc_id,
        }
        if key in virtual:
            return virtual[key]

        parts = key.split(".")
        obj: Any = state
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return None
        return obj

    @staticmethod
    def parse_beats_yaml(path: str) -> list[StoryBeat]:
        """从 YAML 配置文件解析 StoryBeat 列表。

        配置文件格式见 config/story_beats.yaml。
        """
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return [StoryBeat(**item) for item in data.get("beats", [])]

    @staticmethod
    def _match(value: Any, expected: Any) -> bool:
        if isinstance(expected, str):
            # 正则匹配: /pattern/
            if len(expected) > 2 and expected.startswith("/") and expected.endswith("/"):
                pattern = expected[1:-1]
                return bool(re.search(pattern, str(value) if value is not None else ""))

            # 比较运算符: <= >= < > ==
            m = re.match(r"^(<=|>=|<|>|==)\s*(.+)$", expected)
            if m:
                op, rhs = m.group(1), m.group(2)
                try:
                    num_val = float(value) if value is not None else 0
                    num_rhs = float(rhs)
                except (ValueError, TypeError):
                    return False
                if op == "<=":
                    return num_val <= num_rhs
                if op == ">=":
                    return num_val >= num_rhs
                if op == "<":
                    return num_val < num_rhs
                if op == ">":
                    return num_val > num_rhs
                if op == "==":
                    return num_val == num_rhs

        # 精确匹配（包含 bool / None）
        return value == expected
