"""故事加载器 + 引擎新 API 测试。

覆盖: 新目录结构 / 旧格式兼容 / switch_chapter / list_chapters / reload_npcs
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from narrative_engine import (
    NarrativeEngine,
    StoryLoader,
    StoryMeta,
    ChapterConfig,
    GameState,
    WorldState,
    PlayerState,
    BeatManager,
)


# ============ StoryLoader — 新格式 ============

def test_load_new_format():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "story.yaml").write_text(yaml.dump({
            "title": "测试故事",
            "default_world": {"setting": "测试世界", "tone": "eerie"},
        }), encoding="utf-8")
        (d / "npcs.yaml").write_text(yaml.dump({
            "npcs": {
                "npc_a": {"name": "角色A", "mood": "happy"},
            },
        }), encoding="utf-8")
        (d / "chapters" / "chapter_1.yaml").write_text(yaml.dump({
            "title": "第一章",
            "world": {"area": "起始点"},
            "beats": [
                {"id": "beat1", "kind": "description", "text": "测试锚点",
                 "trigger": {"world.area": "起始点"}},
            ],
            "fallback": {"dialogue": ["保底对话"]},
        }), encoding="utf-8")

        loader = StoryLoader(str(d))
        meta, npcs, chapters = loader.load()

        assert meta.title == "测试故事"
        assert meta.default_world.tone == "eerie"
        assert "npc_a" in npcs
        assert npcs["npc_a"].name == "角色A"
        assert "chapter_1" in chapters
        ch = chapters["chapter_1"]
        assert ch.title == "第一章"
        assert len(ch.beats) == 1
        assert ch.beats[0].id == "beat1"


def test_load_new_format_no_story_yaml():
    """story.yaml 可选，不存在时使用默认值。"""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "chapter_1.yaml").write_text(yaml.dump({
            "beats": [{"id": "b", "trigger": {}, "text": "test"}],
        }), encoding="utf-8")

        loader = StoryLoader(str(d))
        meta, npcs, chapters = loader.load()

        assert meta.title == Path(tmp).name
        assert len(chapters) == 1


def test_list_chapters():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "ch01.yaml").write_text("beats: []")
        (d / "chapters" / "ch02.yaml").write_text("beats: []")

        loader = StoryLoader(str(d))
        assert loader.list_chapters() == ["ch01", "ch02"]


# ============ StoryLoader — 旧格式兼容 ============

def test_load_legacy_format():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "story.yaml").write_text(yaml.dump({
            "world": {"setting": "旧格式世界"},
            "npcs": [{"id": "npc_x", "name": "角色X"}],
            "beats": [
                {"id": "old_beat", "kind": "dialogue", "text": "旧锚点",
                 "trigger": {"world.area": "test"}},
            ],
            "fallback": {"dialogue": ["旧保底"]},
        }), encoding="utf-8")

        loader = StoryLoader(str(d))
        meta, npcs, chapters = loader.load()

        assert meta.title == Path(tmp).name
        assert "npc_x" in npcs
        assert npcs["npc_x"].name == "角色X"
        assert "main" in chapters  # 旧格式用 "main" 作为章节名
        assert len(chapters["main"].beats) == 1
        assert chapters["main"].beats[0].id == "old_beat"


# ============ Engine API ============

def test_engine_load_story_new_format():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "story.yaml").write_text(yaml.dump({
            "title": "测试",
        }), encoding="utf-8")
        (d / "npcs.yaml").write_text(yaml.dump({
            "npcs": {"npc_a": {"name": "A"}},
        }), encoding="utf-8")
        (d / "chapters" / "ch1.yaml").write_text(yaml.dump({
            "title": "第一章测试",
            "beats": [
                {"id": "b1", "kind": "description", "text": "锚点文本",
                 "trigger": {"world.area": "test"}},
            ],
        }), encoding="utf-8")

        engine = NarrativeEngine()
        engine.load_story(str(d))

        assert engine.story_title == "测试"
        assert engine.current_chapter == "第一章测试"
        assert engine.list_chapters() == ["ch1"]
        assert "npc_a" in engine.npcs
        assert "b1" in engine.beat_manager._beats

        # tell() 应能命中锚点
        state = GameState(world=WorldState(area="test"))
        result = engine.tell(state, kind="description", context="测试")
        assert result.backend == "storybeat"
        assert "锚点文本" in result.description.text


def test_engine_load_story_legacy_compat():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "story.yaml").write_text(yaml.dump({
            "world": {"setting": "旧格式"},
            "npcs": [{"id": "npc_old", "name": "旧NPC"}],
            "beats": [
                {"id": "beat_old", "kind": "dialogue", "text": "旧文案",
                 "trigger": {"world.area": "anywhere"}},
            ],
            "fallback": {"dialogue": ["无话可说"]},
        }), encoding="utf-8")

        engine = NarrativeEngine.from_story(str(d))

        assert engine.current_chapter == Path(tmp).name
        assert "npc_old" in engine.npcs
        assert len(engine.list_chapters()) == 1


def test_engine_from_story_with_chapter():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "ch1.yaml").write_text(yaml.dump({
            "title": "第一章",
            "beats": [{"id": "b1", "trigger": {"world.area": "a"}, "text": "一"}],
        }), encoding="utf-8")
        (d / "chapters" / "ch2.yaml").write_text(yaml.dump({
            "title": "第二章",
            "beats": [{"id": "b2", "trigger": {"world.area": "a"}, "text": "二"}],
        }), encoding="utf-8")

        engine = NarrativeEngine.from_story(str(d), chapter="ch2")
        assert engine.current_chapter == "第二章"
        assert "b2" in engine.beat_manager._beats
        assert "b1" not in engine.beat_manager._beats


def test_switch_chapter():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "ch1.yaml").write_text(yaml.dump({
            "title": "第一章",
            "beats": [{"id": "b1", "trigger": {"world.area": "a"}, "text": "文案一"}],
            "fallback": {"dialogue": ["保底一"]},
        }), encoding="utf-8")
        (d / "chapters" / "ch2.yaml").write_text(yaml.dump({
            "title": "第二章",
            "beats": [{"id": "b2", "trigger": {"world.area": "a"}, "text": "文案二"}],
            "fallback": {"dialogue": ["保底二"]},
        }), encoding="utf-8")

        engine = NarrativeEngine.from_story(str(d))
        assert engine.current_chapter == "第一章"
        assert "b1" in engine.beat_manager._beats

        engine.switch_chapter("ch2")
        assert engine.current_chapter == "第二章"
        assert "b2" in engine.beat_manager._beats
        assert "b1" not in engine.beat_manager._beats


def test_switch_chapter_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "ch1.yaml").write_text("beats: []")

        engine = NarrativeEngine.from_story(str(d))
        with pytest.raises(ValueError, match="章节不存在"):
            engine.switch_chapter("nonexistent")


def test_reload_npcs():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "ch1.yaml").write_text("beats: []")
        (d / "npcs.yaml").write_text(yaml.dump({
            "npcs": {"npc_a": {"name": "A"}},
        }), encoding="utf-8")

        engine = NarrativeEngine.from_story(str(d))
        assert engine.npcs["npc_a"].name == "A"

        # 修改 npcs.yaml
        (d / "npcs.yaml").write_text(yaml.dump({
            "npcs": {"npc_a": {"name": "A改名"}, "npc_b": {"name": "B"}},
        }), encoding="utf-8")

        engine.reload_npcs()
        assert engine.npcs["npc_a"].name == "A改名"
        assert "npc_b" in engine.npcs


def test_npc_preset_memories_injected():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        (d / "chapters" / "ch1.yaml").write_text("beats: []")
        (d / "npcs.yaml").write_text(yaml.dump({
            "npcs": {
                "npc_a": {
                    "name": "A",
                    "preset_memories": [
                        {"content": "预设记忆一", "importance": 8},
                        {"content": "预设记忆二", "importance": 3},
                    ],
                },
            },
        }), encoding="utf-8")

        engine = NarrativeEngine.from_story(str(d))
        assert engine.memory is not None
        records = engine.memory.recall("npc_a")
        assert len(records) == 2
        contents = {r.content for r in records}
        assert "预设记忆一" in contents
        assert "预设记忆二" in contents


# ============ BeatManager.replace_beats ============

def test_replace_beats_preserves_fired():
    mgr = BeatManager()
    mgr.register_many([
        type("Beat", (), {"id": "a", "once": True, "kind": "all", "trigger": {}, "priority": 0})(),
    ])
    # 用真实 StoryBeat 替换
    from narrative_engine import StoryBeat

    mgr.replace_beats([
        StoryBeat(id="new_a", trigger={"world.area": "x"}, text="新A"),
        StoryBeat(id="new_b", trigger={"world.area": "y"}, text="新B"),
    ])
    assert "new_a" in mgr._beats
    assert "a" not in mgr._beats
    # fired 集合保持不变（空）
    assert mgr.fired == set()


# ============ 目录不存在 ============

def test_story_dir_not_found():
    with pytest.raises(FileNotFoundError):
        StoryLoader("/nonexistent/story/path")


def test_load_story_no_chapters():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "chapters").mkdir()
        # 空 chapters 目录，没有 .yaml 文件

        engine = NarrativeEngine()
        with pytest.raises(ValueError, match="没有章节"):
            engine.load_story(str(d))
