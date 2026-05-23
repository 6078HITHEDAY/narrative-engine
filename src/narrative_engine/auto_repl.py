"""自然语言交互 REPL — CLI play 子命令和 examples/auto_demo.py 共用。"""

from __future__ import annotations

import asyncio

from narrative_engine.core.auto_narrator import AutoNarrator
from narrative_engine.core.engine import NarrativeEngine
from narrative_engine.models.narrative import NarrativeOutput
from narrative_engine.models.state import GameState, PlayerState, WorldState


def _print_output(intent_label: str, result: NarrativeOutput) -> None:
    tag = f"[{intent_label}/{result.backend}]"
    if result.dialogue:
        print(f"{tag} {result.dialogue.text}")
        if result.dialogue.unlock_hint:
            print(f"  · 线索: {result.dialogue.unlock_hint}")
    elif result.event:
        print(f"{tag} 事件: {result.event.title}")
        print(f"  {result.event.description}")
        for i, choice in enumerate(result.event.choices, 1):
            consequence = result.event.consequences.get(choice, "")
            tail = f" → {consequence}" if consequence else ""
            print(f"  {i}. {choice}{tail}")
    elif result.description:
        print(f"{tag} {result.description.text}")

    if result.backend == "fallback":
        print(f"  · 降级: {result.error or '(无明细)'}")


async def _loop(narrator: AutoNarrator) -> None:
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            return

        try:
            intent, result = await narrator.respond(line)
        except Exception as e:
            print(f"  · 错误: {e}")
            continue

        label = intent.kind
        if intent.npc_id:
            label = f"{intent.npc_id}/{intent.kind}"
        if intent.new_area:
            print(f"  · 切到: {intent.new_area}")
        _print_output(label, result)


def run_auto_repl(engine: NarrativeEngine) -> None:
    """同步入口：起一个 AutoNarrator，跑自然语言 REPL 直到用户退出。"""
    state = GameState(player=PlayerState(), world=WorldState())
    narrator = AutoNarrator(engine, state)

    print(f"故事: {engine.story_title or '(未加载)'}")
    print(f"章节: {engine.current_chapter or '(无)'}")
    print(f"NPC: {list(engine.npcs)}")
    print("傻瓜模式：直接输入自然语言（输入 quit 退出）")
    print()

    asyncio.run(_loop(narrator))
