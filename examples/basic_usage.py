"""基本用法示例 — 从故事目录一行启动。

运行前:
    1. 复制 .env.example 为 .env 并填入 API 密钥
    2. uv run python examples/basic_usage.py
"""

from pathlib import Path

from narrative_engine import NarrativeEngine, GameState, PlayerState, WorldState


def main() -> None:
    story_dir = Path(__file__).resolve().parent.parent / "stories" / "seaside_town"

    # ---- 一行启动：加载故事 ----
    engine = NarrativeEngine.from_story(str(story_dir))

    print(f"故事: {engine.story_title}")
    print(f"当前章节: {engine.current_chapter}")
    print(f"全部章节: {engine.list_chapters()}")
    print(f"NPC: {list(engine.npcs.keys())}")
    print(f"待触发锚点: {[b.id for b in engine.beat_manager.pending]}")
    print()

    # ---- 场景一：触发开场锚点 ----
    print("=" * 60)
    print("场景一：进入奶奶的老房子 → 触发 prologue_arrival")
    print("=" * 60)

    state = GameState(
        player=PlayerState(name="悠悠", attributes={"san": 100}),
        world=WorldState(area="grandma_house", time="黄昏", chapter="第一章"),
    )
    result = engine.tell(state, kind="description", context="第一次站在老房子前")
    print(f"  描述: {result.description.text if result.description else 'N/A'}")
    print(f"  后端: {result.backend}")
    print()

    # ---- 场景二：NPC 对话（自动从 npcs.yaml 补全 NPC 信息） ----
    print("=" * 60)
    print("场景二：鱼贩老李认出玩家 → 触发 fishmonger_recognize")
    print("  NPC 信息从 npcs.yaml 自动补全")
    print("=" * 60)

    state2 = GameState(
        player=PlayerState(name="悠悠", attributes={"san": 72}, flags={"met_li": True}),
        world=WorldState(area="old_dock", time="夜晚", weather="雾"),
    )
    result2 = engine.tell(state2, kind="dialogue", npc_id="fishmonger_li",
                          context="老李盯着玩家看了很久")
    print(f"  对话: {result2.dialogue.text if result2.dialogue else 'N/A'}")
    print(f"  线索: {result2.dialogue.unlock_hint if result2.dialogue else 'N/A'}")
    print(f"  后端: {result2.backend}")
    print()

    # ---- 场景三：OR + 正则 + 比较 ----
    print("=" * 60)
    print("场景三：深夜码头，SAN 45 → $or + 正则")
    print("=" * 60)

    state3 = GameState(
        player=PlayerState(name="悠悠", attributes={"san": 45}),
        world=WorldState(area="旧码头", time="night"),
    )
    result3 = engine.tell(state3, kind="event", context="深夜站在码头边")
    if result3.event:
        print(f"  标题: {result3.event.title}")
        print(f"  后端: {result3.backend}")
    print()

    # ---- 场景四：无锚点命中 → AI / fallback ----
    print("=" * 60)
    print("场景四：普通闲聊 → 无锚点，走 fallback")
    print("=" * 60)

    state4 = GameState(
        player=PlayerState(name="悠悠", attributes={"san": 80}),
        world=WorldState(area="市场", time="早晨"),
    )
    result4 = engine.tell(state4, kind="dialogue", npc_id="bakery_aunt",
                          context="问今天有什么新鲜面包")
    print(f"  对话: {result4.dialogue.text if result4.dialogue else 'N/A'}")
    print(f"  后端: {result4.backend}")
    print()

    # ---- 状态 ----
    print("=" * 60)
    print(f"已触发: {engine.beat_manager.fired}")
    print(f"待触发: {[b.id for b in engine.beat_manager.pending]}")


if __name__ == "__main__":
    main()
