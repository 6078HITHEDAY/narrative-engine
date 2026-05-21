"""Prompt 策略测试：动态 temperature、NPC persona 注入、自适应重试。"""

from unittest.mock import patch

import pytest

from narrative_engine import (
    NarrativeEngine,
    EngineConfig,
    LLMBackend,
    ProviderKind,
    TemperatureProfile,
    GameState,
    WorldState,
    NPCState,
    Dialogue,
    StoryBeat,
    NarrativeOutput,
)


def make_state(**kwargs):
    from narrative_engine import PlayerState
    player = PlayerState(**(kwargs.pop("player", {})))
    world = WorldState(**(kwargs.pop("world", {})))
    npcs = kwargs.pop("npcs", {})
    return GameState(player=player, world=world, npcs=npcs, **kwargs)


# ---- Temperature 动态调整 ----

def test_temperature_resolve_disabled():
    """禁用时返回 base 温度。"""
    profile = TemperatureProfile(enabled=False)
    assert profile.resolve(0.8, kind="dialogue", npc_mood="angry") == 0.8


def test_temperature_resolve_dialogue_calm():
    """dialogue + calm → 降低温度。"""
    profile = TemperatureProfile()
    t = profile.resolve(0.8, kind="dialogue", npc_mood="calm")
    assert t < 0.8  # -0.05 - 0.1 = -0.15


def test_temperature_resolve_event_excited():
    """event + excited → 提高温度。"""
    profile = TemperatureProfile()
    t = profile.resolve(0.8, kind="event", npc_mood="excited")
    assert t > 0.8  # +0.1 + 0.1 = +0.2


def test_temperature_resolve_unknown_kind():
    """未知 kind/mood → 用 base 不变。"""
    profile = TemperatureProfile()
    t = profile.resolve(0.8, kind="unknown", npc_mood="unknown")
    assert t == 0.8


def test_temperature_resolve_clamped():
    """温度裁剪到 [0.1, 2.0]。"""
    profile = TemperatureProfile(kind_adjustments={"dialogue": -2.0})
    t = profile.resolve(0.5, kind="dialogue")
    assert t == 0.1

    profile2 = TemperatureProfile(kind_adjustments={"event": 5.0})
    t2 = profile2.resolve(0.5, kind="event")
    assert t2 == 2.0


def test_temperature_profile_on_backend():
    """LLMBackend 自带 TemperatureProfile。"""
    backend = LLMBackend(temperature=1.0)
    t = backend.temperature_profile.resolve(backend.temperature, kind="dialogue", npc_mood="angry")
    assert t != backend.temperature


# ---- NPC Persona 注入 ----

def test_persona_in_prompt():
    """有 NPC 时 prompt 包含 persona 描述。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    npc = NPCState(
        id="doc_wang", name="王医生",
        traits=["严谨", "沉默寡言"],
        mood="calm", relationship=0.3,
    )
    state = make_state(world={"area": "诊所"}, npcs={"doc_wang": npc})

    # 拦截 prompt 而不是 mock LLM
    prompt_captured = []

    def capture_and_return(prompt, schema, **kwargs):
        prompt_captured.append(prompt)
        return Dialogue(text="请坐。"), "raw", 3

    with patch.object(engine._director, "generate", side_effect=capture_and_return):
        engine.tell(state, kind="dialogue", context="看病", npc_id="doc_wang")

    assert len(prompt_captured) == 1
    prompt = prompt_captured[0]
    assert "王医生" in prompt
    assert "严谨" in prompt
    assert "沉默寡言" in prompt


def test_no_npc_no_persona():
    """无 NPC 时 prompt 不含 persona 区块。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "码头"})

    prompt_captured = []

    def capture_and_return(prompt, schema, **kwargs):
        prompt_captured.append(prompt)
        return Dialogue(text="你好。"), "raw", 3

    with patch.object(engine._director, "generate", side_effect=capture_and_return):
        engine.tell(state, kind="dialogue", context="打招呼")

    prompt = prompt_captured[0]
    assert "## 你的角色" not in prompt


