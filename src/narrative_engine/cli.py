"""命令行入口。

用法:
    narrative-engine dialogue --area "旧码头" --npc "鱼贩老李" --context "玩家钓上一只旧靴子"
    narrative-engine event --area "海边" --context "玩家捡到一个漂流瓶"
    narrative-engine describe --area "废弃灯塔" --context "玩家站在灯塔前"
    narrative-engine shell   # 交互式 shell
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    print("narrative-engine v0.1.0")
    print("用法: narrative-engine [dialogue|event|describe|shell|serve|tui] [选项]")
    print()

    if len(sys.argv) < 2:
        print("示例:")
        print('  narrative-engine dialogue --area "旧码头" --npc "鱼贩老李" --context "钓上旧靴子"')
        print('  narrative-engine event --area "海边" --context "捡到漂流瓶"')
        print('  narrative-engine shell')
        print('  narrative-engine serve --port 8000 --story stories/seaside_town')
        print('  narrative-engine tui')
        return

    cmd = sys.argv[1]
    kwargs = _parse_args(sys.argv[2:])

    if cmd == "shell":
        _interactive()
    elif cmd == "serve":
        _serve(kwargs)
    elif cmd == "tui":
        _tui()
    elif cmd in ("dialogue", "event", "describe"):
        _run_generation(cmd, kwargs)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


def _serve(kwargs: dict) -> None:
    try:
        import uvicorn
        from narrative_engine.api import create_app
    except ImportError:
        print("需要安装 API 依赖: pip install narrative-engine[api]")
        return

    host = kwargs.get("host", "0.0.0.0")
    port = int(kwargs.get("port", "8000"))
    story = kwargs.get("story", "")

    engine = None
    if story:
        from narrative_engine import NarrativeEngine
        engine = NarrativeEngine.from_story(story)

    app = create_app(engine)
    print(f"narrative-engine API 启动: http://{host}:{port}")
    if story:
        print(f"故事: {story}")
    uvicorn.run(app, host=host, port=port)


def _tui() -> None:
    try:
        from narrative_engine.tui import NarrativeTUI
    except ImportError:
        print("需要安装 TUI 依赖: pip install narrative-engine[tui]")
        return
    app = NarrativeTUI()
    app.run()


def _parse_args(args: list[str]) -> dict:
    kwargs = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                kwargs[key] = args[i + 1]
                i += 2
            else:
                kwargs[key] = True
                i += 1
        else:
            i += 1
    return kwargs


def _run_generation(kind: str, kwargs: dict) -> None:
    import os
    from narrative_engine import NarrativeEngine, GameState, WorldState, NPCState
    from narrative_engine.models.config import ProviderKind

    backend = os.environ.get("NARRATIVE_BACKEND", "openai")
    engine = NarrativeEngine({
        "backend": {
            "provider": ProviderKind(backend),
            "api_key": os.environ.get("NARRATIVE_API_KEY", ""),
            "api_base": os.environ.get("NARRATIVE_API_BASE", ""),
            "model": os.environ.get("NARRATIVE_MODEL", ""),
        },
    })

    npc_id = kwargs.get("npc", "")
    npcs = {}
    if npc_id:
        npcs[npc_id] = NPCState(id=npc_id, name=kwargs.get("npc_name", npc_id))

    state = GameState(
        world=WorldState(area=kwargs.get("area", "")),
        npcs=npcs,
    )

    result = engine.tell(
        state=state,
        kind=kind,
        context=kwargs.get("context", ""),
        npc_id=npc_id,
    )
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


def _interactive() -> None:
    print("交互模式 (输入 quit 退出)")
    print("示例输入: dialogue 旧码头 鱼贩老李 钓上旧靴子")
    print()

    import os
    from narrative_engine import NarrativeEngine, GameState, WorldState, NPCState
    from narrative_engine.models.config import ProviderKind

    backend = os.environ.get("NARRATIVE_BACKEND", "openai")
    engine = NarrativeEngine({
        "backend": {
            "provider": ProviderKind(backend),
            "api_key": os.environ.get("NARRATIVE_API_KEY", ""),
            "api_base": os.environ.get("NARRATIVE_API_BASE", ""),
            "model": os.environ.get("NARRATIVE_MODEL", ""),
        },
    })

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line.lower() in ("quit", "exit", "q"):
            break
        if not line:
            continue

        parts = line.split(maxsplit=3)
        if len(parts) < 3:
            print("格式: <kind> <area> <npc> <context>")
            continue

        kind, area, npc_name = parts[0], parts[1], parts[2]
        ctx = parts[3] if len(parts) > 3 else ""

        npcs = {npc_name: NPCState(id=npc_name, name=npc_name)}
        state = GameState(world=WorldState(area=area), npcs=npcs)

        result = engine.tell(state=state, kind=kind, context=ctx, npc_id=npc_name)
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        print()
