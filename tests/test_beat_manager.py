"""BeatManager 触发求值器测试。

覆盖: 精确匹配 / 比较运算符 / 正则 / $or / 虚拟字段 / kind 过滤 / 优先级排序
"""

import pytest
from narrative_engine import (
    BeatManager,
    StoryBeat,
    GameState,
    PlayerState,
    WorldState,
    NPCState,
)


def make_state(**kwargs) -> GameState:
    """快速构造 GameState 的辅助函数。"""
    player = PlayerState(**(kwargs.pop("player", {})))
    world = WorldState(**(kwargs.pop("world", {})))
    npcs = {n.id: n for n in kwargs.pop("npcs", [])}
    return GameState(player=player, world=world, npcs=npcs, **kwargs)


# ============ 精确匹配 ============

def test_exact_match_world_area():
    mgr = BeatManager()
    beat = StoryBeat(id="t1", trigger={"world.area": "grandma_house"})
    mgr.register(beat)

    state = make_state(world={"area": "grandma_house"})
    assert mgr.check(state) == beat

    state2 = make_state(world={"area": "old_dock"})
    assert mgr.check(state2) is None


def test_exact_match_nested_path():
    mgr = BeatManager()
    beat = StoryBeat(id="t2", trigger={"player.flags.has_camera": True})
    mgr.register(beat)

    state = make_state(player={"flags": {"has_camera": True}})
    assert mgr.check(state) == beat

    state2 = make_state(player={"flags": {"has_camera": False}})
    assert mgr.check(state2) is None


def test_exact_match_multiple_conditions():
    mgr = BeatManager()
    beat = StoryBeat(id="t3", trigger={"world.area": "dock", "world.time": "night"})
    mgr.register(beat)

    # 全部满足
    state = make_state(world={"area": "dock", "time": "night"})
    assert mgr.check(state) == beat

    # 只满足一个
    state2 = make_state(world={"area": "dock", "time": "morning"})
    assert mgr.check(state2) is None


def test_trigger_empty_dict_returns_none():
    mgr = BeatManager()
    beat = StoryBeat(id="t4", trigger={})
    mgr.register(beat)

    state = make_state()
    assert mgr.check(state) is None  # 空 trigger 不触发


# ============ 比较运算符 ============

@pytest.mark.parametrize("operator,threshold,value,expected", [
    (">=", "12", 12, True),
    (">=", "12", 11, False),
    (">=", "12", 13, True),
    ("<=", "80", 80, True),
    ("<=", "80", 81, False),
    ("<=", "80", 50, True),
    (">", "5", 6, True),
    (">", "5", 5, False),
    ("<", "10", 9, True),
    ("<", "10", 10, False),
    ("==", "7", 7, True),
    ("==", "7", 8, False),
])
def test_comparison_operators(operator, threshold, value, expected):
    mgr = BeatManager()
    beat = StoryBeat(id="cmp", trigger={"player.attributes.san": f"{operator}{threshold}"})
    mgr.register(beat)

    state = make_state(player={"attributes": {"san": value}})
    assert (mgr.check(state) == beat) == expected


# ============ 正则匹配 ============

def test_regex_match_area():
    mgr = BeatManager()
    beat = StoryBeat(id="r1", trigger={"world.area": "/dock|码头/"})
    mgr.register(beat)

    assert mgr.check(make_state(world={"area": "old_dock"})) == beat
    assert mgr.check(make_state(world={"area": "旧码头"})) == beat
    assert mgr.check(make_state(world={"area": "海滩"})) is None


def test_regex_match_npc_id():
    mgr = BeatManager()
    beat = StoryBeat(id="r2", trigger={"_npc_id": "/fish|鱼/"})
    mgr.register(beat)

    assert mgr.check(make_state(), npc_id="fishmonger_li") == beat
    assert mgr.check(make_state(), npc_id="鱼贩老李") == beat
    assert mgr.check(make_state(), npc_id="baker_wang") is None


