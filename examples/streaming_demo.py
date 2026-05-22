"""流式生成 demo — 同步 + 异步两种用法。

运行前:
    export NARRATIVE_API_KEY=sk-xxxx
    export NARRATIVE_API_BASE=https://api.deepseek.com
    export NARRATIVE_MODEL=deepseek-v4-pro

用法:
    python examples/streaming_demo.py [story_dir]
"""

from __future__ import annotations

import asyncio
import sys

import narrative_engine
from narrative_engine import GameState, NarrativeEngine, PlayerState, WorldState


def _print_chunk(label: str, text: str, last: list[str]) -> None:
    """只打印新增 delta，避免 instructor 部分模型每次输出全量。"""
    delta = text[len(last[0]):] if text.startswith(last[0]) else text
    if delta:
        print(delta, end="", flush=True)
        last[0] = text


def sync_streaming(engine: NarrativeEngine, state: GameState) -> None:
    print("[同步流式] dialogue:")
    last = [""]
    for partial in engine.tell_stream(state, kind="dialogue", context="问路"):
        text = getattr(partial, "text", "") or (
            partial.dialogue.text if hasattr(partial, "dialogue") and partial.dialogue else ""
        )
        if text:
            _print_chunk("dialogue", text, last)
    print()


async def async_streaming(engine: NarrativeEngine, state: GameState) -> None:
    print("[异步流式] description:")
    last = [""]
    async for partial in engine.tell_stream_async(state, kind="description", context="环顾四周"):
        text = getattr(partial, "text", "") or (
            partial.description.text if hasattr(partial, "description") and partial.description else ""
        )
        if text:
            _print_chunk("description", text, last)
    print()


def main(argv: list[str]) -> int:
    narrative_engine.enable_logging()
    story_dir = argv[1] if len(argv) > 1 else "stories/seaside_town"

    engine = NarrativeEngine.from_story(story_dir)
    state = GameState(
        player=PlayerState(name="player"),
        world=WorldState(area="market"),
    )

    sync_streaming(engine, state)
    print()
    asyncio.run(async_streaming(engine, state))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
