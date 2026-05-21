# Narrative Engine 使用指南

## 目录

1. [概述](#概述)
2. [安装](#安装)
3. [API 配置](#api-配置)
4. [故事编写](#故事编写)
5. [Python SDK](#python-sdk)
6. [CLI 工具](#cli-工具)
7. [TUI 管理面板](#tui-管理面板)
8. [HTTP API](#http-api)
9. [记忆系统](#记忆系统)
10. [Prompt 策略](#prompt-策略)

---

## 概述

narrative-engine 是一个**底层叙事中间件**。接收结构化的游戏状态（玩家属性、世界参数、NPC 列表、历史记录），返回结构化的叙事内容（对话、事件、场景描述）。

### 四级流水线

```
GameState ──→ StoryBeat 锚点命中？ ──→ 返回手写文案
                │ 否
                ▼
              缓存命中？ ──→ 返回缓存结果
                │ 否
                ▼
              LLM 生成 ──→ 关键词过滤 ──→ 写入缓存 ──→ 返回
                │ 失败
                ▼
            降级保底文案
```

| 优先级 | 阶段 | 说明 |
|--------|------|------|
| 1 | **StoryBeat 锚点** | 手写内容，100% 可控 |
| 2 | **缓存** | diskcache 持久化，相同输入零成本返回 |
| 3 | **LLM 生成** | litellm + instructor，结构化输出 |
| 4 | **Fallback** | 配置的保底文案池 |

### 核心数据流

```
GameState (输入)                    NarrativeOutput (输出)
├── player: PlayerState             ├── kind: "dialogue"|"event"|"description"
│   ├── name: str                   ├── dialogue: Dialogue
│   ├── attributes: dict            │   ├── text: str
│   ├── inventory: list             │   ├── mood_change: int
│   ├── flags: dict                 │   └── unlock_hint: str
│   └── recent_actions: list        ├── event: Event
├── world: WorldState               │   ├── title: str
│   ├── area: str                   │   ├── description: str
│   ├── time: str                   │   ├── choices: list
│   ├── weather: str                │   └── consequences: dict
│   └── chapter: str                ├── description: Description
├── npcs: dict[str, NPCState]       │   ├── text: str
└── history: list                   │   └── mood: str
                                    ├── backend: str
                                    ├── tokens_used: int
                                    └── cached: bool
```

---

## 安装

```bash
# 基础安装
pip install -e .

# 含 TUI 管理面板
pip install -e ".[tui]"

# 含 HTTP API
pip install -e ".[api]"

# 开发依赖（测试用）
pip install -e ".[dev]"

# 全部
pip install -e ".[tui,api,dev]"
```

依赖：Python ≥ 3.11，pydantic ≥ 2.0，litellm ≥ 1.0，instructor ≥ 1.0，diskcache ≥ 5.0，jinja2 ≥ 3.0，pyyaml ≥ 6.0。

---

## API 配置

### API 格式

引擎支持两种 API 格式，通过 litellm 统一接口调用：

| 格式 | 说明 | 适用服务 |
|------|------|---------|
| `openai` | OpenAI 兼容 API | DeepSeek, Ollama, vLLM, 大多数国产模型 |
| `anthropic` | Anthropic 兼容 API | Claude 系列 |

### 配置方式

**方式一：环境变量**

```bash
export NARRATIVE_BACKEND=openai
export NARRATIVE_API_KEY=sk-your-api-key
export NARRATIVE_API_BASE=https://api.deepseek.com
export NARRATIVE_MODEL=deepseek-v4-pro
```

**方式二：TUI 配置页**

```bash
narrative-engine tui
```

进入 API 配置页（按键 `1`），填写：
- API 格式：选择 OpenAI 兼容或 Anthropic 兼容
- API Key：你的 API 密钥
- Base URL：API 端点地址
- Model：模型名称（如 `deepseek-v4-pro`）
- Temperature：生成温度 (0.0-2.0)

点击"测试连接"验证配置，点击"保存配置"持久化。

**方式三：代码中配置**

```python
from narrative_engine import NarrativeEngine
from narrative_engine.models.config import LLMBackend, ProviderKind, EngineConfig

backend = LLMBackend(
    provider=ProviderKind.openai,
    api_key="sk-xxxx",
    api_base="https://api.deepseek.com",
    model="deepseek-v4-pro",
    temperature=0.8,
)

engine = NarrativeEngine(EngineConfig(backend=backend))
```

### Model 名称解析规则

- `model="deepseek-v4-pro"` → 自动解析为 `openai/deepseek-v4-pro`
- `model="openai/deepseek-v4-pro"` → 包含 `/` 则保留不变（完整 litellm 路径）
- `model=""` → 使用默认模型（openai: `deepseek-v4-pro`, anthropic: `claude-sonnet-4-6`）

### 存储模式

API 配置支持两种存储方式，可在 TUI 中切换：

| 模式 | 说明 |
|------|------|
| 内存 | 进程级存储，退出后清空（默认） |
| 文件 | 持久化到 `~/.narrative_engine/config.json` |

---

## 故事编写

### 目录结构

```
stories/<故事名>/
├── story.yaml          # 故事元信息（标题、世界观、保底文案）
├── npcs.yaml           # NPC 定义（ID、名称、性格、情绪、预设记忆）
└── chapters/
    ├── chapter_1.yaml  # 章节 1（标题、世界观覆盖、beats、保底文案）
    └── chapter_2.yaml  # 章节 2
```

故事目录支持两种格式：
- **新格式（推荐）**：story.yaml + npcs.yaml + chapters/ 独立文件
- **旧格式（兼容）**：单个 story.yaml 包含所有内容

### story.yaml — 故事元信息

```yaml
title: 海边小镇

# 默认世界观（被各章节继承，可被章节级 world 覆盖）
default_world:
  setting: |
    一个克苏鲁题材的海边小镇，诡异与日常并存。
    小镇居民对异常现象习以为常，把它们当作生活的一部分。
  tone: eerie               # neutral / peaceful / eerie / tense / dread
  era: 模糊的近代

# 默认保底文案（LLM 调用失败时随机选取）
default_fallback:
  dialogue:
    - "……"
    - "（沉默）"
    - "风吹过，没有人说话。"
  event:
    - "远处有什么东西动了一下，但你没看清。"
    - "水面泛起一圈圈涟漪，然后恢复了平静。"
  description:
    - "海风带着咸味和淡淡的腥味。"
    - "远处的灯塔在雾气中明灭。"
```

### npcs.yaml — NPC 定义

```yaml
npcs:
  fishmonger_li:
    name: 鱼贩老李
    mood: grumpy             # neutral / happy / sad / angry / excited / calm / peaceful
    traits:                  # 性格标签，注入对话 prompt
      - 沉默寡言
      - 认识奶奶
      - 二十年老摊主
    relationship: 0.0        # 与玩家亲密度 (-10 ~ 10)
    preset_memories:         # 预设记忆，加载故事时写入 NPC 长期记忆
      - content: 二十年前欠奶奶一碗汤，至今记得那个味道
        importance: 8

  lighthouse_keeper:
    name: 灯塔守灯人
    mood: mysterious
    traits:
      - 从不说话
      - 只在黄昏出现
      - 手里永远提着一盏不灭的灯
```

NPCState 完整字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 唯一标识符 |
| `name` | str | 显示名称 |
| `mood` | str | 当前情绪，影响 temperature 调整 |
| `traits` | list[str] | 性格标签，注入 prompt |
| `relationship` | float | 与玩家亲密度 (-10 ~ 10) |
| `preset_memories` | list[dict] | 预设记忆 `{content, importance}` |
| `extra` | dict | 扩展字段 |

### 章节文件 (chapters/*.yaml)

```yaml
title: 第一章 · 抵达

# 章节级世界观（覆盖 story.yaml 的 default_world）
world:
  setting: 玩家刚抵达小镇，一切都还很陌生。
  tone: eerie

# StoryBeat 锚点列表
beats:
  - id: prologue_arrival
    kind: description
    priority: 100
    trigger:
      world.area: grandma_house
    text: "你站在奶奶的老房子前。相机挂在脖子上，镜头盖内刻着一行字。"
    mood: eerie
    unlocks:
      - chapter1_start

# 章节级保底文案（覆盖 story.yaml 的 default_fallback）
fallback:
  dialogue:
    - "这个镇上的人说话都很奇怪。"
```

---

## Python SDK

### 初始化引擎

```python
from narrative_engine import NarrativeEngine

# 方式一：从故事目录加载
engine = NarrativeEngine.from_story("stories/seaside_town")

# 方式二：从配置目录加载（config/engine.yaml + config/world.yaml + ...）
engine = NarrativeEngine.from_config_dir("config")

# 方式三：编程式构造
from narrative_engine.models.config import EngineConfig, LLMBackend, ProviderKind

backend = LLMBackend(
    provider=ProviderKind.openai,
    api_key="sk-xxxx",
    api_base="https://api.deepseek.com",
    model="deepseek-v4-pro",
)
config = EngineConfig(
    backend=backend,
    cache_enabled=True,
    filter_enabled=True,
    memory_enabled=True,
)
engine = NarrativeEngine(config)
```

### 构建 GameState

```python
from narrative_engine import GameState, PlayerState, WorldState, NPCState

state = GameState(
    player=PlayerState(
        name="悠悠",
        attributes={"san": 72, "str": 10},
        inventory=["旧相机", "奶奶的钥匙"],
        flags={"met_li": True, "chapter1_complete": False},
        recent_actions=["在码头钓鱼", "捡到漂流瓶"],
    ),
    world=WorldState(
        area="old_dock",
        time="夜晚",
        weather="雾",
        chapter="第一章",
    ),
    npcs={
        "fishmonger_li": NPCState(
            id="fishmonger_li",
            name="鱼贩老李",
            mood="grumpy",
            traits=["沉默寡言", "认识奶奶"],
        ),
    },
)
```

### 生成叙事内容

```python
# 对话
result = engine.tell(state, kind="dialogue", npc_id="fishmonger_li",
                     context="玩家把旧靴子拿给鱼贩看")
print(result.dialogue.text)       # "你奶奶……欠我一碗汤。二十年了。"
print(result.dialogue.mood_change) # -1
print(result.backend)             # "storybeat" | "openai/deepseek-v4-pro" | "fallback"

# 事件
result = engine.tell(state, kind="event", context="玩家在码头待到深夜")
print(result.event.title)
print(result.event.choices)       # ["举起相机", "慢慢后退", "扔一块石头"]

# 场景描述
result = engine.tell(state, kind="description", context="第一次站在老房子前")
print(result.description.text)
print(result.description.mood)    # "eerie"
```

### 异步 API

```python
import asyncio

async def main():
    engine = NarrativeEngine.from_story("stories/seaside_town")

    # 异步加载
    await engine.load_story_async("stories/seaside_town")

    # 异步生成
    result = await engine.tell_async(state, kind="dialogue", npc_id="fishmonger_li")

    # 异步流式
    async for partial in engine.tell_stream_async(state, kind="event"):
        if hasattr(partial, "text"):
            print(partial.text, end="", flush=True)
```

### 流式生成

```python
# 同步流式
for partial in engine.tell_stream(state, kind="dialogue", npc_id="fishmonger_li"):
    if hasattr(partial, "text"):
        print(partial.text, end="", flush=True)
    elif hasattr(partial, "dialogue"):
        # 完整 NarrativeOutput（锚点命中时直接 yield）
        print(f"\n[锚点] {partial.dialogue.text}")
```

### 章节和 NPC 管理

```python
# 章节
print(engine.list_chapters())          # ["chapter_1", "chapter_2"]
print(engine.current_chapter)          # "第一章 · 抵达"
engine.switch_chapter("chapter_2")

# NPC
print(list(engine.npcs.keys()))        # ["fishmonger_li", "lighthouse_keeper", ...]
engine.reload_npcs()                   # 从 npcs.yaml 热重载

# 状态持久化
engine.save_state()                    # 保存已触发的 beat 状态
engine.load_state()                    # 恢复
```

### 访问内部组件

```python
# 记忆系统
if engine.memory:
    engine.memory.remember("fishmonger_li", "玩家帮忙修好了渔网", importance=5)
    records = engine.memory.recall("fishmonger_li", limit=10)
    engine.memory.new_session()  # 重置会话上下文

# 缓存
if engine._cache:
    engine._cache.clear()

# Beat 管理
print(engine.beat_manager.pending)     # 待触发 beats
print(engine.beat_manager.fired)       # 已触发 beats
```

---

## CLI 工具

```bash
narrative-engine <command> [options]
```

### 子命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `dialogue` | 生成对话 | `narrative-engine dialogue --area "码头" --npc "fishmonger_li" --context "..."` |
| `event` | 生成事件 | `narrative-engine event --area "海边" --context "捡到漂流瓶"` |
| `describe` | 生成描述 | `narrative-engine describe --area "废弃灯塔"` |
| `shell` | 交互模式 | `narrative-engine shell` |
| `serve` | HTTP API | `narrative-engine serve --story stories/seaside_town --port 8000` |
| `tui` | TUI 面板 | `narrative-engine tui` |

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NARRATIVE_BACKEND` | API 格式 | `openai` |
| `NARRATIVE_API_KEY` | API 密钥 | (空) |
| `NARRATIVE_API_BASE` | API 端点 URL | (空) |
| `NARRATIVE_MODEL` | 模型名称 | (空，使用默认) |

### 交互模式

```bash
narrative-engine shell
> dialogue 旧码头 fishmonger_li 玩家钓上一只旧靴子
{
  "kind": "dialogue",
  "dialogue": {"text": "今天的鱼不新鲜。", "mood_change": 0},
  ...
}
> quit
```

---

## TUI 管理面板

```bash
narrative-engine tui
```

### 页面导航

| 按键 | 页面 | 功能 |
|------|------|------|
| `1` | API 配置 | 选择 API 格式、填入 Key/Base URL/Model/ Temperature、测试连接、保存配置 |
| `2` | 故事管理 | 加载/新建故事、章节列表与切换、NPC 热重载 |
| `3` | NPC 编辑 | NPC 列表、属性编辑表单（name/mood/traits/relationship/memories）、写入文件 |
| `4` | 交互测试 | 参数输入（area/npc_id/context/kind）、流式/非流式生成、会话历史 |
| `5` | 记忆查看 | NPC 长期记忆和会话历史查看、清空/导出 |

键盘 `q` 退出，也可用鼠标点击左侧边栏切换页面。

---

## HTTP API

```bash
narrative-engine serve --story stories/seaside_town --host 0.0.0.0 --port 8000
```

### 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查，返回引擎状态 |
| `/tell` | POST | 非流式叙事生成 |
| `/tell/stream` | POST | SSE 流式叙事生成 |
| `/story/info` | GET | 当前故事标题、章节、NPC 列表 |
| `/story/chapters` | GET | 所有章节列表 |
| `/story/chapter/{name}` | POST | 切换到指定章节 |
| `/story/npcs/reload` | POST | 从 npcs.yaml 热重载 NPC |

### 请求格式

```json
POST /tell
{
  "state": {
    "player": {"name": "悠悠", "attributes": {"san": 72}},
    "world": {"area": "old_dock", "time": "night"}
  },
  "kind": "dialogue",
  "context": "玩家钓上旧靴子",
  "npc_id": "fishmonger_li"
}
```

### 流式响应 (SSE)

```bash
curl -N -X POST http://localhost:8000/tell/stream \
  -H "Content-Type: application/json" \
  -d '{"state":{"world":{"area":"码头"}},"kind":"dialogue","context":"你好"}'
```

事件类型：`partial`（流式片段）→ `result`（最终完整结果）→ `done`

---

## 记忆系统

### 两层架构

| 层级 | 类型 | 生命周期 | 用途 |
|------|------|---------|------|
| Session | 短期 | 当前会话 | 维护对话上下文，最近 N 轮注入 prompt |
| Memory | 长期 | 跨会话持久化 | NPC 对玩家的持久记忆，JSON 文件存储 |

### 配置

```python
config = EngineConfig(
    memory_enabled=True,
    memory_size=20,      # 每个 NPC 最多记忆条数
    session_turns=5,     # prompt 中包含的最近轮数
    memory_path=".state/memories.json",
)
```

### 记忆淘汰策略

- 按 `importance` 降序、`timestamp` 降序排列
- 超过 `memory_size` 条时淘汰低重要性的旧记忆
- 完全相同内容自动去重

### 编程接口

```python
# 写入记忆
engine.memory.remember("fishmonger_li", "玩家帮忙修好了渔网", importance=5)

# 召回记忆（按重要性排序）
records = engine.memory.recall("fishmonger_li", limit=10)
for r in records:
    print(f"[{r.kind}] {r.content} (重要性: {r.importance})")

# 导出会话上下文（注入 prompt）
context = engine.memory.session_context()

# 新建会话（清空短期上下文）
engine.memory.new_session()

# 清空全部记忆
engine.memory.clear()
```

---

## Prompt 策略

### Temperature 动态调整

TemperatureProfile 根据叙事类型和 NPC 情绪微调 temperature：

```python
# 默认调整量
kind_adjustments = {
    "dialogue": -0.05,    # 对话稍保守
    "event": 0.1,         # 事件需要更多创意
    "description": 0.0,   # 描述不变
}

mood_adjustments = {
    "angry": 0.15,        # 愤怒时更不可预测
    "excited": 0.1,
    "calm": -0.1,         # 平静时更稳定
    "peaceful": -0.1,
    "sad": -0.05,
}
```

可在 LLMBackend 中禁用：
```python
backend = LLMBackend(
    temperature_profile=TemperatureProfile(enabled=False),
)
```

### NPC Persona 注入

对话生成时自动将 NPC 性格信息注入 prompt：

```
## 你的角色
你是 鱼贩老李。性格特点：沉默寡言、认识奶奶、二十年老摊主。
当前情绪：grumpy。与玩家的关系亲密度：0.0。
```

### 自适应重试

LLM 调用失败后自动以 `temperature × 0.6` 重试一次，处理网络超时等临时性错误。
