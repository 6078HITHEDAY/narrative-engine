"""HTTP API 测试。"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from narrative_engine import (
    NarrativeEngine,
    EngineConfig,
    LLMBackend,
    ProviderKind,
    GameState,
    WorldState,
    NPCState,
    Dialogue,
    StoryBeat,
    NarrativeOutput,
)
from narrative_engine.api import create_app


def make_state(**kwargs):
    from narrative_engine import PlayerState
    player = PlayerState(**(kwargs.pop("player", {})))
    world = WorldState(**(kwargs.pop("world", {})))
    return GameState(player=player, world=world, **kwargs)


@pytest.fixture
def engine():
    return NarrativeEngine(EngineConfig(
        backend=LLMBackend(provider=ProviderKind.openai, model="gpt-test"),
        cache_enabled=False,
        memory_enabled=True,
        fallback_pool={"dialogue": ["测试降级"], "event": ["事件降级"], "description": ["描述降级"]},
    ))


@pytest.fixture
def client(engine):
    app = create_app(engine)
    return TestClient(app)


# ---- /health ----

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---- /tell 非流式 ----

def test_tell_non_stream(client, engine):
    def fake_gen(prompt, schema):
        return Dialogue(text="你好啊旅人。"), "raw", 10

    with patch.object(engine._director, "generate", side_effect=fake_gen):
        resp = client.post("/tell", json={
            "state": make_state(world={"area": "旧码头"}).model_dump(),
            "kind": "dialogue",
            "context": "打招呼",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "dialogue"
    assert data["dialogue"]["text"] == "你好啊旅人。"
    assert data["backend"] == "gpt-test"


def test_tell_non_stream_anchor(client, engine):
    engine._beat_manager.replace_beats([
        StoryBeat(id="anchor_http", trigger={"world.area": "灯塔"}, text="灯塔管理员默默点头。")
    ])

    resp = client.post("/tell", json={
        "state": make_state(world={"area": "灯塔"}).model_dump(),
        "kind": "dialogue",
        "context": "询问",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == "storybeat"
    assert "灯塔管理员默默点头" in data["dialogue"]["text"]


def test_tell_non_stream_fallback(client, engine):
    def fake_gen(prompt, schema):
        raise ConnectionError("boom")

    with patch.object(engine._director, "generate", side_effect=fake_gen):
        resp = client.post("/tell", json={
            "state": make_state(world={"area": "测试"}).model_dump(),
            "kind": "dialogue",
            "context": "随便",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == "fallback"
    assert data["dialogue"]["text"] == "测试降级"


# ---- /tell 流式 (SSE) ----

def test_tell_stream_sse(client, engine):
    partials = [
        Dialogue(text="今天"),
        Dialogue(text="今天的鱼"),
        Dialogue(text="今天的鱼不新鲜。", mood_change=0),
    ]

    def fake_stream(prompt, schema):
        for p in partials:
            yield p

    with patch.object(engine._director, "generate_stream", side_effect=fake_stream):
        resp = client.post("/tell", json={
            "state": make_state(world={"area": "测试"}).model_dump(),
            "kind": "dialogue",
            "context": "闲聊",
            "stream": True,
        })

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
    assert len(lines) >= 3  # 3 partials + [DONE]

    # 检查 partial 数据
    partial_line = lines[0]
    assert "partial" in partial_line
    assert "今天" in partial_line

    # 最后一行是 [DONE]
    assert "[DONE]" in lines[-1]


def test_tell_stream_anchor_sse(client, engine):
    engine._beat_manager.replace_beats([
        StoryBeat(id="anchor_sse", trigger={"world.area": "诊所"}, text="医生抬了抬眼镜。")
    ])

    resp = client.post("/tell", json={
        "state": make_state(world={"area": "诊所"}).model_dump(),
        "kind": "dialogue",
        "context": "看病",
        "stream": True,
    })

    assert resp.status_code == 200
    lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
    # 锚点：1 个完整结果 + [DONE]
    assert len(lines) == 2
    assert "医生抬了抬眼镜" in lines[0]
    assert "[DONE]" in lines[1]


def test_tell_stream_fallback_sse(client, engine):
    def fake_stream(prompt, schema):
        raise ConnectionError("中断")
        yield

    with patch.object(engine._director, "generate_stream", side_effect=fake_stream):
        resp = client.post("/tell", json={
            "state": make_state(world={"area": "测试"}).model_dump(),
            "kind": "dialogue",
            "context": "闲聊",
            "stream": True,
        })

    assert resp.status_code == 200
    lines = [l for l in resp.text.strip().split("\n") if l.startswith("data:")]
    assert len(lines) == 2
    assert "[DONE]" in lines[-1]


# ---- /story ----

def test_story_info(client, engine):
    resp = client.get("/story")
    assert resp.status_code == 200
    data = resp.json()
    assert "title" in data
    assert "chapter" in data
    assert "chapters" in data
    assert "npcs" in data


# ---- /story/load ----

def test_story_load(client):
    resp = client.post("/story/load", json={
        "story_dir": "stories/seaside_town",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chapter"] != ""


def test_story_load_with_chapter(client):
    resp = client.post("/story/load", json={
        "story_dir": "stories/seaside_town",
        "chapter": "chapter_1",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_story_load_bad_path(client):
    with pytest.raises(Exception):
        client.post("/story/load", json={
            "story_dir": "nonexistent_path",
        })


# ---- /story/chapters ----

def test_story_chapters(client):
    resp = client.get("/story/chapters")
    assert resp.status_code == 200
    data = resp.json()
    assert "chapters" in data


# ---- /story/chapter/switch ----

def test_chapter_switch(client):
    client.post("/story/load", json={"story_dir": "stories/seaside_town"})

    resp = client.post("/story/chapter/switch", json={"chapter": "chapter_1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chapter"] != ""


def test_chapter_switch_bad_name(client):
    client.post("/story/load", json={"story_dir": "stories/seaside_town"})

    with pytest.raises(ValueError, match="章节不存在"):
        client.post("/story/chapter/switch", json={"chapter": "nonexistent_chapter"})


# ---- /story/npcs/reload ----

def test_npcs_reload(client):
    client.post("/story/load", json={"story_dir": "stories/seaside_town"})

    resp = client.post("/story/npcs/reload")
    assert resp.status_code == 200
    assert "npcs" in resp.json()


def test_npcs_reload_no_story(client):
    app = create_app(NarrativeEngine())
    tc = TestClient(app)

    resp = tc.post("/story/npcs/reload")
    assert resp.status_code == 200
    assert resp.json()["npcs"] == []


# ---- NPC 自动补全 ----

def test_tell_with_npc_autocomplete(client, engine):
    engine._npcs["fishmonger"] = NPCState(id="fishmonger", name="鱼贩老李")

    def fake_gen(prompt, schema):
        return Dialogue(text="今天的鱼很新鲜。"), "raw", 5

    with patch.object(engine._director, "generate", side_effect=fake_gen):
        resp = client.post("/tell", json={
            "state": make_state(world={"area": "码头"}).model_dump(),
            "kind": "dialogue",
            "context": "问鱼价",
            "npc_id": "fishmonger",
        })

    assert resp.status_code == 200
    assert resp.json()["dialogue"]["text"] == "今天的鱼很新鲜。"
