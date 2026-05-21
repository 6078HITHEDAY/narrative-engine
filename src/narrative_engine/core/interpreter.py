"""配置解释器。

读取 config/ 目录下所有 yaml/json 文件，按文件名约定或内容自动识别类型，
合并为统一的 RuntimeConfig。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from narrative_engine.models.config import (
    RuntimeConfig,
    WorldConfig,
    PromptTemplates,
    FallbackPool,
)
from narrative_engine.models.narrative import StoryBeat
from narrative_engine.models.state import NPCState


class ConfigInterpreter:
    def __init__(self, config_dir: str) -> None:
        self._dir = Path(config_dir)
        if not self._dir.is_dir():
            raise FileNotFoundError(f"配置目录不存在: {config_dir}")

    @classmethod
    def from_story_dir(cls, story_dir: str) -> RuntimeConfig:
        """从故事目录加载单个 story.yaml，按顶层 key 自动分类。"""
        path = Path(story_dir) / "story.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"故事文件不存在: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"story.yaml 必须是 dict 格式，不能是 list")
        runtime = RuntimeConfig()
        self = cls.__new__(cls)
        self._merge(runtime, "story", data)
        return runtime

    def interpret(self) -> RuntimeConfig:
        runtime = RuntimeConfig()

        for filepath in sorted(self._dir.glob("*")):
            if filepath.suffix not in (".yaml", ".yml", ".json"):
                continue
            data = self._load(filepath)
            if data is None:
                continue
            self._merge(runtime, filepath.stem, data)

        return runtime

    def _load(self, path: Path) -> dict | list | None:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None

        if path.suffix == ".json":
            import json
            return json.loads(text)

        return yaml.safe_load(text)

    def _merge(self, runtime: RuntimeConfig, stem: str, data: dict | list) -> None:
        # --- 文件名约定 ---
        handlers = {
            "world": lambda d: self._merge_world(runtime, d),
            "beats": lambda d: self._merge_beats(runtime, d),
            "npcs": lambda d: self._merge_npcs(runtime, d),
            "templates": lambda d: self._merge_templates(runtime, d),
            "fallback": lambda d: self._merge_fallback(runtime, d),
        }
        if stem in handlers and isinstance(data, (dict, list)):
            handlers[stem](data)
            return

        # --- 内容推断 ---
        if isinstance(data, dict):
            for key in handlers:
                if key in data and key != stem:
                    handlers[key](data[key])

    def _merge_world(self, runtime: RuntimeConfig, data: dict) -> None:
        runtime.world = WorldConfig(**data)

    def _merge_beats(self, runtime: RuntimeConfig, data: dict | list) -> None:
        items = data if isinstance(data, list) else data.get("beats", [])
        for item in items:
            runtime.beats.append(StoryBeat(**item))

    def _merge_npcs(self, runtime: RuntimeConfig, data: dict | list) -> None:
        items = data if isinstance(data, list) else data.get("npcs", [])
        if isinstance(items, list):
            for item in items:
                npc = NPCState(**item)
                runtime.npcs[npc.id] = npc
        elif isinstance(items, dict):
            for npc_id, npc_data in items.items():
                runtime.npcs[npc_id] = NPCState(id=npc_id, **npc_data)

    def _merge_templates(self, runtime: RuntimeConfig, data: dict) -> None:
        runtime.templates = PromptTemplates(**data)

    def _merge_fallback(self, runtime: RuntimeConfig, data: dict) -> None:
        runtime.fallback = FallbackPool(**data)
