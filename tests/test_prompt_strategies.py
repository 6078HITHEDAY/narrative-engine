"""Prompt 策略测试：动态 temperature、NPC persona 注入、自适应重试。"""

from unittest.mock import patch

import pytest

from narrative_engine import (
    NarrativeEngine,
    DirectorError,
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
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
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
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
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
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
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

    backend = LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test", temperature=0.8)
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

    backend = LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test", temperature=0.8)
    director = AIDirector(backend)

    def always_fail(**kwargs):
        raise ConnectionError("持续中断")

    with patch.object(director._client, "create_with_completion", side_effect=always_fail):
        with pytest.raises(DirectorError) as exc_info:
            director.generate("test prompt", Dialogue)
        assert "持续中断" in str(exc_info.value)
        assert exc_info.value.model == "openai/gpt-test"
        assert exc_info.value.provider == "openai"


def test_retry_triggers_fallback_in_engine():
    """engine 层：retry 耗尽后走 fallback。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
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

    backend = LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test", temperature=0.8)
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
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test", temperature=0.8),
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


# ---- Inventory + recent_actions 注入 ----

def _capture_prompt(engine, state, kind="dialogue", **kwargs):
    captured = []

    def capture(prompt, schema, **_):
        captured.append(prompt)
        return Dialogue(text="..."), "raw", 1

    with patch.object(engine._director, "generate", side_effect=capture):
        engine.tell(state, kind=kind, **kwargs)
    return captured[0]


def test_inventory_injected_into_dialogue_prompt():
    """非空 inventory 应在 dialogue prompt 中显式出现。"""
    from narrative_engine import PlayerState

    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(
        player={"inventory": ["旧相机", "奶奶的钥匙"]},
        world={"area": "市场"},
    )
    prompt = _capture_prompt(engine, state, kind="dialogue", context="问路")
    assert "玩家持有" in prompt
    assert "旧相机" in prompt
    assert "奶奶的钥匙" in prompt


def test_recent_actions_injected_takes_last_three():
    """recent_actions 注入时应只取最后 3 条。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(
        player={"recent_actions": ["a1", "a2", "a3", "a4", "a5"]},
        world={"area": "市场"},
    )
    prompt = _capture_prompt(engine, state, kind="event", context="转一圈")
    assert "最近行动" in prompt
    section = prompt.split("最近行动：", 1)[1].split("\n", 1)[0]
    assert "a3" in section and "a4" in section and "a5" in section
    assert "a1" not in section and "a2" not in section


def test_empty_inventory_no_section():
    """空 inventory 时不应出现「玩家持有」段落，避免污染 prompt。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "市场"})
    prompt = _capture_prompt(engine, state, kind="description", context="环顾")
    assert "玩家持有" not in prompt
    assert "最近行动" not in prompt


def test_inventory_in_all_three_kinds():
    """三种 kind 的内置模板都应注入 inventory。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(player={"inventory": ["数据卡"]}, world={"area": "酒吧"})
    for kind in ("dialogue", "event", "description"):
        prompt = _capture_prompt(engine, state, kind=kind, context="...")
        assert "数据卡" in prompt, f"{kind} prompt 未注入 inventory"


# ---- apply_choice ----

def test_apply_choice_appends_to_recent_actions():
    """选择应追加到 recent_actions。"""
    from narrative_engine import Event

    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "码头"})
    event = Event(title="夜里的动静", description="...", choices=["举起相机", "后退"])

    engine.apply_choice(state, event, "举起相机")

    assert state.player.recent_actions == ["举起相机"]


def test_apply_choice_appends_to_history_with_consequence():
    """history 应包含「事件「...」：选择了「...」→ 后果」。"""
    from narrative_engine import Event

    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "码头"})
    event = Event(
        title="夜里的动静",
        description="...",
        choices=["举起相机", "后退"],
        consequences={"举起相机": "拍到了奇怪的影子"},
    )

    engine.apply_choice(state, event, "举起相机")

    assert len(state.history) == 1
    line = state.history[0]
    assert "事件「夜里的动静」" in line
    assert "举起相机" in line
    assert "拍到了奇怪的影子" in line


def test_apply_choice_history_without_consequence():
    """没有 consequences 映射时仍能写入 history。"""
    from narrative_engine import Event

    engine = NarrativeEngine(EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    ))
    state = make_state(world={"area": "码头"})
    event = Event(title="无果之事", description="...", choices=["A", "B"])

    engine.apply_choice(state, event, "B")

    assert state.history == ["事件「无果之事」：选择了「B」"]


def test_apply_choice_invalid_raises():
    """choice 不在 event.choices 中应抛 ValueError。"""
    from narrative_engine import Event

    engine = NarrativeEngine(EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    ))
    state = make_state(world={"area": "码头"})
    event = Event(title="t", description="d", choices=["A", "B"])

    with pytest.raises(ValueError, match="无效选项"):
        engine.apply_choice(state, event, "C")


def test_apply_choice_returns_same_state():
    """返回的应是同一个 state 对象，方便链式调用。"""
    from narrative_engine import Event

    engine = NarrativeEngine(EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    ))
    state = make_state(world={"area": "码头"})
    event = Event(title="t", description="d", choices=["A"])

    returned = engine.apply_choice(state, event, "A")
    assert returned is state


def test_apply_choice_then_next_tell_sees_action():
    """apply_choice 之后，下一轮 tell 的 prompt 应包含该选择。"""
    from narrative_engine import Event

    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "码头"})
    event = Event(title="t", description="d", choices=["举起相机"])

    engine.apply_choice(state, event, "举起相机")
    prompt = _capture_prompt(engine, state, kind="description", context="拍完之后")
    assert "举起相机" in prompt
