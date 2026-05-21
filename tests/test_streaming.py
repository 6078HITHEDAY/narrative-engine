"""流式生成测试。"""

from unittest.mock import patch

from narrative_engine import (
    NarrativeEngine,
    EngineConfig,
    LLMBackend,
    ProviderKind,
    GameState,
    WorldState,
    StoryBeat,
    Dialogue,
    NarrativeOutput,
)


def make_state(**kwargs):
    from narrative_engine import PlayerState
    player = PlayerState(**(kwargs.pop("player", {})))
    world = WorldState(**(kwargs.pop("world", {})))
    return GameState(player=player, world=world, **kwargs)


def test_tell_stream_anchor_hits_immediately():
    """锚点命中 → 一次 yield 完整 NarrativeOutput。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        beats=[StoryBeat(id="instant", trigger={"world.area": "test"}, text="手写内容")],
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "test"})

    parts = list(engine.tell_stream(state, kind="dialogue", context="触发"))

    assert len(parts) == 1
    assert isinstance(parts[0], NarrativeOutput)
    assert parts[0].backend == "storybeat"
    assert "手写内容" in parts[0].dialogue.text


def test_tell_stream_yields_partial_models():
    """AI 生成 → 多次 yield 部分模型。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试区"})

    # Mock 流式：yield 3 个 partial
    partials = [
        Dialogue(text="今天"),
        Dialogue(text="今天的鱼"),
        Dialogue(text="今天的鱼不新鲜。", mood_change=0),
    ]

    def fake_stream(prompt, schema, **kwargs):
        for p in partials:
            yield p

    with patch.object(engine._director, "generate_stream", side_effect=fake_stream):
        parts = list(engine.tell_stream(state, kind="dialogue", context="闲聊"))

    assert len(parts) == 3
    assert parts[0].text == "今天"
    assert parts[1].text == "今天的鱼"
    assert parts[2].text == "今天的鱼不新鲜。"


def test_tell_stream_fallback_on_error():
    """流式异常 → yield fallback。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
        fallback_pool={"dialogue": ["网络错误"]},
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    def fake_stream(prompt, schema, **kwargs):
        raise ConnectionError("网络中断")
        yield

    with patch.object(engine._director, "generate_stream", side_effect=fake_stream):
        parts = list(engine.tell_stream(state, kind="dialogue", context="闲聊"))

    assert len(parts) == 1
    assert isinstance(parts[0], NarrativeOutput)
    assert parts[0].backend == "fallback"
    assert parts[0].dialogue.text == "网络错误"


def test_tell_stream_records_turn():
    """流式完成后应记录 session turn。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
        memory_enabled=True,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    def fake_stream(prompt, schema, **kwargs):
        yield Dialogue(text="AI 流式回复")

    with patch.object(engine._director, "generate_stream", side_effect=fake_stream):
        list(engine.tell_stream(state, kind="dialogue", context="你好", npc_id="npc_x"))

    ctx = engine.memory.session_context()
    assert "你好" in ctx
    assert "AI 流式回复" in ctx
