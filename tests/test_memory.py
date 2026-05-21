"""记忆系统测试。

覆盖: record_turn / session_context / remember / recall / memory_context / 持久化 roundtrip
"""

import tempfile
from pathlib import Path

from narrative_engine import MemoryManager, MemoryRecord, SessionTurn


# ============ Session (短期) ============

def test_record_turn_and_session_context():
    mgr = MemoryManager(session_turns=3)
    mgr.record_turn("npc_a", "你好", "你好，旅行者", "dialogue")
    mgr.record_turn("npc_b", "今天天气不错", "是啊", "dialogue")
    mgr.record_turn("npc_a", "再见", "一路顺风", "dialogue")

    ctx = mgr.session_context()
    assert "你好" in ctx
    assert "旅行者" in ctx
    assert "一路顺风" in ctx


def test_session_context_respects_max_turns():
    mgr = MemoryManager(session_turns=2)
    for i in range(5):
        mgr.record_turn("npc", f"ctx{i}", f"resp{i}", "dialogue")

    ctx = mgr.session_context()
    assert "ctx0" not in ctx
    assert "ctx3" in ctx
    assert "ctx4" in ctx


def test_session_context_empty():
    mgr = MemoryManager()
    assert mgr.session_context() == ""


def test_new_session_clears_turns():
    mgr = MemoryManager()
    mgr.record_turn("npc", "hi", "hello", "dialogue")
    assert mgr.session_context() != ""

    mgr.new_session()
    assert mgr.session_context() == ""
    assert mgr._turn_counter == 0


# ============ Memory (长期) ============

def test_remember_and_recall():
    mgr = MemoryManager()
    mgr.remember("fishmonger", "鱼不新鲜", "dialogue", importance=5)
    mgr.remember("fishmonger", "提到了奶奶的汤", "dialogue", importance=8)
    mgr.remember("fishmonger", "今天天气不错", "dialogue", importance=0)

    records = mgr.recall("fishmonger")
    assert len(records) == 3
    # 高 importance 排最前
    assert records[0].content == "提到了奶奶的汤"


def test_remember_ignores_empty():
    mgr = MemoryManager()
    mgr.remember("npc", "", "dialogue")
    mgr.remember("", "some content", "dialogue")
    mgr.remember("npc", "   ", "dialogue")

    assert mgr.recall("npc") == []


def test_recall_nonexistent_npc():
    mgr = MemoryManager()
    assert mgr.recall("nonexistent") == []


def test_memory_context_format():
    mgr = MemoryManager()
    mgr.remember("fishmonger", "鱼不新鲜", "dialogue", importance=5)
    mgr.remember("fishmonger", "提到了奶奶的汤", "dialogue", importance=8)

    ctx = mgr.memory_context("fishmonger")
    assert "鱼不新鲜" in ctx
    assert "奶奶的汤" in ctx
    assert "- [" in ctx  # 格式化标记


def test_memory_context_empty():
    mgr = MemoryManager()
    assert mgr.memory_context("nobody") == ""


def test_memory_size_limit():
    mgr = MemoryManager(memory_size=3)
    for i in range(10):
        mgr.remember("npc", f"memory {i}", "dialogue")

    records = mgr.recall("npc", limit=20)
    assert len(records) == 3
    # 同 importance=0 → 按时间保留最近 3 条
    contents = {r.content for r in records}
    assert "memory 7" in contents
    assert "memory 8" in contents
    assert "memory 9" in contents


def test_importance_eviction_keeps_important():
    """高 importance 记录不被低 importance 新记录挤出。"""
    mgr = MemoryManager(memory_size=3)
    mgr.remember("npc", "关键信息", "dialogue", importance=8)
    mgr.remember("npc", "不太重要1", "dialogue", importance=0)
    mgr.remember("npc", "不太重要2", "dialogue", importance=0)
    # 超过限额，低 importance 的先淘汰
    mgr.remember("npc", "琐碎闲聊", "dialogue", importance=0)

    records = mgr.recall("npc")
    assert len(records) == 3
    contents = {r.content for r in records}
    assert "关键信息" in contents  # high importance 存活
    assert len([r for r in records if r.importance == 0]) == 2


def test_dedup_skips_identical_content():
    """相同内容不应创建重复记忆。"""
    mgr = MemoryManager()
    mgr.remember("npc", "鱼不新鲜", "dialogue")
    mgr.remember("npc", "鱼不新鲜", "dialogue")
    mgr.remember("npc", "鱼不新鲜", "dialogue")

    records = mgr.recall("npc")
    assert len(records) == 1
    # 即使带不同 importance 也应该跳过（内容完全相同）
    mgr.remember("npc", "鱼不新鲜", "dialogue", importance=9)
    assert len(mgr.recall("npc")) == 1


def test_content_stripped_before_dedup():
    """去重前先 strip 内容。"""
    mgr = MemoryManager()
    mgr.remember("npc", "  鱼不新鲜  ", "dialogue")
    mgr.remember("npc", "鱼不新鲜", "dialogue")
    assert len(mgr.recall("npc")) == 1


# ============ 持久化 ============

def test_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "memories.json"

        mgr1 = MemoryManager(memory_path=str(path))
        mgr1.remember("npc_a", "记忆A", "dialogue", importance=3)
        mgr1.remember("npc_b", "记忆B", "event", importance=5)
        mgr1.save()

        assert path.exists()

        mgr2 = MemoryManager(memory_path=str(path))
        assert len(mgr2.recall("npc_a")) == 1
        assert mgr2.recall("npc_a")[0].content == "记忆A"
        assert len(mgr2.recall("npc_b")) == 1
        assert mgr2.recall("npc_b")[0].kind == "event"


def test_save_without_path_is_noop():
    """未配置 memory_path 时 save() 不抛异常。"""
    mgr = MemoryManager()
    mgr.remember("npc", "test", "dialogue")
    mgr.save()  # 无 path，no-op，不应抛异常


def test_save_to_valid_path():
    """save 到有效路径正常工作。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sub" / "mem.json"
        mgr = MemoryManager()
        mgr.remember("npc", "test", "dialogue")
        mgr.save(str(path))
        assert path.exists()


def test_load_nonexistent_file():
    mgr = MemoryManager(memory_path="/nonexistent/path/mem.json")
    assert mgr.recall("anyone") == []


def test_clear():
    mgr = MemoryManager()
    mgr.remember("npc", "记忆", "dialogue")
    mgr.record_turn("npc", "hi", "hello", "dialogue")

    assert mgr.recall("npc") != []
    assert mgr.session_context() != ""

    mgr.clear()

    assert mgr.recall("npc") == []
    assert mgr.session_context() == ""
    assert mgr._turn_counter == 0


# ============ 模型 ============

def test_memory_record_defaults():
    r = MemoryRecord(content="test")
    assert r.npc_id == ""
    assert r.kind == "dialogue"
    assert r.importance == 0
    assert r.timestamp > 0


def test_session_turn_defaults():
    t = SessionTurn(turn=1, engine_response="hello")
    assert t.npc_id == ""
    assert t.player_context == ""
    assert t.kind == "dialogue"
