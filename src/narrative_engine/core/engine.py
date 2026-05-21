from __future__ import annotations

import json
import random
from pathlib import Path

from narrative_engine.core.beat_manager import BeatManager
from narrative_engine.core.cache import CacheManager
from narrative_engine.core.context import ContextManager
from narrative_engine.core.director import AIDirector
from narrative_engine.core.memory import MemoryManager
from narrative_engine.filters.keyword import KeywordFilter
from narrative_engine.models.config import EngineConfig, LLMBackend, RuntimeConfig
from narrative_engine.models.narrative import (
    NarrativeOutput,
    Dialogue,
    Event,
    Description,
)
from narrative_engine.models.state import GameState, NPCState

_OUTPUT_SCHEMAS = {
    "dialogue": Dialogue,
    "event": Event,
    "description": Description,
}


class NarrativeEngine:
    def __init__(
        self,
        config: EngineConfig | dict | None = None,
        *,
        runtime: RuntimeConfig | None = None,
        backend: LLMBackend | None = None,
    ) -> None:
        if runtime is not None:
            self._runtime = runtime
            self._config = runtime.to_engine_config(backend)
        else:
            if isinstance(config, dict):
                config = EngineConfig(**config)
            self._config = config or EngineConfig()
            if backend:
                self._config.backend = backend
            self._runtime = None

        self._npcs: dict[str, NPCState] = {}
        if self._runtime:
            self._npcs = dict(self._runtime.npcs)

        self._director = AIDirector(self._config.backend)
        self._context_mgr = ContextManager(
            self._config.world_setting,
            templates=self._runtime.templates if self._runtime else None,
        )
        self._cache = CacheManager(self._config.cache_dir) if self._config.cache_enabled else None
        self._filter = KeywordFilter(self._config.filter_blacklist) if self._config.filter_enabled else None
        self._memory = (
            MemoryManager(
                memory_size=self._config.memory_size,
                session_turns=self._config.session_turns,
                memory_path=self._config.memory_path,
            )
            if self._config.memory_enabled
            else None
        )
        self._beat_manager = BeatManager(
            self._config.beats,
            state_path=self._config.state_path or "",
        )

        self._story_dir = ""
        self._story_meta = None
        self._chapters: dict = {}
        self._current_chapter = ""

    @classmethod
    def from_config_dir(cls, config_dir: str, **overrides) -> NarrativeEngine:
        from narrative_engine.core.interpreter import ConfigInterpreter

        interpreter = ConfigInterpreter(config_dir)
        runtime = interpreter.interpret()
        for key, value in overrides.items():
            if hasattr(runtime, key):
                setattr(runtime, key, value)
        return cls(runtime=runtime)

    @classmethod
    def from_story(cls, story_dir: str, config_dir: str | None = None, chapter: str | None = None) -> NarrativeEngine:
        backend = cls._load_engine_backend(config_dir) if config_dir else None
        engine = cls(backend=backend) if backend else cls()
        engine.load_story(story_dir, chapter=chapter)
        return engine

    @staticmethod
    def _load_engine_backend(config_dir: str) -> LLMBackend | None:
        from pathlib import Path
        import yaml

        path = Path(config_dir) / "engine.yaml"
        if not path.is_file():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        backend_data = data.get("backend", {})
        if backend_data:
            return LLMBackend(**backend_data)
        return None

    @property
    def config(self) -> EngineConfig:
        return self._config

    @property
    def runtime(self) -> RuntimeConfig | None:
        return self._runtime

    @property
    def beat_manager(self) -> BeatManager:
        return self._beat_manager

    @property
    def memory(self) -> MemoryManager | None:
        return self._memory

    @property
    def current_chapter(self) -> str:
        return self._current_chapter

    @property
    def story_title(self) -> str:
        return self._story_meta.title if self._story_meta else ""

    @property
    def npcs(self) -> dict:
        return self._npcs

    # ---- 故事加载 ----

    def load_story(self, story_dir: str, chapter: str | None = None) -> None:
        from narrative_engine.core.story_loader import StoryLoader

        loader = StoryLoader(story_dir)
        meta, npcs, chapters_map = loader.load()

        if not chapters_map:
            raise ValueError(f"故事目录没有章节: {story_dir}")

        self._story_dir = str(story_dir)
        self._story_meta = meta
        self._chapters = chapters_map
        self._npcs = dict(npcs)

        # 选择章节
        if chapter and chapter in chapters_map:
            ch = chapters_map[chapter]
        else:
            ch = next(iter(chapters_map.values()))

        self._apply_chapter(ch)

        # 设定故事级状态文件路径
        state_dir = Path(story_dir) / ".state"
        self._config.state_path = str(state_dir / "story_state.json")
        self._config.memory_path = str(state_dir / "memories.json")
        self._beat_manager._state_path = Path(self._config.state_path)
        self._beat_manager.load()

        if self._memory:
            self._memory._path = Path(self._config.memory_path)
            self._memory.load()

        # 注入 NPC 预设记忆
        if self._memory:
            for npc in npcs.values():
                for mem in npc.preset_memories:
                    self._memory.remember(
                        npc.id,
                        mem.get("content", ""),
                        importance=mem.get("importance", 0),
                    )

    def switch_chapter(self, chapter_name: str) -> None:
        if chapter_name not in self._chapters:
            raise ValueError(f"章节不存在: {chapter_name}")
        self._apply_chapter(self._chapters[chapter_name])

    def list_chapters(self) -> list[str]:
        return sorted(self._chapters.keys())

    def reload_npcs(self) -> None:
        if not self._story_dir:
            return
        from narrative_engine.core.story_loader import StoryLoader

        loader = StoryLoader(self._story_dir)
        self._npcs = loader.load_npcs()

    def _apply_chapter(self, ch) -> None:
        from narrative_engine.models.config import ChapterConfig

        self._current_chapter = ch.title
        self._context_mgr.update_world_setting(ch.world.setting)
        self._beat_manager.replace_beats(ch.beats)

        fallback = ch.fallback or (
            self._story_meta.default_fallback if self._story_meta else None
        )
        if fallback:
            self._config.fallback_pool = fallback.to_dict()
        self._config.world_setting = ch.world.setting

    # ----

    def configure(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def save_state(self, path: str | None = None) -> None:
        self._beat_manager.save(path)

    def load_state(self, path: str | None = None) -> None:
        self._beat_manager.load(path)

    def tell(
        self,
        state: GameState | dict,
        kind: str,
        context: str = "",
        npc_id: str = "",
    ) -> NarrativeOutput:
        """单入口叙事生成。

        优先级：
        1. StoryBeat 锚点命中 → 直接出手写文案，不走 AI
        2. 缓存命中 → 返回缓存结果
        3. AI 生成 → 调 LLM
        4. 全部失败 → 降级保底文案
        """
        if isinstance(state, dict):
            state = GameState(**state)

        # ---- NPC 自动补全 ----
        if npc_id and npc_id not in state.npcs and npc_id in self._npcs:
            state.npcs[npc_id] = self._npcs[npc_id]

        # ---- 锚点优先 ----
        beat = self._beat_manager.check(state, kind=kind, npc_id=npc_id)
        if beat and beat.hand_written:
            self._beat_manager.mark_fired(beat.id)
            self._beat_manager.save()
            output = beat.hand_written
            output.cached = False
            output.backend = "storybeat"
            self._record_turn(npc_id, context, self._output_text(output), kind)
            return output

        # ---- 缓存 ----
        schema = _OUTPUT_SCHEMAS.get(kind, Dialogue)
        state_json = state.model_dump_json()

        if self._cache:
            cached = self._cache.get(state_json, context, kind, self._director.model_name)
            if cached:
                return NarrativeOutput(
                    kind=kind,
                    dialogue=Dialogue(**cached) if kind == "dialogue" else None,
                    event=Event(**cached) if kind == "event" else None,
                    description=Description(**cached) if kind == "description" else None,
                    tokens_used=0,
                    cached=True,
                    backend=self._director.model_name,
                )

        # ---- AI 生成 ----
        session_ctx = self._memory.session_context() if self._memory else ""
        mem_ctx = self._memory.memory_context(npc_id) if npc_id and self._memory else ""
        npc = state.npcs.get(npc_id) if npc_id else None
        prompt = self._context_mgr.build(state, kind, context, session_ctx, mem_ctx, npc=npc)

        try:
            result, raw, tokens = self._director.generate(
                prompt, schema, kind=kind, npc_mood=npc.mood if npc else "",
            )
        except Exception:
            return self._fallback(kind, npc_id, context)

        text = self._extract_text(result)
        if self._filter and text and not self._filter.validate(text):
            return self._fallback(kind, npc_id, context)

        if self._cache:
            self._cache.set(state_json, context, kind, self._director.model_name, result.model_dump())

        self._record_turn(npc_id, context, text, kind)

        return NarrativeOutput(
            kind=kind,
            dialogue=result if isinstance(result, Dialogue) else None,
            event=result if isinstance(result, Event) else None,
            description=result if isinstance(result, Description) else None,
            tokens_used=tokens,
            cached=False,
            backend=self._director.model_name,
            raw=raw,
        )

    async def tell_async(
        self,
        state: GameState | dict,
        kind: str,
        context: str = "",
        npc_id: str = "",
    ) -> NarrativeOutput:
        """异步版 tell()。与同步版相同的四级流水线。"""
        if isinstance(state, dict):
            state = GameState(**state)

        if npc_id and npc_id not in state.npcs and npc_id in self._npcs:
            state.npcs[npc_id] = self._npcs[npc_id]

        beat = self._beat_manager.check(state, kind=kind, npc_id=npc_id)
        if beat and beat.hand_written:
            self._beat_manager.mark_fired(beat.id)
            await self._beat_manager.asave()
            output = beat.hand_written
            output.cached = False
            output.backend = "storybeat"
            self._record_turn(npc_id, context, self._output_text(output), kind)
            return output

        schema = _OUTPUT_SCHEMAS.get(kind, Dialogue)
        state_json = state.model_dump_json()

        if self._cache:
            cached = await self._cache.aget(state_json, context, kind, self._director.model_name)
            if cached:
                return NarrativeOutput(
                    kind=kind,
                    dialogue=Dialogue(**cached) if kind == "dialogue" else None,
                    event=Event(**cached) if kind == "event" else None,
                    description=Description(**cached) if kind == "description" else None,
                    tokens_used=0,
                    cached=True,
                    backend=self._director.model_name,
                )

        session_ctx = self._memory.session_context() if self._memory else ""
        mem_ctx = self._memory.memory_context(npc_id) if npc_id and self._memory else ""
        npc = state.npcs.get(npc_id) if npc_id else None
        prompt = self._context_mgr.build(state, kind, context, session_ctx, mem_ctx, npc=npc)

        try:
            result, raw, tokens = await self._director.generate_async(
                prompt, schema, kind=kind, npc_mood=npc.mood if npc else "",
            )
        except Exception:
            return self._fallback(kind, npc_id, context)

        text = self._extract_text(result)
        if self._filter and text and not self._filter.validate(text):
            return self._fallback(kind, npc_id, context)

        if self._cache:
            await self._cache.aset(state_json, context, kind, self._director.model_name, result.model_dump())

        self._record_turn(npc_id, context, text, kind)

        return NarrativeOutput(
            kind=kind,
            dialogue=result if isinstance(result, Dialogue) else None,
            event=result if isinstance(result, Event) else None,
            description=result if isinstance(result, Description) else None,
            tokens_used=tokens,
            cached=False,
            backend=self._director.model_name,
            raw=raw,
        )

    def tell_stream(
        self,
        state: GameState | dict,
        kind: str,
        context: str = "",
        npc_id: str = "",
    ):
        """流式叙事生成。锚点命中立即 yield 完整结果，否则 yield 部分模型。"""
        if isinstance(state, dict):
            state = GameState(**state)

        if npc_id and npc_id not in state.npcs and npc_id in self._npcs:
            state.npcs[npc_id] = self._npcs[npc_id]

        # 锚点优先
        beat = self._beat_manager.check(state, kind=kind, npc_id=npc_id)
        if beat and beat.hand_written:
            self._beat_manager.mark_fired(beat.id)
            self._beat_manager.save()
            output = beat.hand_written
            output.cached = False
            output.backend = "storybeat"
            self._record_turn(npc_id, context, self._output_text(output), kind)
            yield output
            return

        # 构建 prompt
        schema = _OUTPUT_SCHEMAS.get(kind, Dialogue)
        session_ctx = self._memory.session_context() if self._memory else ""
        mem_ctx = self._memory.memory_context(npc_id) if npc_id and self._memory else ""
        npc = state.npcs.get(npc_id) if npc_id else None
        prompt = self._context_mgr.build(state, kind, context, session_ctx, mem_ctx, npc=npc)

        # 流式生成
        final_text = ""
        try:
            for partial in self._director.generate_stream(
                prompt, schema, kind=kind, npc_mood=npc.mood if npc else "",
            ):
                yield partial
                part = getattr(partial, "text", None)
                if part:
                    final_text = part
                elif hasattr(partial, "description"):
                    d = getattr(partial, "description", "")
                    if d:
                        final_text = d
        except Exception:
            yield self._fallback(kind, npc_id, context)
            return

        self._record_turn(npc_id, context, final_text, kind)

    async def tell_stream_async(
        self,
        state: GameState | dict,
        kind: str,
        context: str = "",
        npc_id: str = "",
    ):
        """异步流式叙事生成。"""
        if isinstance(state, dict):
            state = GameState(**state)

        if npc_id and npc_id not in state.npcs and npc_id in self._npcs:
            state.npcs[npc_id] = self._npcs[npc_id]

        beat = self._beat_manager.check(state, kind=kind, npc_id=npc_id)
        if beat and beat.hand_written:
            self._beat_manager.mark_fired(beat.id)
            await self._beat_manager.asave()
            output = beat.hand_written
            output.cached = False
            output.backend = "storybeat"
            self._record_turn(npc_id, context, self._output_text(output), kind)
            yield output
            return

        schema = _OUTPUT_SCHEMAS.get(kind, Dialogue)
        session_ctx = self._memory.session_context() if self._memory else ""
        mem_ctx = self._memory.memory_context(npc_id) if npc_id and self._memory else ""
        npc = state.npcs.get(npc_id) if npc_id else None
        prompt = self._context_mgr.build(state, kind, context, session_ctx, mem_ctx, npc=npc)

        final_text = ""
        try:
            async for partial in self._director.generate_stream_async(
                prompt, schema, kind=kind, npc_mood=npc.mood if npc else "",
            ):
                yield partial
                part = getattr(partial, "text", None)
                if part:
                    final_text = part
                elif hasattr(partial, "description"):
                    d = getattr(partial, "description", "")
                    if d:
                        final_text = d
        except Exception:
            yield self._fallback(kind, npc_id, context)
            return

        self._record_turn(npc_id, context, final_text, kind)

    async def load_story_async(self, story_dir: str, chapter: str | None = None) -> None:
        import asyncio
        await asyncio.to_thread(self.load_story, story_dir, chapter)

    def _record_turn(self, npc_id: str, context: str, text: str, kind: str) -> None:
        if not self._memory:
            return
        self._memory.record_turn(npc_id, context, text, kind)
        if npc_id and text.strip():
            self._memory.remember(npc_id, text, kind)

    @staticmethod
    def _output_text(output: NarrativeOutput) -> str:
        if output.dialogue:
            return output.dialogue.text
        if output.event:
            return output.event.description
        if output.description:
            return output.description.text
        return ""

    def _extract_text(self, result: Dialogue | Event | Description) -> str:
        if isinstance(result, Dialogue):
            return result.text
        if isinstance(result, Event):
            return result.description
        if isinstance(result, Description):
            return result.text
        return ""

    def _fallback(self, kind: str, npc_id: str = "", context: str = "") -> NarrativeOutput:
        pool = self._config.fallback_pool.get(kind, [])
        if not pool:
            pool = ["……", "（沉默）", "风吹过，没有人说话。"]

        text = random.choice(pool)

        if kind == "dialogue":
            result = NarrativeOutput(kind=kind, dialogue=Dialogue(text=text), cached=False, backend="fallback")
        elif kind == "event":
            result = NarrativeOutput(kind=kind, event=Event(title="微小的动静", description=text), cached=False, backend="fallback")
        else:
            result = NarrativeOutput(kind=kind, description=Description(text=text), cached=False, backend="fallback")

        self._record_turn(npc_id, context, text, kind)
        return result
