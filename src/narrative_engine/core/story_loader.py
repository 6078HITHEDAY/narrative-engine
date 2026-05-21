"""故事加载器。

支持两种目录结构：

新结构（推荐）:
  story_dir/
    story.yaml          # 故事元信息 + 默认 world/fallback
    npcs.yaml           # NPC 独立配置
    chapters/
      chapter_1.yaml    # 章节文件
      chapter_2.yaml

旧结构（向后兼容）:
  story_dir/
    story.yaml          # world + npcs + beats + fallback 全塞一个文件
"""

from __future__ import annotations

from pathlib import Path

import yaml

from narrative_engine.models.config import (
    ChapterConfig,
    FallbackPool,
    StoryMeta,
    WorldConfig,
)
from narrative_engine.models.narrative import StoryBeat
from narrative_engine.models.state import NPCState


class StoryLoader:
    def __init__(self, story_dir: str) -> None:
        self._dir = Path(story_dir)
        if not self._dir.is_dir():
            raise FileNotFoundError(f"故事目录不存在: {story_dir}")

    # ---- 主入口 ----

    def load(self) -> tuple[StoryMeta, dict[str, NPCState], dict[str, ChapterConfig]]:
        """加载整个故事目录。

        Returns:
            (meta, npcs, chapters)
        """
        chapters_dir = self._dir / "chapters"
        if chapters_dir.is_dir():
            return self._load_new_format()
        return self._load_legacy_format()

    # ---- 单文件加载 ----

    def load_npcs(self) -> dict[str, NPCState]:
        path = self._dir / "npcs.yaml"
        if not path.is_file():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        items = data.get("npcs", {})
        if isinstance(items, list):
            return {npc["id"]: NPCState(**npc) for npc in items}
        if isinstance(items, dict):
            return {npc_id: NPCState(id=npc_id, **npc_data) for npc_id, npc_data in items.items()}
        return {}

    def load_chapter(self, path: str | Path, defaults: StoryMeta | None = None) -> ChapterConfig:
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ChapterConfig()

        chapter = ChapterConfig(
            title=data.get("title", p.stem),
            beats=[StoryBeat(**b) for b in data.get("beats", [])],
        )

        # world: 章节 > 故事默认
        if "world" in data and isinstance(data["world"], dict):
            chapter.world = WorldConfig(**data["world"])
        elif defaults:
            chapter.world = defaults.default_world

        # fallback: 章节 > 故事默认
        if "fallback" in data and isinstance(data["fallback"], dict):
            chapter.fallback = FallbackPool(**data["fallback"])
        elif defaults:
            chapter.fallback = defaults.default_fallback

        return chapter

    def list_chapters(self) -> list[str]:
        chapters_dir = self._dir / "chapters"
        if not chapters_dir.is_dir():
            return []
        return sorted(
            p.stem for p in chapters_dir.glob("*.yaml")
            if p.is_file()
        )

    # ---- 内部 ----

    def _load_new_format(self) -> tuple[StoryMeta, dict[str, NPCState], dict[str, ChapterConfig]]:
        meta = self._load_story_meta()
        npcs = self.load_npcs()
        chapters = {}
        for name in self.list_chapters():
            path = self._dir / "chapters" / f"{name}.yaml"
            chapters[name] = self.load_chapter(path, meta)
        return meta, npcs, chapters

    def _load_legacy_format(self) -> tuple[StoryMeta, dict[str, NPCState], dict[str, ChapterConfig]]:
        """向后兼容旧的单文件 story.yaml 格式。"""
        path = self._dir / "story.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"故事文件不存在: {path}")

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("story.yaml 必须是 dict 格式")

        # 解析 NPC
        npcs: dict[str, NPCState] = {}
        npc_data = data.get("npcs", [])
        if isinstance(npc_data, list):
            for item in npc_data:
                npc = NPCState(**item)
                npcs[npc.id] = npc
        elif isinstance(npc_data, dict):
            for npc_id, npc_info in npc_data.items():
                npcs[npc_id] = NPCState(id=npc_id, **npc_info)

        # 解析 world
        world = WorldConfig(**data["world"]) if "world" in data else WorldConfig()

        # 解析 fallback
        fallback = FallbackPool()
        if "fallback" in data:
            fallback = FallbackPool(**data["fallback"])

        # 构建 meta
        meta = StoryMeta(
            title=data.get("title", self._dir.name),
            default_world=world,
            default_fallback=fallback,
        )

        # 构建章节（整个故事作为一章）
        beats = [StoryBeat(**b) for b in data.get("beats", [])]
        chapter = ChapterConfig(
            title=data.get("title", self._dir.name),
            world=world,
            beats=beats,
            fallback=fallback,
        )

        return meta, npcs, {"main": chapter}

    def _load_story_meta(self) -> StoryMeta:
        path = self._dir / "story.yaml"
        if not path.is_file():
            return StoryMeta(title=self._dir.name)

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return StoryMeta(title=self._dir.name)

        default_world = WorldConfig()
        if "default_world" in data and isinstance(data["default_world"], dict):
            default_world = WorldConfig(**data["default_world"])

        default_fallback = FallbackPool()
        if "default_fallback" in data and isinstance(data["default_fallback"], dict):
            default_fallback = FallbackPool(**data["default_fallback"])

        return StoryMeta(
            title=data.get("title", self._dir.name),
            default_world=default_world,
            default_fallback=default_fallback,
        )
