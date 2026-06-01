"""AI 总编剧：根据用户灵感一次性生成完整 stories/<name>/ 目录。

LLM 一次输出 GeneratedStory（schema 见 models/generated.py），由 _write_story_dir 落盘为：
    stories/<name>/
      ├── story.yaml
      ├── npcs.yaml
      └── chapters/chapter_1.yaml ... chapter_N.yaml

落盘后立即可被 NarrativeEngine.from_story() 加载。
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from jinja2 import Environment, PackageLoader

from narrative_engine._env import backend_from_env
from narrative_engine.core.director import AIDirector
from narrative_engine.models.config import LLMBackend
from narrative_engine.models.generated import GeneratedStory

logger = logging.getLogger(__name__)

DEFAULT_GENERATOR_MAX_TOKENS = 8192


class StoryGenerator:
    """根据自然语言灵感生成完整故事目录。"""

    def __init__(self, backend: LLMBackend | None = None) -> None:
        self._backend = backend or self._backend_from_env() or LLMBackend(
            max_tokens=DEFAULT_GENERATOR_MAX_TOKENS,
        )
        self._director = AIDirector(self._backend)
        self._env = Environment(loader=PackageLoader("narrative_engine", "prompts"))

    @staticmethod
    def _backend_from_env() -> LLMBackend | None:
        return backend_from_env(
            max_tokens_env="NARRATIVE_GENERATOR_MAX_TOKENS",
            default_max_tokens=DEFAULT_GENERATOR_MAX_TOKENS,
        )

    def generate(
        self,
        idea: str,
        out_dir: str | Path,
        *,
        num_npcs: int = 3,
        num_beats: int = 5,
        overwrite: bool = False,
    ) -> Path:
        """同步生成。返回写入的目录 Path。"""
        story = self._invoke_llm(idea, num_npcs, num_beats)
        return self._write_story_dir(story, Path(out_dir), overwrite)

    async def generate_async(
        self,
        idea: str,
        out_dir: str | Path,
        *,
        num_npcs: int = 3,
        num_beats: int = 5,
        overwrite: bool = False,
    ) -> Path:
        story = await self._invoke_llm_async(idea, num_npcs, num_beats)
        return self._write_story_dir(story, Path(out_dir), overwrite)

    def _build_prompt(self, idea: str, num_npcs: int, num_beats: int) -> str:
        template = self._env.get_template("story_generator.j2")
        return template.render(idea=idea, num_npcs=num_npcs, num_beats=num_beats)

    def _invoke_llm(self, idea: str, num_npcs: int, num_beats: int) -> GeneratedStory:
        prompt = self._build_prompt(idea, num_npcs, num_beats)
        result, _, tokens = self._director.generate(prompt, GeneratedStory)
        logger.info("Story generated (tokens=%d, npcs=%d, chapters=%d)",
                    tokens, len(result.npcs), len(result.chapters))
        return result

    async def _invoke_llm_async(self, idea: str, num_npcs: int, num_beats: int) -> GeneratedStory:
        prompt = self._build_prompt(idea, num_npcs, num_beats)
        result, _, tokens = await self._director.generate_async(prompt, GeneratedStory)
        logger.info("Story generated async (tokens=%d, npcs=%d, chapters=%d)",
                    tokens, len(result.npcs), len(result.chapters))
        return result

    @staticmethod
    def _write_story_dir(story: GeneratedStory, out_dir: Path, overwrite: bool) -> Path:
        if out_dir.exists():
            if not overwrite:
                raise FileExistsError(
                    f"目录已存在: {out_dir}（用 overwrite=True 强制覆盖）",
                )
        out_dir.mkdir(parents=True, exist_ok=True)
        chapters_dir = out_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)

        story_yaml = {
            "title": story.title,
            "default_world": {
                "setting": story.setting,
                "tone": story.tone,
                "era": story.era,
            },
            "default_fallback": {
                "dialogue": story.fallback_dialogue,
                "event": story.fallback_event,
                "description": story.fallback_description,
            },
        }
        _dump_yaml(out_dir / "story.yaml", story_yaml)

        npcs_yaml = {
            "npcs": {
                npc.id: {
                    k: v for k, v in {
                        "name": npc.name,
                        "mood": npc.mood,
                        "traits": npc.traits,
                        "relationship": npc.relationship,
                        "preset_memories": npc.preset_memories,
                    }.items() if v not in ("", [], {}, None)
                }
                for npc in story.npcs
            }
        }
        _dump_yaml(out_dir / "npcs.yaml", npcs_yaml)

        for idx, chapter in enumerate(story.chapters, 1):
            beats_data = []
            for beat in chapter.beats:
                entry: dict = {
                    "id": beat.id,
                    "kind": beat.kind,
                    "priority": beat.priority,
                    "trigger": beat.trigger,
                }
                if beat.text:
                    entry["text"] = beat.text
                if beat.mood and beat.mood != "neutral":
                    entry["mood"] = beat.mood
                if beat.event_title:
                    entry["event_title"] = beat.event_title
                if beat.event_choices:
                    entry["event_choices"] = beat.event_choices
                if beat.event_consequences:
                    entry["event_consequences"] = beat.event_consequences
                beats_data.append(entry)

            world = {
                k: v for k, v in {
                    "setting": chapter.world_setting,
                    "tone": chapter.tone,
                    "area": chapter.area,
                    "time": chapter.time,
                    "weather": chapter.weather,
                    "chapter": chapter.chapter,
                }.items() if v not in ("", [], {}, None)
            }
            chapter_yaml = {
                k: v for k, v in {
                    "title": chapter.title,
                    "world": world,
                    "beats": beats_data,
                }.items() if v not in ("", [], {}, None)
            }
            _dump_yaml(chapters_dir / f"chapter_{idx}.yaml", chapter_yaml)

        return out_dir


def _dump_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
