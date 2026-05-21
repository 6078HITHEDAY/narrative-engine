"""异步引擎测试。"""

from unittest.mock import patch

import pytest

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


@pytest.mark.asyncio
async def test_async_anchor_hit():
    """异步锚点命中。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        beats=[StoryBeat(id="async_anchor", trigger={"world.area": "灯塔"}, text="守塔人点了点头。")],
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "灯塔"})

    result = await engine.tell_async(state, kind="dialogue", context="问路")

    assert result.backend == "storybeat"
    assert "守塔人点了点头" in result.dialogue.text


@pytest.mark.asyncio
async def test_async_ai_generates():
    """异步 AI 生成。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    fake_result = Dialogue(text="异步生成的内容")
    async def fake_gen(prompt, schema, **kwargs):
        return fake_result, "raw", 5

    with patch.object(engine._director, "generate_async", side_effect=fake_gen):
        result = await engine.tell_async(state, kind="dialogue", context="测试")

    assert result.dialogue.text == "异步生成的内容"
    assert result.backend == "openai/gpt-test"


@pytest.mark.asyncio
async def test_async_cache_hit(tmp_path):
    """异步缓存命中。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=True,
        cache_dir=str(tmp_path / "cache"),
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    fake_result = Dialogue(text="首次生成")
    call_count = 0

    async def fake_gen(prompt, schema, **kwargs):
        nonlocal call_count
        call_count += 1
        return fake_result, "raw", 3

    with patch.object(engine._director, "generate_async", side_effect=fake_gen):
        r1 = await engine.tell_async(state, kind="dialogue", context="缓存测试")
        r2 = await engine.tell_async(state, kind="dialogue", context="缓存测试")

    assert r1.dialogue.text == "首次生成"
    assert r2.cached is True
    assert call_count == 1


@pytest.mark.asyncio
async def test_async_stream():
    """异步流式生成。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    partials = [
        Dialogue(text="A"),
        Dialogue(text="AB"),
        Dialogue(text="ABC"),
    ]

    async def fake_stream(prompt, schema, **kwargs):
        for p in partials:
            yield p

    with patch.object(engine._director, "generate_stream_async", side_effect=fake_stream):
        parts = []
        async for p in engine.tell_stream_async(state, kind="dialogue", context="测试"):
            parts.append(p)

    assert len(parts) == 3
    assert parts[0].text == "A"
    assert parts[1].text == "AB"
    assert parts[2].text == "ABC"


@pytest.mark.asyncio
async def test_async_stream_anchor():
    """异步流式锚点命中。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        beats=[StoryBeat(id="async_str_anchor", trigger={"world.area": "诊所"}, text="医生抬头。")],
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "诊所"})

    parts = []
    async for p in engine.tell_stream_async(state, kind="dialogue", context="看病"):
        parts.append(p)

    assert len(parts) == 1
    assert isinstance(parts[0], NarrativeOutput)
    assert parts[0].backend == "storybeat"
    assert "医生抬头" in parts[0].dialogue.text


@pytest.mark.asyncio
async def test_async_fallback():
    """异步异常降级。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        fallback_pool={"dialogue": ["异步降级文案"]},
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    async def fake_gen(prompt, schema, **kwargs):
        raise ConnectionError("网络中断")

    with patch.object(engine._director, "generate_async", side_effect=fake_gen):
        result = await engine.tell_async(state, kind="dialogue", context="随便")

    assert result.backend == "fallback"
    assert result.dialogue.text == "异步降级文案"


@pytest.mark.asyncio
async def test_async_stream_fallback():
    """异步流式异常降级。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        fallback_pool={"dialogue": ["流式降级"]},
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    async def fake_stream(prompt, schema, **kwargs):
        raise ConnectionError("中断")
        yield

    with patch.object(engine._director, "generate_stream_async", side_effect=fake_stream):
        parts = []
        async for p in engine.tell_stream_async(state, kind="dialogue", context="测试"):
            parts.append(p)

    assert len(parts) == 1
    assert parts[0].backend == "fallback"
    assert parts[0].dialogue.text == "流式降级"


@pytest.mark.asyncio
async def test_async_records_turn():
    """异步生成后记录 session turn。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        memory_enabled=True,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    async def fake_gen(prompt, schema, **kwargs):
        return Dialogue(text="异步记忆测试"), "raw", 3

    with patch.object(engine._director, "generate_async", side_effect=fake_gen):
        await engine.tell_async(state, kind="dialogue", context="你好", npc_id="npc_a")

    ctx = engine.memory.session_context()
    assert "你好" in ctx
    assert "异步记忆测试" in ctx


@pytest.mark.asyncio
async def test_async_load_story():
    """异步加载故事。"""
    engine = NarrativeEngine()
    await engine.load_story_async("stories/seaside_town")
    assert engine.story_title != ""
    assert engine.current_chapter != ""
    assert len(engine.list_chapters()) > 0
