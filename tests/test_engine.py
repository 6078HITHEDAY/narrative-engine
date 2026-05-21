"""NarrativeEngine 集成测试。

覆盖: 锚点优先 / fallback / StoryBeat 简写 / 持久化 roundtrip
"""

import json
import tempfile
from pathlib import Path

import pytest
from narrative_engine import (
    NarrativeEngine,
    BeatManager,
    StoryBeat,
    GameState,
    WorldState,
    PlayerState,
    NPCState,
    EngineConfig,
)


def make_state(**kwargs) -> GameState:
    player = PlayerState(**(kwargs.pop("player", {})))
    world = WorldState(**(kwargs.pop("world", {})))
    npcs = {n.id: n for n in kwargs.pop("npcs", [])}
    return GameState(player=player, world=world, npcs=npcs, **kwargs)


# ============ 锚点优先 ============

def test_anchor_hit_returns_handwritten_text():
    """StoryBeat 命中 → 返回手写文案，backend='storybeat'"""
    config = EngineConfig(beats=[
        StoryBeat(
            id="opening",
            kind="description",
            trigger={"world.area": "grandma_house"},
            text="你站在老房子前，相机挂在脖子上。",
            mood="eerie",
        ),
    ])
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "grandma_house"})

    result = engine.tell(state, kind="description", context="玩家到达")

    assert result.description is not None
    assert "老房子" in result.description.text
    assert result.description.mood == "eerie"
    assert result.backend == "storybeat"
    assert result.cached is False


def test_anchor_marks_fired():
    """锚点触发后应在 fired 集合中，不会重复触发。"""
    config = EngineConfig(beats=[
        StoryBeat(id="once_beat", once=True, trigger={"world.area": "test"}, text="..."),
    ])
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "test"})

    r1 = engine.tell(state, kind="dialogue")
    assert r1.backend == "storybeat"
    assert "once_beat" in engine.beat_manager.fired

    # 再次调用应走 fallback（锚点已触发，不会再命中）
    r2 = engine.tell(state, kind="dialogue")
    assert r2.backend != "storybeat"


def test_no_anchor_falls_through():
    """无锚点命中时、无 API key → fallback"""
    config = EngineConfig(beats=[
        StoryBeat(id="specific", trigger={"world.area": "nowhere_land"}, text="..."),
    ])
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "random_place"})

    result = engine.tell(state, kind="dialogue", context="闲聊")
    # 应走 fallback（无 API key + 无锚点）
    assert result.backend in ("fallback", "deepseek")  # 有 API key 时走 deepseek


# ============ StoryBeat 简写 ============

def test_shorthand_dialogue():
    beat = StoryBeat(id="s1", kind="dialogue", text="你好。", mood_change=-2, unlock_hint="key_found")
    assert beat.hand_written is not None
    assert beat.hand_written.dialogue is not None
    assert beat.hand_written.dialogue.text == "你好。"
    assert beat.hand_written.dialogue.mood_change == -2
    assert beat.hand_written.dialogue.unlock_hint == "key_found"


def test_shorthand_description():
    beat = StoryBeat(id="s2", kind="description", text="海风带着咸味。", mood="eerie")
    assert beat.hand_written.description is not None
    assert beat.hand_written.description.text == "海风带着咸味。"
    assert beat.hand_written.description.mood == "eerie"


def test_shorthand_event():
    beat = StoryBeat(
        id="s3", kind="event",
        event_title="突如其来的敲门声",
        text="门外传来三声沉重的敲击。",
        event_choices=["开门", "从窗户偷看"],
        event_consequences={"开门": "门外空无一人", "从窗户偷看": "一个黑影闪过"},
    )
    assert beat.hand_written.event is not None
    assert beat.hand_written.event.title == "突如其来的敲门声"
    assert beat.hand_written.event.description == "门外传来三声沉重的敲击。"
    assert len(beat.hand_written.event.choices) == 2


def test_shorthand_all_kind():
    beat = StoryBeat(id="s4", kind="all",
                     text="通用文本", event_title="事件标题",
                     mood="tense", mood_change=-1)
    assert beat.hand_written.dialogue is not None
    assert beat.hand_written.dialogue.text == "通用文本"
    assert beat.hand_written.event is not None
    assert beat.hand_written.event.title == "事件标题"
    assert beat.hand_written.description is not None
    assert beat.hand_written.description.mood == "tense"


def test_full_hand_written_overrides_shorthand():
    """当 hand_written 显式提供时，简写字段被忽略。"""
    from narrative_engine.models.narrative import NarrativeOutput, Dialogue

    explicit = NarrativeOutput(kind="dialogue", dialogue=Dialogue(text="显式文案"))
    beat = StoryBeat(
        id="s5", kind="dialogue",
        hand_written=explicit,
        text="这条被忽略",
    )
    assert beat.hand_written.dialogue.text == "显式文案"


# ============ 持久化 roundtrip ============

def test_persistence_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "story_state.json"

        # 第一个引擎：触发锚点，自动保存
        engine1 = NarrativeEngine(EngineConfig(
            beats=[StoryBeat(id="beat1", trigger={"world.area": "test"}, text="...")],
            state_path=str(state_file),
        ))
        engine1.tell(make_state(world={"area": "test"}), kind="dialogue")
        assert state_file.exists()

        # 第二个引擎：从同一个文件加载
        engine2 = NarrativeEngine(EngineConfig(
            beats=[StoryBeat(id="beat1", trigger={"world.area": "test"}, text="...")],
            state_path=str(state_file),
        ))
        assert "beat1" in engine2.beat_manager.fired

        # 再次调用应不触发锚点
        result = engine2.tell(make_state(world={"area": "test"}), kind="dialogue")
        assert result.backend != "storybeat"


# ============ BeatManager.parse_beats_yaml ============

def test_parse_beats_yaml():
    import tempfile, yaml
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"beats": [
            {"id": "b1", "kind": "description", "text": "测试", "trigger": {"world.area": "test"}},
            {"id": "b2", "kind": "dialogue", "text": "测试2", "trigger": {"_npc_id": "test_npc"}},
        ]}, f)
        f.flush()
        path = f.name

    try:
        beats = BeatManager.parse_beats_yaml(path)
        assert len(beats) == 2
        assert beats[0].id == "b1"
        assert beats[0].hand_written.description.text == "测试"
        assert beats[1].id == "b2"
        assert beats[1].hand_written.dialogue.text == "测试2"
    finally:
        Path(path).unlink()


# ============ cache 行为 ============

def test_anchor_skips_cache():
    """锚点命中时不应查缓存，直接返回手写内容。"""
    config = EngineConfig(
        beats=[StoryBeat(id="a", trigger={"world.area": "test"}, text="手写")],
        cache_enabled=True,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "test"})

    result = engine.tell(state, kind="dialogue")
    assert result.backend == "storybeat"
    assert result.cached is False
