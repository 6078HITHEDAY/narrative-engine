"""AI 生成全链路测试。

Mock AIDirector.generate 来测试：
- AI 生成 → 解析 → 返回 NarrativeOutput
- 关键词过滤拦截 → 降级 fallback
- 缓存：首次调 AI，相同 state 第二次命中缓存
- 锚点优先（有 AI 时也不走 AI）
"""

from unittest.mock import patch, MagicMock

from narrative_engine import (
    NarrativeEngine,
    EngineConfig,
    LLMBackend,
    ProviderKind,
    GameState,
    WorldState,
    PlayerState,
    StoryBeat,
    Dialogue,
    Description,
)


def make_state(**kwargs) -> GameState:
    player = PlayerState(**(kwargs.pop("player", {})))
    world = WorldState(**(kwargs.pop("world", {})))
    return GameState(player=player, world=world, **kwargs)


# ============ AI 生成 - 对话 ============

def test_ai_generates_dialogue():
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试区"})

    fake_result = Dialogue(text="这是 AI 生成的内容", mood_change=0)
    with patch.object(engine._director, "generate", return_value=(fake_result, '{"text": "..."}', 42)):
        result = engine.tell(state, kind="dialogue", context="测试上下文")

    assert result.backend == "openai/gpt-test"
    assert result.dialogue is not None
    assert "AI 生成" in result.dialogue.text
    assert result.tokens_used == 42
    assert result.cached is False


# ============ AI 生成 - 描述 ============

def test_ai_generates_description():
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "海边"})

    fake_result = Description(text="海风吹过废弃的码头", mood="eerie")
    with patch.object(engine._director, "generate", return_value=(fake_result, "raw", 30)):
        result = engine.tell(state, kind="description", context="海风吹过")

    assert result.backend == "openai/gpt-test"
    assert result.description is not None
    assert "海风" in result.description.text


# ============ 过滤拦截 ============

def test_filter_blocks_banned_keyword():
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        filter_blacklist=["你好我是AI", "CPU"],
        fallback_pool={"dialogue": ["（沉默）"]},
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    fake_result = Dialogue(text="你好我是AI，我不能回答这个问题")
    with patch.object(engine._director, "generate", return_value=(fake_result, "raw", 10)):
        result = engine.tell(state, kind="dialogue", context="测试")

    assert result.backend == "fallback"
    assert result.dialogue.text == "（沉默）"


def test_clean_text_passes_filter():
    """不含禁用词的合法内容直接通过"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        filter_blacklist=["你好我是AI"],
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    fake_result = Dialogue(text="今天鱼不新鲜。")
    with patch.object(engine._director, "generate", return_value=(fake_result, "raw", 5)):
        result = engine.tell(state, kind="dialogue", context="闲聊")

    assert result.backend == "openai/gpt-test"
    assert result.dialogue.text == "今天鱼不新鲜。"


# ============ 缓存 ============

def test_cache_hit_skips_ai_call(tmp_path):
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=True,
        cache_dir=str(tmp_path / "cache"),
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "缓存测试"})

    fake_result = Dialogue(text="AI 回答")
    with patch.object(engine._director, "generate", wraps=engine._director.generate) as spy:
        spy.return_value = (fake_result, "raw", 10)

        r1 = engine.tell(state, kind="dialogue", context="测试")
        assert r1.cached is False
        assert spy.call_count == 1

        r2 = engine.tell(state, kind="dialogue", context="测试")
        assert r2.cached is True
        assert r2.dialogue.text == "AI 回答"
        assert spy.call_count == 1  # 缓存命中，没再调


def test_different_state_goes_to_ai(tmp_path):
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=True,
        cache_dir=str(tmp_path / "cache2"),
    )
    engine = NarrativeEngine(config)

    fake = Dialogue(text="X")
    with patch.object(engine._director, "generate", return_value=(fake, "raw", 10)) as spy:
        engine.tell(make_state(world={"area": "A"}), kind="dialogue")
        engine.tell(make_state(world={"area": "B"}), kind="dialogue")
        assert spy.call_count == 2


# ============ 锚点优先 ============

def test_anchor_beats_ai():
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        beats=[StoryBeat(id="anchor", trigger={"world.area": "test"}, text="手写文案")],
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "test"})

    with patch.object(engine._director, "generate") as spy:
        result = engine.tell(state, kind="dialogue", context="测试")

    assert result.backend == "storybeat"
    assert result.dialogue.text == "手写文案"
    spy.assert_not_called()


# ============ AI 失败 → fallback ============

def test_ai_failure_falls_back():
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        fallback_pool={"dialogue": ["连接丢失"]},
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    with patch.object(engine._director, "generate", side_effect=ConnectionError("网络错误")):
        result = engine.tell(state, kind="dialogue", context="测试")

    assert result.backend == "fallback"
    assert result.dialogue.text == "连接丢失"


# ============ 记忆系统集成 ============

def test_memory_injects_context_into_prompt():
    """连续两次 tell()，第二次 prompt 应包含第一轮的历史。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        memory_enabled=True,
        session_turns=3,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    captured_prompts = []

    def capture_and_return(prompt, schema, **kwargs):
        captured_prompts.append(prompt)
        return Dialogue(text="AI 回复"), "raw", 10

    with patch.object(engine._director, "generate", side_effect=capture_and_return):
        # 第一轮
        engine.tell(state, kind="dialogue", context="你好", npc_id="test_npc")
        # 第二轮
        engine.tell(state, kind="dialogue", context="还记得我吗", npc_id="test_npc")

    assert len(captured_prompts) == 2
    # 第二轮 prompt 应包含第一轮的历史
    assert "你好" in captured_prompts[1]
    assert "AI 回复" in captured_prompts[1]
    assert "最近对话" in captured_prompts[1]


def test_anchor_also_records_turn(tmp_path):
    """锚点命中时也应记录会话轮次。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        beats=[StoryBeat(id="talk", trigger={"world.area": "test"}, text="手写回复")],
        memory_enabled=True,
        cache_enabled=True,
        cache_dir=str(tmp_path / "cache3"),
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "test"})

    # 锚点命中
    engine.tell(state, kind="dialogue", context="触发锚点", npc_id="npc")
    # 再走一次 AI
    fake = Dialogue(text="AI 跟进")
    captured = []

    def capture(prompt, schema, **kwargs):
        captured.append(prompt)
        return fake, "raw", 10

    with patch.object(engine._director, "generate", side_effect=capture):
        engine.tell(state, kind="dialogue", context="继续聊", npc_id="npc")

    assert len(captured) == 1
    assert "触发锚点" in captured[0]
    assert "手写回复" in captured[0]


def test_memory_disabled_no_injection():
    """memory_enabled=False 时 prompt 不应有记忆块。"""
    config = EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="openai/gpt-test"),
        cache_enabled=False,
        memory_enabled=False,
    )
    engine = NarrativeEngine(config)
    state = make_state(world={"area": "测试"})

    captured = []

    def capture(prompt, schema, **kwargs):
        captured.append(prompt)
        return Dialogue(text="回复"), "raw", 10

    with patch.object(engine._director, "generate", side_effect=capture):
        engine.tell(state, kind="dialogue", context="你好", npc_id="test_npc")
        engine.tell(state, kind="dialogue", context="还在吗", npc_id="test_npc")

    assert len(captured) == 2
    assert "最近对话" not in captured[1]
