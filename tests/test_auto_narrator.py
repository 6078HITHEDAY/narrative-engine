"""AutoNarrator 单元测试 — mock 路由 LLM，验证四类输入的分发。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from narrative_engine import (
    AutoIntent,
    AutoNarrator,
    GameState,
    NarrativeEngine,
    NarrativeOutput,
    NPCState,
    PlayerState,
    WorldState,
)
from narrative_engine.models.narrative import Description, Dialogue, Event


def _make_engine_with_npc(npc_id: str = "li") -> NarrativeEngine:
    engine = NarrativeEngine()
    engine.set_npc(npc_id, NPCState(id=npc_id, name="老李", traits=["寡言"]))
    return engine


def _patch_router(narrator: AutoNarrator, intent: AutoIntent) -> None:
    async def _fake_route(_user_input: str) -> AutoIntent:
        return intent
    narrator._route = _fake_route  # type: ignore[assignment]


def _patch_tell(engine: NarrativeEngine, output: NarrativeOutput) -> None:
    engine.tell_async = AsyncMock(return_value=output)  # type: ignore[method-assign]


def test_dialogue_intent_calls_tell_with_npc():
    engine = _make_engine_with_npc("li")
    state = GameState(world=WorldState(area="market"), player=PlayerState())
    narrator = AutoNarrator(engine, state)

    _patch_router(narrator, AutoIntent(
        kind="dialogue", npc_id="li",
        rewritten_context="玩家上前问候",
    ))
    out = NarrativeOutput(kind="dialogue", dialogue=Dialogue(text="嗯。"), backend="mock")
    _patch_tell(engine, out)

    intent, result = asyncio.run(narrator.respond("跟老李打个招呼"))

    engine.tell_async.assert_awaited_once_with(
        state, kind="dialogue", context="玩家上前问候", npc_id="li",
    )
    assert intent.npc_id == "li"
    assert result.dialogue.text == "嗯。"


def test_description_intent_no_npc():
    engine = _make_engine_with_npc()
    state = GameState(world=WorldState(area="dock"))
    narrator = AutoNarrator(engine, state)

    _patch_router(narrator, AutoIntent(
        kind="description", rewritten_context="环顾码头",
    ))
    out = NarrativeOutput(kind="description", description=Description(text="海风咸湿。"), backend="mock")
    _patch_tell(engine, out)

    asyncio.run(narrator.respond("看看周围"))

    engine.tell_async.assert_awaited_once_with(
        state, kind="description", context="环顾码头", npc_id="",
    )


def test_new_area_updates_world():
    engine = _make_engine_with_npc()
    state = GameState(world=WorldState(area="house"))
    narrator = AutoNarrator(engine, state)

    _patch_router(narrator, AutoIntent(
        kind="description", rewritten_context="抵达灯塔",
        new_area="lighthouse",
    ))
    _patch_tell(engine, NarrativeOutput(
        kind="description", description=Description(text="..."), backend="mock",
    ))

    asyncio.run(narrator.respond("去灯塔"))

    assert state.world.area == "lighthouse"


def test_event_choices_set_pending():
    engine = _make_engine_with_npc()
    state = GameState()
    narrator = AutoNarrator(engine, state)

    _patch_router(narrator, AutoIntent(kind="event", rewritten_context="尝试推门"))
    event_out = NarrativeOutput(
        kind="event",
        event=Event(title="门后", description="门微微开启。", choices=["推开", "退后"]),
        backend="mock",
    )
    _patch_tell(engine, event_out)

    asyncio.run(narrator.respond("我推一下门"))

    assert narrator.pending_event is not None
    assert narrator.pending_event.choices == ["推开", "退后"]


def test_choice_index_applies_choice_and_clears_pending():
    engine = _make_engine_with_npc()
    state = GameState()
    narrator = AutoNarrator(engine, state)

    pending = Event(title="门后", description="...", choices=["推开", "退后"], consequences={})
    narrator._pending_event = pending

    _patch_router(narrator, AutoIntent(
        kind="description", rewritten_context="选择之后",
        choice_index=0,
    ))
    follow = NarrativeOutput(
        kind="description", description=Description(text="门后是漆黑的。"), backend="mock",
    )
    _patch_tell(engine, follow)

    intent, result = asyncio.run(narrator.respond("我推开"))

    assert narrator.pending_event is None
    assert "推开" in state.player.recent_actions
    engine.tell_async.assert_awaited_once()
    args, kwargs = engine.tell_async.call_args
    assert kwargs["kind"] == "description"
    assert "推开" in kwargs["context"]


def test_choice_index_out_of_range_falls_through():
    engine = _make_engine_with_npc()
    state = GameState()
    narrator = AutoNarrator(engine, state)

    pending = Event(title="x", description="x", choices=["a", "b"], consequences={})
    narrator._pending_event = pending

    _patch_router(narrator, AutoIntent(
        kind="dialogue", rewritten_context="路过",
        choice_index=99,
    ))
    _patch_tell(engine, NarrativeOutput(
        kind="dialogue", dialogue=Dialogue(text="..."), backend="mock",
    ))

    asyncio.run(narrator.respond("不选，继续走"))

    assert narrator.pending_event is pending
    engine.tell_async.assert_awaited_once()
