"""StoryGenerator mock 单测：不调真实 LLM，验证写盘 + 落盘后能被 StoryLoader 加载。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from narrative_engine.core.story_loader import StoryLoader
from narrative_engine.generators import StoryGenerator
from narrative_engine.models.config import LLMBackend, ProviderKind
from narrative_engine.models.generated import (
    GeneratedBeat,
    GeneratedChapter,
    GeneratedNPC,
    GeneratedStory,
)
from narrative_engine.generators.story_generator import DEFAULT_GENERATOR_MAX_TOKENS


def _fake_story() -> GeneratedStory:
    return GeneratedStory(
        title="测试故事",
        setting="一个用于测试的虚构小镇。",
        tone="neutral",
        era="近代",
        fallback_dialogue=["……", "（沉默）", "他没回答。"],
        fallback_event=["远处响了一声", "树叶动了一下", "有什么经过"],
        fallback_description=["夜色降临", "风带着凉意", "街灯昏黄"],
        npcs=[
            GeneratedNPC(
                id="npc_a", name="A 先生", mood="calm",
                traits=["稳重", "话少"],
                preset_memories=[{"content": "记得玩家", "importance": 5}],
            ),
            GeneratedNPC(id="npc_b", name="B 小姐", traits=["活泼"]),
        ],
        chapters=[
            GeneratedChapter(
                title="第一章",
                world_setting="主舞台",
                tone="neutral",
                area="main",
                time="midnight",
                weather="rain",
                chapter="chapter_1",
                beats=[
                    GeneratedBeat(
                        id="b1", kind="description", priority=100,
                        trigger={"world.area": "main"},
                        text="开场。", mood="neutral",
                    ),
                    GeneratedBeat(
                        id="b2", kind="dialogue", priority=50,
                        trigger={"_npc_id": "npc_a"},
                        text="你好。",
                    ),
                    GeneratedBeat(
                        id="b3", kind="event", priority=60,
                        trigger={"world.area": "main"},
                        event_title="小事件",
                        text="发生了一些事。",
                        event_choices=["选 A", "选 B"],
                        event_consequences={"选 A": "好结果", "选 B": "坏结果"},
                    ),
                ],
            ),
        ],
    )


def _make_generator() -> StoryGenerator:
    backend = LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test")
    return StoryGenerator(backend=backend)


def test_generate_writes_three_files(tmp_path: Path):
    gen = _make_generator()
    out = tmp_path / "test_story"
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        result_path = gen.generate("测试灵感", out)

    assert result_path == out
    assert (out / "story.yaml").is_file()
    assert (out / "npcs.yaml").is_file()
    assert (out / "chapters" / "chapter_1.yaml").is_file()


def test_generator_env_backend_uses_large_default_max_tokens(monkeypatch):
    monkeypatch.setenv("NARRATIVE_API_KEY", "test-key")
    monkeypatch.delenv("NARRATIVE_GENERATOR_MAX_TOKENS", raising=False)

    backend = StoryGenerator._backend_from_env()

    assert backend is not None
    assert backend.max_tokens == DEFAULT_GENERATOR_MAX_TOKENS


def test_generator_env_backend_allows_max_tokens_override(monkeypatch):
    monkeypatch.setenv("NARRATIVE_API_KEY", "test-key")
    monkeypatch.setenv("NARRATIVE_GENERATOR_MAX_TOKENS", "12345")

    backend = StoryGenerator._backend_from_env()

    assert backend is not None
    assert backend.max_tokens == 12345


def test_generated_story_loadable_by_story_loader(tmp_path: Path):
    gen = _make_generator()
    out = tmp_path / "round_trip"
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        gen.generate("测试", out)

    meta, npcs, chapters = StoryLoader(str(out)).load()

    assert meta.title == "测试故事"
    assert meta.default_world.tone == "neutral"
    assert "npc_a" in npcs
    assert npcs["npc_a"].name == "A 先生"
    assert "chapter_1" in chapters
    assert len(chapters["chapter_1"].beats) == 3


def test_generate_refuses_existing_dir(tmp_path: Path):
    gen = _make_generator()
    out = tmp_path / "existing"
    out.mkdir()
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        with pytest.raises(FileExistsError):
            gen.generate("测试", out)


def test_generate_overwrite_allowed(tmp_path: Path):
    gen = _make_generator()
    out = tmp_path / "existing"
    out.mkdir()
    (out / "stale.yaml").write_text("old")
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        gen.generate("测试", out, overwrite=True)
    assert (out / "story.yaml").is_file()


def test_num_npcs_and_beats_in_prompt(tmp_path: Path):
    gen = _make_generator()
    captured = []

    def capture(prompt, schema, **kwargs):
        captured.append(prompt)
        return _fake_story(), "raw", 100

    with patch.object(gen._director, "generate", side_effect=capture):
        gen.generate("测试", tmp_path / "out", num_npcs=7, num_beats=9)

    assert len(captured) == 1
    prompt = captured[0]
    assert "7" in prompt
    assert "9" in prompt


def test_event_beat_choices_persisted(tmp_path: Path):
    gen = _make_generator()
    out = tmp_path / "story"
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        gen.generate("测试", out)

    _, _, chapters = StoryLoader(str(out)).load()
    event_beat = next(b for b in chapters["chapter_1"].beats if b.id == "b3")
    assert event_beat.kind == "event"
    assert event_beat.event_choices == ["选 A", "选 B"]
    assert event_beat.event_consequences == {"选 A": "好结果", "选 B": "坏结果"}


def test_chapter_world_fields_persisted(tmp_path: Path):
    gen = _make_generator()
    out = tmp_path / "story"
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        gen.generate("测试", out)

    _, _, chapters = StoryLoader(str(out)).load()
    world = chapters["chapter_1"].world
    assert world.area == "main"
    assert world.time == "midnight"
    assert world.weather == "rain"
    assert world.chapter == "chapter_1"


def test_generated_story_immediately_runnable(tmp_path: Path):
    """生成后能被 NarrativeEngine.from_story() 加载并跑 tell（mock LLM）。"""
    from narrative_engine import GameState, NarrativeEngine, WorldState
    from narrative_engine.models.narrative import Description

    gen = _make_generator()
    out = tmp_path / "playable"
    with patch.object(gen._director, "generate", return_value=(_fake_story(), "raw", 100)):
        gen.generate("测试", out)

    engine = NarrativeEngine.from_story(str(out))

    state = GameState(world=WorldState(area="main"))
    result = engine.tell(state, kind="description", context="开场")
    assert result.description is not None
    assert result.backend == "storybeat"
    assert result.description.text == "开场。"