def test_npc_mood_in_director_call():
    """NPC mood 被传给 director 的 kind/npc_mood 参数。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    npc = NPCState(id="angry_li", name="暴躁老李", mood="angry", traits=["暴躁"])
    state = make_state(world={"area": "码头"}, npcs={"angry_li": npc})

    call_kwargs = {}

    def capture_kwargs(prompt, schema, **kwargs):
        call_kwargs.update(kwargs)
        return Dialogue(text="滚！"), "raw", 3

    with patch.object(engine._director, "generate", side_effect=capture_kwargs):
        engine.tell(state, kind="dialogue", context="问路", npc_id="angry_li")

    assert call_kwargs.get("kind") == "dialogue"
    assert call_kwargs.get("npc_mood") == "angry"


# ---- 自适应重试 ----

def test_retry_succeeds_on_second_attempt():
    """第一次失败、第二次成功 → 返回结果。"""
    from narrative_engine.core.director import AIDirector

    backend = LLMBackend(provider=ProviderKind.openai, model="gpt-test", temperature=0.8)
    director = AIDirector(backend)

    call_count = 0

    def flaky_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("网络中断")
        # 第二次成功
        fake_result = Dialogue(text="重试后结果")
        fake_raw = type("Raw", (), {
            "usage": type("Usage", (), {"total_tokens": 5})(),
            "choices": [type("Choice", (), {"message": type("Msg", (), {"content": "raw text"})()})()],
        })()
        return fake_result, fake_raw

    with patch.object(director._client, "create_with_completion", side_effect=flaky_create):
        result, raw_text, tokens = director.generate("test prompt", Dialogue)

    assert call_count == 2
    assert result.text == "重试后结果"


def test_retry_exhausted_raises():
    """两次都失败 → 上抛异常。"""
    from narrative_engine.core.director import AIDirector

    backend = LLMBackend(provider=ProviderKind.openai, model="gpt-test", temperature=0.8)
    director = AIDirector(backend)

    def always_fail(**kwargs):
        raise ConnectionError("持续中断")

    with patch.object(director._client, "create_with_completion", side_effect=always_fail):
        with pytest.raises(ConnectionError):
            director.generate("test prompt", Dialogue)


def test_retry_triggers_fallback_in_engine():
    """engine 层：retry 耗尽后走 fallback。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
        fallback_pool={"dialogue": ["重试失败降级"]},
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    def always_fail(prompt, schema, **kwargs):
        raise ConnectionError("中断")

    with patch.object(engine._director, "generate", side_effect=always_fail):
        result = engine.tell(state, kind="dialogue", context="测试")

    assert result.backend == "fallback"
    assert result.dialogue.text == "重试失败降级"


@pytest.mark.asyncio
async def test_async_retry_succeeds_on_second_attempt():
    """异步重试：第一次失败第二次成功。"""
    from narrative_engine.core.director import AIDirector

    backend = LLMBackend(provider=ProviderKind.openai, model="gpt-test", temperature=0.8)
    director = AIDirector(backend)

    call_count = 0

    async def flaky_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("异步中断")
        fake_result = Dialogue(text="异步重试成功")
        fake_raw = type("Raw", (), {
            "usage": type("Usage", (), {"total_tokens": 3})(),
            "choices": [type("Choice", (), {"message": type("Msg", (), {"content": "raw"})()})()],
        })()
        return fake_result, fake_raw

    with patch.object(director._async_client, "create_with_completion", side_effect=flaky_create):
        result, raw_text, tokens = await director.generate_async("test", Dialogue)

    assert call_count == 2
    assert result.text == "异步重试成功"


# ---- Temperature via engine ----

def test_temperature_passed_to_director():
    """engine 把 kind/npc_mood 传给 director，_resolve_temperature 被调用。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test", temperature=0.8),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    npc = NPCState(id="calm_npc", name="冷静NPC", mood="calm", traits=["冷静"])
    state = make_state(world={"area": "测试"}, npcs={"calm_npc": npc})

    captured_kwargs = {}

    def capture(prompt, schema, **kwargs):
        captured_kwargs.update(kwargs)
        return Dialogue(text="嗯。"), "raw", 3

    with patch.object(engine._director, "generate", side_effect=capture):
        engine.tell(state, kind="dialogue", context="闲聊", npc_id="calm_npc")

    assert captured_kwargs.get("kind") == "dialogue"
    assert captured_kwargs.get("npc_mood") == "calm"

    # 验证 temperature 实际被正确计算（通过 TemperatureProfile 单元测试覆盖）
