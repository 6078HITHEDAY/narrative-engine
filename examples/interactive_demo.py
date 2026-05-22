"""通用互动 demo — 任意 stories/<dir> 都能跑。

用法:
    python examples/interactive_demo.py [story_dir]

默认 story_dir = stories/seaside_town。命令：

    look              当前场景描述
    go <area>         切换到新场景
    talk <npc_id>     和 NPC 对话
    event [context]   触发一个支线事件（列出 choices）
    choose <n>        选刚才事件的第 n 个选项（调 apply_choice）
    pick <item>       添加物品到 inventory（验证 prompt 注入）
    drop <item>       从 inventory 移除
    inv               查看 inventory + 最近行动
    npcs              列出已加载 NPC
    chapters          列出章节
    chapter <name>    切换章节
    quit              退出
"""

from __future__ import annotations

import sys
from pathlib import Path

import narrative_engine
from narrative_engine import GameState, NarrativeEngine, PlayerState, WorldState


def _print_output(result, label: str = "") -> None:
    if label:
        print(f"[{label}]", end=" ")
    if result.dialogue:
        print(result.dialogue.text)
        if result.dialogue.unlock_hint:
            print(f"  · 线索: {result.dialogue.unlock_hint}")
    elif result.event:
        print(f"事件: {result.event.title}")
        print(f"  {result.event.description}")
        for i, choice in enumerate(result.event.choices, 1):
            consequence = result.event.consequences.get(choice, "")
            tail = f" → {consequence}" if consequence else ""
            print(f"  {i}. {choice}{tail}")
    elif result.description:
        print(result.description.text)

    if result.backend == "fallback":
        print(f"  · 降级: {result.error or '(无明细)'}")


def _cmd_look(engine, state) -> None:
    result = engine.tell(state, kind="description", context=f"环顾 {state.world.area}")
    _print_output(result, label=result.backend)


def _cmd_go(engine, state, args: list[str]) -> None:
    if not args:
        print("用法: go <area>")
        return
    area = " ".join(args)
    state.world.area = area
    print(f"  · 切换到: {area}")
    result = engine.tell(state, kind="description", context=f"刚到 {area}")
    _print_output(result, label=result.backend)


def _cmd_talk(engine, state, args: list[str]) -> None:
    if not args:
        print("用法: talk <npc_id>（已加载: " + ", ".join(engine.npcs) + "）")
        return
    npc_id = args[0]
    context = " ".join(args[1:]) or "玩家上前搭话"
    result = engine.tell(state, kind="dialogue", context=context, npc_id=npc_id)
    _print_output(result, label=f"{npc_id}/{result.backend}")


def _cmd_event(engine, state, args: list[str], event_slot: dict) -> None:
    context = " ".join(args) or f"在 {state.world.area} 闲逛"
    result = engine.tell(state, kind="event", context=context)
    _print_output(result, label=result.backend)
    if result.event and result.event.choices:
        event_slot["last"] = result.event


def _cmd_choose(engine, state, args: list[str], event_slot: dict) -> None:
    last = event_slot.get("last")
    if not last:
        print("没有待选事件。先 `event` 触发一个。")
        return
    if not args or not args[0].isdigit():
        print(f"用法: choose <1-{len(last.choices)}>")
        return
    idx = int(args[0]) - 1
    if not 0 <= idx < len(last.choices):
        print(f"序号越界 (1-{len(last.choices)})")
        return
    choice = last.choices[idx]
    engine.apply_choice(state, last, choice)
    print(f"  · 选了: {choice}")
    consequence = last.consequences.get(choice, "")
    if consequence:
        print(f"  · 后果: {consequence}")
    event_slot["last"] = None
    follow = engine.tell(
        state, kind="description",
        context=f"刚做出选择「{choice}」之后",
    )
    _print_output(follow, label=f"after-choice/{follow.backend}")


def _cmd_pick(state, args: list[str]) -> None:
    if not args:
        print("用法: pick <item>")
        return
    item = " ".join(args)
    state.player.inventory.append(item)
    print(f"  · 持有: {state.player.inventory}")


def _cmd_drop(state, args: list[str]) -> None:
    if not args:
        print("用法: drop <item>")
        return
    item = " ".join(args)
    if item in state.player.inventory:
        state.player.inventory.remove(item)
        print(f"  · 持有: {state.player.inventory}")
    else:
        print(f"  · 没有 {item}")


def _cmd_inv(state) -> None:
    print(f"  Inventory: {state.player.inventory or '(空)'}")
    print(f"  Recent actions: {state.player.recent_actions[-5:] or '(空)'}")
    print(f"  History (尾 3): {state.history[-3:] or '(空)'}")


def _cmd_chapters(engine) -> None:
    chapters = engine.list_chapters()
    print(f"  当前章节: {engine.current_chapter}")
    print(f"  全部章节: {chapters}")


def _cmd_chapter(engine, args: list[str]) -> None:
    if not args:
        print("用法: chapter <name>（用 `chapters` 列出可用名）")
        return
    try:
        engine.switch_chapter(args[0])
        print(f"  · 切到: {engine.current_chapter}")
    except ValueError as e:
        print(f"  · 失败: {e}")


def main(argv: list[str]) -> int:
    narrative_engine.enable_logging()

    story_dir = argv[1] if len(argv) > 1 else "stories/seaside_town"
    if not Path(story_dir).is_dir():
        print(f"故事目录不存在: {story_dir}")
        return 1

    engine = NarrativeEngine.from_story(story_dir)
    engine.reset_beats()

    state = GameState(player=PlayerState(), world=WorldState())
    event_slot: dict = {"last": None}

    print(f"故事: {engine.story_title}")
    print(f"章节: {engine.current_chapter}")
    print(f"NPC: {list(engine.npcs)}")
    print("输入 `look` / `go <area>` / `talk <npc>` / `event` / `choose <n>` / `inv` / `quit`")
    print()

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]

        if cmd in ("quit", "exit", "q"):
            break
        elif cmd == "look":
            _cmd_look(engine, state)
        elif cmd == "go":
            _cmd_go(engine, state, args)
        elif cmd == "talk":
            _cmd_talk(engine, state, args)
        elif cmd == "event":
            _cmd_event(engine, state, args, event_slot)
        elif cmd == "choose":
            _cmd_choose(engine, state, args, event_slot)
        elif cmd == "pick":
            _cmd_pick(state, args)
        elif cmd == "drop":
            _cmd_drop(state, args)
        elif cmd == "inv":
            _cmd_inv(state)
        elif cmd == "npcs":
            print(f"  {list(engine.npcs)}")
        elif cmd == "chapters":
            _cmd_chapters(engine)
        elif cmd == "chapter":
            _cmd_chapter(engine, args)
        else:
            print(f"未知命令: {cmd}（look/go/talk/event/choose/pick/drop/inv/npcs/chapters/chapter/quit）")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
