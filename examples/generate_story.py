"""AI 总编剧 demo — 一段灵感生成完整 stories/<name>/，立即可玩。

运行前:
    export NARRATIVE_API_KEY=sk-xxxx
    export NARRATIVE_API_BASE=https://api.deepseek.com   # 或其他 OpenAI 兼容端点
    export NARRATIVE_MODEL=deepseek-v4-pro

用法:
    python examples/generate_story.py "<故事灵感>" [输出目录]

例:
    python examples/generate_story.py "赛博朋克侦探在霓虹酒吧调查失踪案"
    python examples/generate_story.py "武侠客栈黑店悬案" stories/wuxia_inn
"""

from __future__ import annotations

import sys
from pathlib import Path

import narrative_engine
from narrative_engine import GameState, NarrativeEngine, WorldState
from narrative_engine.generators import StoryGenerator


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^\w一-鿿]+", "_", text.strip())
    return re.sub(r"_+", "_", s).strip("_").lower()[:40] or "story"


def main(argv: list[str]) -> int:
    narrative_engine.enable_logging()

    if len(argv) < 2:
        print(__doc__)
        return 1

    idea = argv[1]
    out = argv[2] if len(argv) > 2 else f"stories/{_slugify(idea)}"

    print(f"灵感: {idea}")
    print(f"输出: {out}")
    print()

    if Path(out).exists():
        print(f"目录已存在: {out}（删了或换路径再试）")
        return 1

    print("调用 LLM 生成故事，可能需要 10-30 秒...")
    gen = StoryGenerator()
    path = gen.generate(idea, out, num_npcs=3, num_beats=5)

    print(f"\n故事已生成: {path}")
    print(f"  story.yaml    {(path / 'story.yaml').stat().st_size} bytes")
    print(f"  npcs.yaml     {(path / 'npcs.yaml').stat().st_size} bytes")
    chapters = list((path / "chapters").glob("*.yaml"))
    for ch in chapters:
        print(f"  chapters/{ch.name}  {ch.stat().st_size} bytes")
    print()

    print("自检：用刚生成的目录初始化引擎并跑一轮 description...")
    engine = NarrativeEngine.from_story(str(path))
    engine.reset_beats()
    print(f"  标题: {engine.story_title}")
    print(f"  章节: {engine.current_chapter}")
    print(f"  NPC: {list(engine.npcs)}")

    sample_area = ""
    for chapter in engine._chapters.values():
        for beat in chapter.beats:
            area = beat.trigger.get("world.area")
            if isinstance(area, str) and not area.startswith("/"):
                sample_area = area
                break
        if sample_area:
            break

    state = GameState(world=WorldState(area=sample_area))
    result = engine.tell(state, kind="description", context="刚到达此地")
    text = result.description.text if result.description else "(空)"
    print(f"  首段描述 ({result.backend}): {text}")
    print()

    print("下一步:")
    print(f"  python examples/interactive_demo.py {path}")
    print(f"  narrative-engine serve --story {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