# ============ $or 条件组 ============

def test_or_both_groups_match():
    mgr = BeatManager()
    beat = StoryBeat(id="or1", trigger={
        "$or": [
            {"world.area": "dock", "world.time": "night"},
            {"world.area": "graveyard", "world.time": "dusk"},
        ],
    })
    mgr.register(beat)

    assert mgr.check(make_state(world={"area": "dock", "time": "night"})) == beat
    assert mgr.check(make_state(world={"area": "graveyard", "time": "dusk"})) == beat
    assert mgr.check(make_state(world={"area": "dock", "time": "morning"})) is None


def test_or_combined_with_and():
    mgr = BeatManager()
    beat = StoryBeat(id="or_and", trigger={
        "$or": [
            {"world.area": "dock"},
            {"world.area": "graveyard"},
        ],
        "player.attributes.san": "<=50",
    })
    mgr.register(beat)

    # OR 满足 + AND 满足
    assert mgr.check(make_state(
        world={"area": "dock"}, player={"attributes": {"san": 40}}
    )) == beat

    # OR 满足 + AND 不满足
    assert mgr.check(make_state(
        world={"area": "dock"}, player={"attributes": {"san": 80}}
    )) is None


# ============ $not ============

def test_not_dict_negates_single_condition():
    mgr = BeatManager()
    beat = StoryBeat(id="not1", trigger={
        "$not": {"world.area": "safe_zone"},
    })
    mgr.register(beat)

    assert mgr.check(make_state(world={"area": "dock"})) == beat
    assert mgr.check(make_state(world={"area": "market"})) == beat
    assert mgr.check(make_state(world={"area": "safe_zone"})) is None


def test_not_list_negates_or_of_groups():
    mgr = BeatManager()
    beat = StoryBeat(id="not2", trigger={
        "$not": [
            {"world.area": "dock"},
            {"world.area": "market"},
        ],
    })
    mgr.register(beat)

    # dock / market → blocked by $not
    assert mgr.check(make_state(world={"area": "dock"})) is None
    assert mgr.check(make_state(world={"area": "market"})) is None
    # anywhere else → passes
    assert mgr.check(make_state(world={"area": "graveyard"})) == beat
    assert mgr.check(make_state(world={"area": "home"})) == beat


def test_not_combined_with_and():
    mgr = BeatManager()
    beat = StoryBeat(id="not_and", trigger={
        "$not": {"world.area": "safe_zone"},
        "player.attributes.san": "<=50",
    })
    mgr.register(beat)

    # 不在 safe_zone + san <= 50 → pass
    assert mgr.check(make_state(
        world={"area": "dock"}, player={"attributes": {"san": 40}}
    )) == beat
    # 在 safe_zone + san <= 50 → fail
    assert mgr.check(make_state(
        world={"area": "safe_zone"}, player={"attributes": {"san": 40}}
    )) is None
    # 不在 safe_zone + san > 50 → fail
    assert mgr.check(make_state(
        world={"area": "dock"}, player={"attributes": {"san": 80}}
    )) is None


def test_not_with_or_inside():
    """$not 内嵌 $or → 不在 (dock 或 market)"""
    mgr = BeatManager()
    beat = StoryBeat(id="not_or", trigger={
        "$not": {
            "$or": [
                {"world.area": "dock"},
                {"world.area": "market"},
            ],
        },
    })
    mgr.register(beat)

    assert mgr.check(make_state(world={"area": "dock"})) is None
    assert mgr.check(make_state(world={"area": "market"})) is None
    assert mgr.check(make_state(world={"area": "graveyard"})) == beat


# ============ 虚拟字段 ============

def test_virtual_inventory_count():
    mgr = BeatManager()
    beat = StoryBeat(id="v1", trigger={"_inventory_count": ">=3"})
    mgr.register(beat)

    assert mgr.check(make_state(player={"inventory": ["a", "b", "c"]})) == beat
    assert mgr.check(make_state(player={"inventory": ["a"]})) is None
    assert mgr.check(make_state(player={"inventory": []})) is None


