"""真实 LLM 集成测试。

默认 `pytest` 会跳过本文件（pyproject.toml 设了 -m 'not integration'）。
显式触发：

    NARRATIVE_API_KEY=sk-xxx \
    NARRATIVE_API_BASE=https://api.deepseek.com \
    NARRATIVE_MODEL=deepseek-v4-pro \
        pytest -m integration -v

验证「引擎通用能力」而非 stories/seaside_town 的具体内容。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from narrative_engine import (
    GameState,
    NarrativeEngine,
    PlayerState,
    WorldState,
)
from narrative_engine.generators import StoryGenerator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("NARRATIVE_API_KEY"),
        reason="需要 NARRATIVE_API_KEY",
    ),
]


@pytest.fixture
def engine() -> NarrativeEngine:
    e = NarrativeEngine.from_story("stories/seaside_town")
    e.reset_beats()
    if e.memory:
        e.memory.clear()
    return e


@pytest.fixture
def generic_state() -> GameState:
    """不依赖具体故事的通用状态——area 为空让锚点不命中，强制走 LLM。"""
    return GameState(
        player=PlayerState(name="player"),
        world=WorldState(area="random_area_no_beat", time="afternoon"),
    )


def test_dialogue_returns_valid_output(engine, generic_state):
    """通用：LLM 应返回非空 dialogue.text 且未降级。"""
    npc_id = next(iter(engine.npcs))
    result = engine.tell(generic_state, kind="dialogue", context="问候", npc_id=npc_id)
    assert result.backend != "fallback", f"降级了: {result.error}"
    assert result.dialogue is not None
    assert result.dialogue.text.strip()


def test_event_returns_choices(engine, generic_state):
    """通用：event.choices 应至少 2 条、每条非空。"""
    result = engine.tell(generic_state, kind="event", context="环顾四周")
    assert result.backend != "fallback", f"降级了: {result.error}"
    assert result.event is not None
    assert len(result.event.choices) >= 2
    assert all(c.strip() for c in result.event.choices)


def test_description_returns_text(engine, generic_state):
    """通用：description.text 应非空。"""
    result = engine.tell(generic_state, kind="description", context="刚到达")
    assert result.backend != "fallback", f"降级了: {result.error}"
    assert result.description is not None
    assert result.description.text.strip()


def test_apply_choice_recorded_and_next_tell_works(engine, generic_state):
    """apply_choice 后 recent_actions 应有记录，下一轮 tell 仍能跑通。"""
    event_result = engine.tell(generic_state, kind="event", context="探索")
    assert event_result.event is not None
    choice = event_result.event.choices[0]

    engine.apply_choice(generic_state, event_result.event, choice)
    assert generic_state.player.recent_actions[-1] == choice

    follow = engine.tell(generic_state, kind="description", context="选完之后")
    assert follow.backend != "fallback", f"降级了: {follow.error}"


def test_cache_hit_zero_cost_second_call(engine, generic_state):
    """相同 state + context 第二次调用应 cached=True, tokens_used=0。"""
    r1 = engine.tell(generic_state, kind="description", context="测试缓存")
    assert r1.backend != "fallback"
    r2 = engine.tell(generic_state, kind="description", context="测试缓存")
    assert r2.cached is True
    assert r2.tokens_used == 0


def test_story_generator_produces_loadable_story(tmp_path: Path):
    """生成器：一段灵感 → 完整目录 → 立即能加载并跑通一次 tell。"""
    out = tmp_path / "generated_story"
    gen = StoryGenerator()
    gen.generate(
        "一个小镇上突然下起红色的雨，居民开始失踪",
        out,
        num_npcs=2,
        num_beats=3,
    )

    assert (out / "story.yaml").is_file()
    assert (out / "npcs.yaml").is_file()
    assert (out / "chapters" / "chapter_1.yaml").is_file()

    new_engine = NarrativeEngine.from_story(str(out))
    new_engine.reset_beats()
    assert new_engine.story_title
    assert new_engine.npcs

    sample_area = ""
    for chapter in new_engine._chapters.values():
        for beat in chapter.beats:
            area = beat.trigger.get("world.area")
            if isinstance(area, str) and not area.startswith("/"):
                sample_area = area
                break
        if sample_area:
            break

    state = GameState(world=WorldState(area=sample_area or "any"))
    result = new_engine.tell(state, kind="description", context="开场")
    assert result.backend != "fallback", f"生成的故事跑不通: {result.error}"
    assert result.description is not None
    assert result.description.text.strip()
