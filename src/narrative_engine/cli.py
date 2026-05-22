"""命令行入口。

用法:
    narrative-engine dialogue --area "<area>" --npc "<npc_id>" --context "<情境>"
    narrative-engine event --area "<area>" --context "<情境>"
    narrative-engine describe --area "<area>" --context "<情境>"
    narrative-engine generate --idea "<故事灵感>" --out stories/<名字>
    narrative-engine shell   # 交互式 shell
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    print("narrative-engine v0.1.0")
    print("用法: narrative-engine [dialogue|event|describe|generate|shell|serve|tui] [选项]")
    print()

    if len(sys.argv) < 2:
        print("示例:")
        print('  narrative-engine dialogue --area "<area>" --npc "<npc_id>" --context "<情境>"')
        print('  narrative-engine event --area "<area>" --context "<情境>"')
        print('  narrative-engine generate --idea "<故事灵感>" --out stories/<名字>')
        print('  narrative-engine shell')
        print('  narrative-engine serve --port 8000 --story stories/<故事名>')
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
        kind = "description" if cmd == "describe" else cmd
        _run_generation(kind, kwargs)
    elif cmd == "generate":
        _generate_story(kwargs)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


def _generate_story(kwargs: dict) -> None:
    """AI 总编剧：根据灵感一次性生成 stories/<name>/ 目录。"""
    from narrative_engine.generators import StoryGenerator

    idea = kwargs.get("idea")
    if not idea or idea is True:
        try:
            idea = input("故事灵感: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
    if not idea:
        print("缺少 --idea")
        sys.exit(1)

    out = kwargs.get("out")
    if not out or out is True:
        out = f"stories/{_slugify(idea)}"

    overwrite = bool(kwargs.get("overwrite", False))
    num_npcs = int(kwargs.get("npcs", 3))
    num_beats = int(kwargs.get("beats", 5))

    print(f"灵感: {idea}")
    print(f"输出: {out}")
    print(f"NPC 数: {num_npcs} / Beat 数: {num_beats}")
    print("调用 LLM 生成故事...")

    gen = StoryGenerator()
    try:
        path = gen.generate(idea, out, num_npcs=num_npcs, num_beats=num_beats, overwrite=overwrite)
    except FileExistsError as e:
        print(f"错误: {e}")
        sys.exit(1)

    print(f"\n故事已生成: {path}")
    print(f"运行: narrative-engine serve --story {path}")
    print(f"或互动: python examples/interactive_demo.py {path}")


def _slugify(text: str) -> str:
    """中文/标点转 snake_case 目录名。"""
    import re
    s = re.sub(r"[^\w一-鿿]+", "_", text.strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s[:50] or "untitled_story"


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
    print("格式: <kind> <area> <npc_id> <context>")
    print("示例: dialogue <area> <npc_id> <context>")
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