def test_virtual_photos_count():
    mgr = BeatManager()
    beat = StoryBeat(id="v2", trigger={"_photos_count": ">=5"})
    mgr.register(beat)

    state = make_state(player={"recent_actions": ["a"] * 5})
    assert mgr.check(state) == beat

    state2 = make_state(player={"recent_actions": ["a"] * 3})
    assert mgr.check(state2) is None


def test_virtual_npc_count():
    mgr = BeatManager()
    beat = StoryBeat(id="v3", trigger={"_npc_count": ">=2"})
    mgr.register(beat)

    state = make_state(npcs=[
        NPCState(id="a", name="A"),
        NPCState(id="b", name="B"),
    ])
    assert mgr.check(state) == beat


# ============ kind / priority / once ============

def test_kind_filtering():
    mgr = BeatManager()
    dialogue_beat = StoryBeat(id="d", kind="dialogue", trigger={"world.area": "test"})
    event_beat = StoryBeat(id="e", kind="event", trigger={"world.area": "test"})
    all_beat = StoryBeat(id="a", kind="all", trigger={"world.area": "test"})
    mgr.register_many([dialogue_beat, event_beat, all_beat])

    state = make_state(world={"area": "test"})
    assert mgr.check(state, kind="dialogue") == dialogue_beat
    assert mgr.check(state, kind="event") == event_beat
    assert mgr.check(state, kind="description") == all_beat  # all 匹配所有 kind


def test_priority_ordering():
    mgr = BeatManager()
    low = StoryBeat(id="low", priority=1, trigger={"world.area": "test"})
    high = StoryBeat(id="high", priority=100, trigger={"world.area": "test"})
    mid = StoryBeat(id="mid", priority=50, trigger={"world.area": "test"})
    mgr.register_many([low, high, mid])

    state = make_state(world={"area": "test"})
    assert mgr.check(state).id == "high"


def test_once_semantics():
    mgr = BeatManager()
    once_beat = StoryBeat(id="once", once=True, priority=50, trigger={"world.area": "test"})
    repeat_beat = StoryBeat(id="repeat", once=False, priority=10, trigger={"world.area": "test"})
    mgr.register_many([once_beat, repeat_beat])

    state = make_state(world={"area": "test"})

    # 首次: once_beat 优先级更高
    assert mgr.check(state).id == "once"
    mgr.mark_fired("once")

    # 再次: once_beat 已触发，应返回 repeat_beat
    assert mgr.check(state).id == "repeat"
    mgr.mark_fired("repeat")

    # 第三次: repeat_beat 也可重复
    assert mgr.check(state).id == "repeat"


def test_fired_and_pending_tracking():
    mgr = BeatManager()
    mgr.register_many([
        StoryBeat(id="a", trigger={"world.area": "test"}),
        StoryBeat(id="b", trigger={"world.area": "test2"}),
        StoryBeat(id="c", trigger={"world.area": "test3"}),
    ])

    assert mgr.fired == set()
    assert len(mgr.pending) == 3

    mgr.mark_fired("a")
    assert mgr.fired == {"a"}
    assert len(mgr.pending) == 2
    assert {b.id for b in mgr.pending} == {"b", "c"}

    mgr.reset()
    assert mgr.fired == set()
    assert len(mgr.pending) == 3


# ============ 边界情况 ============

def test_nonexistent_path_returns_none():
    mgr = BeatManager()
    beat = StoryBeat(id="nx", trigger={"player.nonexistent.field": "value"})
    mgr.register(beat)

    assert mgr.check(make_state()) is None


def test_attribute_not_in_model():
    mgr = BeatManager()
    beat = StoryBeat(id="nx2", trigger={"world.nonexistent": True})
    mgr.register(beat)

    assert mgr.check(make_state()) is None  # 不抛异常
