"""傻瓜模式 demo — 直接输入自然语言，AI 自动调引擎。

用法:
    python examples/auto_demo.py [story_dir]

默认 story_dir = stories/seaside_town。
"""

from __future__ import annotations

import sys
from pathlib import Path

import narrative_engine
from narrative_engine import NarrativeEngine
from narrative_engine.auto_repl import run_auto_repl


def main(argv: list[str]) -> int:
    narrative_engine.enable_logging()

    story_dir = argv[1] if len(argv) > 1 else "stories/seaside_town"
    if not Path(story_dir).is_dir():
        print(f"故事目录不存在: {story_dir}")
        return 1

    engine = NarrativeEngine.from_story(story_dir)
    engine.reset_beats()
    run_auto_repl(engine)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
