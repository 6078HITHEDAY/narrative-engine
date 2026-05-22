# Narrative Engine 使用指南

## 目录

1. [概述](#概述)
2. [安装](#安装)
3. [API 配置](#api-配置)
4. [故事编写](#故事编写)
5. [如何写自己的故事](#如何写自己的故事)
6. [Python SDK](#python-sdk)
7. [AI 驱动互动剧情](#ai-驱动互动剧情)
8. [CLI 工具](#cli-工具)
9. [TUI 管理面板](#tui-管理面板)
10. [HTTP API](#http-api)
11. [启动验证](#启动验证)
12. [记忆系统](#记忆系统)
13. [Prompt 策略](#prompt-策略)

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

## 如何写自己的故事

引擎不绑定任何具体题材——所有剧情内容（世界观、NPC、锚点、保底文案）都活在 `stories/<故事名>/` 一个文件夹里，src/ 不需要改一行。

### 完整参考

`stories/seaside_town/` 是开箱即用的完整示例（克苏鲁海边小镇）：

```
stories/seaside_town/
├── story.yaml          # 世界观 + 默认保底文案
├── npcs.yaml           # NPC 定义（性格、情绪、预设记忆）
└── chapters/
    └── chapter_1.yaml  # 章节 + StoryBeat 锚点 + 章节级保底
```

打开这三个文件就能看到一个能跑的故事长什么样。**写自己的故事 = 复制这个目录结构 → 替换内容 → 不动 src/**。

### 三个文件各装什么

| 文件 | 装什么 | 引擎怎么用 |
|------|--------|----------|
| `story.yaml` | 故事标题、`default_world`（世界观）、`default_fallback`（LLM 失败时的保底文案池） | 加载时解析为 `StoryMeta`，注入 prompt 顶端的"世界观设定" |
| `npcs.yaml` | NPC 列表（id / name / mood / traits / relationship / preset_memories） | 加载时实例化为 `NPCState`，写入引擎 `_npcs`；预设记忆灌入长期记忆 |
| `chapters/*.yaml` | 章节标题、章节级 `world` 覆盖、`beats` 锚点列表、章节级 `fallback` 覆盖 | 切章节时替换 `BeatManager` 的 beats，覆盖 world_setting 和 fallback_pool |

各字段语义和最小示例见上一节 [故事编写](#故事编写)，完整示例直接看 `stories/seaside_town/`。

### 跑起来

```bash
# 终端交互
python examples/interactive_demo.py stories/<your_story>

# HTTP API
narrative-engine serve --story stories/<your_story>

# 作为库引入
engine = NarrativeEngine.from_story("stories/<your_story>")
```

### 换题材时调整 prompt 模板

默认 `.j2` 模板带轻微克苏鲁味（写在 `description.j2` 里："可以略带克苏鲁式的诡异感"）。换题材时按需用 `PromptTemplates` 覆盖，见后文 [自定义 prompt 模板](#自定义-prompt-模板)。**模板覆盖是"语气调整"——故事内容仍只在 `stories/` 里。**

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

## AI 驱动互动剧情

引擎自身只生成**单回合**叙事内容；要把它接成**互动循环**，需要把玩家的选择反馈进 GameState，再调下一轮 `tell()`。这一节讲完整范式。

### 闭环范式

```
┌────────────────────────────────────────────────────┐
│  tell(kind="event")  →  Event(choices=[...])       │
│         ↑                       │                  │
│         │                       │ 玩家选了 "举起相机"│
│         │                       ▼                  │
│         │   apply_choice(state, event, choice)     │
│         │                       │                  │
│         │                       ▼                  │
│         │   recent_actions += ["举起相机"]          │
│         │   history += ["事件「...」：选择了「举起相机」"]│
│         │                       │                  │
│         └───────────────────────┘                  │
│       下一轮 tell() 自动看到玩家最近行动             │
└────────────────────────────────────────────────────┘
```

### `apply_choice()` 方法

```python
def apply_choice(self, state: GameState, event: Event, choice: str) -> GameState:
    ...
```

| 参数 | 说明 |
|------|------|
| `state` | 当前 GameState（会被原地修改） |
| `event` | 上一轮 `tell(kind="event")` 返回的 `Event` |
| `choice` | 玩家选的字符串，必须在 `event.choices` 中 |

返回被修改的 state（同一对象）。`choice` 不在 `event.choices` 中时抛 `ValueError`。

引擎只把选择写入 `state.player.recent_actions` 和 `state.history`——**物品消耗、属性变化、解锁标志由游戏层处理**。这条边界让引擎对任何题材都通用。

### 最小互动循环示例

```python
from narrative_engine import NarrativeEngine, GameState, PlayerState, WorldState

engine = NarrativeEngine.from_story("stories/seaside_town")

state = GameState(
    player=PlayerState(name="悠悠", inventory=["相机"]),
    world=WorldState(area="old_dock", time="夜晚"),
)

# 1. 引擎生成事件
result = engine.tell(state, kind="event", context="深夜站在码头")
event = result.event
print(f"事件：{event.title}\n{event.description}")
for i, c in enumerate(event.choices):
    print(f"  {i+1}. {c}")

# 2. 玩家选一个
choice = event.choices[0]

# 3. 把选择写回 state
engine.apply_choice(state, event, choice)

# 4. 游戏层自行处理后果（引擎不管）
if "举起相机" in choice:
    state.player.inventory.append("怪物的照片")  # 业务逻辑

# 5. 下一轮 tell() — prompt 自动包含 recent_actions
next_result = engine.tell(state, kind="description", context="拍完之后")
print(next_result.description.text)
```

### 玩家视角注入到 prompt

引擎在渲染 prompt 模板时，会把以下两个字段（如果非空）以醒目段落注入末尾：

- `state.player.inventory: list[str]` — 当前持有物
- `state.player.recent_actions: list[str]` — 最近行动（取最后 3 条）

模板片段（出现在所有内置 `.j2` 中）：

```jinja
{% if state.player.inventory %}
玩家持有：{{ state.player.inventory | join("、") }}
{% endif %}
{% if state.player.recent_actions %}
最近行动：{{ state.player.recent_actions[-3:] | join(" → ") }}
{% endif %}
```

**为什么显式抽出来**：完整 `state_json` 嵌套很深，AI 容易忽略字段；提到末尾让模型感知更明确。

**为什么用条件渲染**：纯对话游戏 / 视觉小说不一定需要 inventory 概念，留空时这两段不出现，不污染 prompt。

**字段都是 `list[str]`**：作者可以放任意字符串——「相机」、「数据卡」、「断剑」、「黑曜石碎片」——引擎不关心内容含义。

### 自定义 prompt 模板

如果默认模板的"克苏鲁味"不符合你的题材（比如你写的是赛博朋克或武侠），可以通过 `PromptTemplates` 全量覆盖：

```python
from narrative_engine import NarrativeEngine, EngineConfig, PromptTemplates

custom = PromptTemplates(
    dialogue="""
你是赛博朋克世界的 NPC：{{ npc.name if npc else "路人" }}。
{% if npc %}性格：{{ npc.traits | join("、") }}。情绪：{{ npc.mood }}。{% endif %}

世界观：{{ world_setting }}
当前状态：{{ state_json }}

{% if state.player.inventory %}
玩家持有：{{ state.player.inventory | join("、") }}
{% endif %}

{{ context }}

请生成一句 NPC 对话，要带街头黑话。返回 JSON：
{"text": "...", "mood_change": 0, "unlock_hint": null}
""",
    event="...",          # 同样可覆盖 event 模板
    description="...",    # 同样可覆盖 description 模板
)

engine = NarrativeEngine(EngineConfig(prompt_templates=custom))
```

`PromptTemplates`（`models/config.py:96`）的三个字段对应三种 `kind`，留空就回退到内置 `.j2`。变量集与内置一致：`world_setting / state / state_json / context / session_context / memory_context / npc`。

完整可运行的互动 demo 见 `examples/interactive_demo.py`，支持 `talk`、`event`、`choose`、`pick`、`drop`、`inv` 等命令。

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
| `/health` | GET | 健康检查 |
| `/tell` | POST | 叙事生成（非流式 / 流式由 body 中 `stream: true` 切换） |
| `/story` | GET | 当前故事标题、章节、NPC 列表 |
| `/story/load` | POST | 加载/切换到指定 story_dir |
| `/story/chapters` | GET | 所有章节列表 |
| `/story/chapter/switch` | POST | 切换到指定章节（body: `{"chapter": "<name>"}`） |
| `/story/npcs/reload` | POST | 从 npcs.yaml 热重载 NPC |

### 请求格式

```json
POST /tell
{
  "state": {
    "player": {"name": "player", "attributes": {"hp": 100}},
    "world": {"area": "marketplace", "time": "noon"}
  },
  "kind": "dialogue",
  "context": "玩家询价",
  "npc_id": "trader",
  "stream": false
}
```

### 流式响应 (SSE)

把请求体里的 `stream` 设成 `true` 即可：

```bash
curl -N -X POST http://localhost:8000/tell \
  -H "Content-Type: application/json" \
  -d '{"state":{"world":{"area":"marketplace"}},"kind":"dialogue","context":"你好","stream":true}'
```

事件流：每个 `data:` 是一行 `partial` JSON，最后一条是 `[DONE]`。

---

## 启动验证

`pytest` 通过不代表三个表面（CLI / HTTP / TUI）能正常起来——routes 装配、TUI screen mount、CLI 入口的 import 错误，单元测试都不一定能挡住。仓库里 `.claude/skills/run/` 提供了一个 driver，把三个表面都点一遍。

### 一键跑

```bash
.claude/skills/run/driver.sh           # CLI + HTTP + TUI 全跑
.claude/skills/run/driver.sh cli       # 只验 CLI
.claude/skills/run/driver.sh http      # 只验 HTTP
.claude/skills/run/driver.sh tui       # 只验 TUI（headless）
```

退出码非零代表至少一个表面挂了。

### 各表面验证语义

| 表面 | 验证内容 | 是否需要 LLM key |
|------|---------|----------------|
| CLI  | `narrative-engine` 无参运行，stdout 含版本号 | 否 |
| HTTP | uvicorn 起来 → `GET /health` → `GET /story` → `POST /tell`（beat-anchored payload） | 否（默认走锚点） |
| TUI  | `App.run_test()` 跑一次事件循环，5 个 screen 全部 mount 成功 | 否 |

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `STORY` | `stories/seaside_town` | 故事目录 |
| `PORT`  | `18234` | HTTP 端口 |
| `HOST`  | `127.0.0.1` | HTTP 监听地址 |
| `NO_TELL` | `0` | 设 `1` 跳过 `/tell` 探测（用于非 seaside_town 故事，beat 锚点不会命中） |
| `TELL_PAYLOAD_FILE` | — | 自定义 `/tell` payload 的 JSON 文件路径 |

### `/tell` 探测细节

driver 默认发的 payload：

```json
{"state":{"world":{"area":"grandma_house","chapter":"第一章"}},"kind":"description","context":""}
```

这份状态命中 `stories/seaside_town/chapters/chapter_1.yaml` 里的 `prologue_arrival` beat（`world.area: grandma_house` + `world.chapter: 第一章`），所以走 StoryBeat 锚点直接返回手写文案，**不需要 LLM key**。

失败判定：

- `kind` 不是 `description` → payload 编码挂了（多半是 locale 问题，driver 已经用 heredoc 写文件 + `curl -d @file` 规避了 `env -i` 下的 UTF-8 字面量被打成 `?`）
- `degraded:true` → 锚点没命中，引擎降级到 LLM，但又没 API key → 报错并提示设 `NARRATIVE_API_KEY` 或 `NO_TELL=1`

换故事时，要么 `NO_TELL=1` 跳过 `/tell`，要么用 `TELL_PAYLOAD_FILE` 指向一份能命中你自己 chapter 1 锚点的 payload。

### 失败排查

| 症状 | 多半是 |
|------|--------|
| `.venv not found` | 还没装环境，先 `pip install -e ".[api,tui,dev]"` |
| `需要安装 API 依赖` | 装的是基础 extras，补 `[api]` |
| `/health` 15s 超时 | 端口被占 / 别的 uvicorn 没退干净 → `lsof -i:18234` |
| TUI smoke 抛 `ImportError: textual` | 缺 `[tui]` extras |
| TUI smoke 抛 `compose()` 异常 | 改坏了某个 screen，看 traceback 定位 `src/narrative_engine/tui/screens/*.py` |

详细文档见 `.claude/skills/run/SKILL.md`。

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
