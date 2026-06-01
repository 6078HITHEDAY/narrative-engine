# Narrative Engine 使用指南

## 目录

1. [概述](#概述)
2. [安装](#安装)
3. [API 配置](#api-配置)
4. [故事编写](#故事编写)
5. [如何写自己的故事](#如何写自己的故事)
6. [Python SDK](#python-sdk)
7. [AI 驱动互动剧情](#ai-驱动互动剧情)
8. [自然语言驱动（傻瓜模式）](#自然语言驱动傻瓜模式)
9. [AI 总编剧（故事生成器）](#ai-总编剧故事生成器)
10. [CLI 工具](#cli-工具)
11. [TUI 管理面板](#tui-管理面板)
12. [HTTP API](#http-api)
13. [启动验证](#启动验证)
14. [进阶参考](#进阶参考)

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

异步 API、流式生成、章节/NPC 管理、内部组件访问见 [reference.md](reference.md)。

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

玩家视角注入（inventory/recent_actions 如何进入 prompt）和自定义 prompt 模板见 [reference.md](reference.md)。完整互动 demo：`examples/interactive_demo.py`，支持 `talk`、`event`、`choose`、`pick`、`drop`、`inv` 等命令。

---

## 自然语言驱动（傻瓜模式）

傻瓜模式是引擎最高层封装——玩家直接用自然语言输入（"去码头看看"、"跟鱼贩聊天"、"选第一项"），引擎内部调一次 LLM 做意图路由，自动判定 `kind`、选择 `npc_id`、切换 `world.area`、响应待处理的 event 选项，再走正常的四级流水线出文案。

### 快速体验

```bash
# CLI 一行启动
narrative-engine play stories/seaside_town

# 或用 Python 脚本
python examples/auto_demo.py stories/seaside_town
```

进入 REPL 后直接输入自然语言：

```
故事: 海边小镇
章节: 第一章 · 抵达
NPC: ['fishmonger_li', 'lighthouse_keeper']
傻瓜模式：直接输入自然语言（输入 quit 退出）

> 去老房子看看
  · 切到: grandma_house
[description/storybeat] 你站在奶奶的老房子前。相机挂在脖子上，镜头盖内刻着一行字。

> 跟鱼贩老李聊聊今天的渔获
  · 切到: old_dock
[fishmonger_li/dialogue/openai/deepseek-v4-pro] 今天的鱼不新鲜。你要是想买，等明天早潮吧。

> 深夜在码头待到很晚
  · 切到: old_dock
[event/openai/deepseek-v4-pro] 事件: 暗处有东西在看你
  水面下有什么巨大的轮廓缓缓滑过……
  1. 举起相机
  2. 慢慢后退
  3. 扔一块石头

> 我选第一个
[description/openai/deepseek-v4-pro] 取景框里的画面让你的手止不住地颤抖...

> quit
```

每次输入后，引擎输出 `[kind/backend]` 标签，让你知道走的是锚点 (`storybeat`)、缓存还是 LLM。

### 意图路由机制

`AutoNarrator` 每轮调一次 LLM（轻量 `AutoIntent` schema）做三件事：

1. **判定叙事类型**：分析用户输入决定该出 dialogue / event / description
2. **选择交互目标**：如果用户提到 NPC 名字，自动匹配 `npc_id`
3. **检测场景切换**：用户说"去码头"就切 `world.area = "old_dock"`
4. **响应待处理选项**：如果上一轮引擎出了 event（带 choices），用户说"选第一个"时自动调 `apply_choice()` 推进剧情

路由失败的极端情况（如 LLM 不可用）会退回到默认 description + 当前 area，不会中断交互。

`AutoNarrator` SDK 编程接口（`AutoIntent` 字段、交互循环模板）见 [reference.md](reference.md)。完整示例：`examples/auto_demo.py`。

---

## AI 总编剧（故事生成器）

StoryGenerator 接收一句自然语言灵感，调用 LLM 一次性生成完整的故事目录——`story.yaml` + `npcs.yaml` + `chapters/*.yaml`，落盘后立即可被 `NarrativeEngine.from_story()` 加载。

### CLI 生成

```bash
narrative-engine generate --idea "赛博朋克背景的侦探故事，主角是退役义体医生" --out stories/cyber_detective

# 可选参数
narrative-engine generate \
  --idea "魔法学院里的学生会选举暗流涌动" \
  --out stories/magic_academy \
  --npcs 5 \
  --beats 8 \
  --overwrite
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--idea` | 故事灵感（自然语言，支持中英文） | (必填) |
| `--out` | 输出目录 | (自动从 idea 生成 slug) |
| `--npcs` | 生成 NPC 数量 | `3` |
| `--beats` | 每章生成 StoryBeat 数量 | `5` |
| `--overwrite` | 强制覆盖已存在的目录 | 否 |

如果不传 `--idea`，CLI 会交互式提示输入。

### 生成结果

```
stories/cyber_detective/
├── story.yaml          # 标题 + default_world + 保底文案池
├── npcs.yaml           # 3-5 个 NPC（性格、情绪、预设记忆）
└── chapters/
    ├── chapter_1.yaml  # 第一章（world 覆盖 + beats 锚点）
    ├── chapter_2.yaml  # 第二章
    └── chapter_3.yaml  # 第三章
```

生成后立即可用：

```bash
narrative-engine serve --story stories/cyber_detective
narrative-engine play stories/cyber_detective
```

`StoryGenerator` SDK 编程接口（同步/异步、显式 `LLMBackend` 配置）见 [reference.md](reference.md)。完整示例：`examples/generate_story.py`。

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
| `generate` | AI 生成故事目录 | `narrative-engine generate --idea "赛博朋克武侠江湖" --out stories/cyber_wuxia` |
| `play` | 自然语言傻瓜模式 | `narrative-engine play stories/seaside_town` |
| `shell` | 交互模式 | `narrative-engine shell` |
| `serve` | HTTP API | `narrative-engine serve --story stories/seaside_town --port 8000` |
| `tui` | TUI 面板 | `narrative-engine tui` |

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NARRATIVE_BACKEND` | API 格式 (`openai` / `anthropic`) | `openai` |
| `NARRATIVE_API_KEY` | API 密钥 | (空) |
| `NARRATIVE_API_BASE` | API 端点 URL | (空) |
| `NARRATIVE_MODEL` | 模型名称 | (空，使用默认) |
| `NARRATIVE_STRUCTURED_OUTPUT_MODE` | 结构化输出模式 (`tools` / `json`) | (空，自动探测) |
| `NARRATIVE_REASONING_MODEL` | 是否启用 reasoning 模式 | (空) |
| `NARRATIVE_REASONING_MAX_TOKENS` | reasoning 模式最大 token 数 | (空) |
| `NARRATIVE_GENERATOR_MAX_TOKENS` | story generator 最大 token 数 | `8192` |

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

请求/响应格式和 SSE 流式细节见 [reference.md](reference.md)。

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

Driver 的环境变量、`/tell` 探测细节和失败排查见 [reference.md](reference.md)。

---

## 进阶参考

以上覆盖了从安装到第一个互动故事的核心路径。以下主题见 [reference.md](reference.md)（API 与配置参考）：

| 主题 | 说明 |
|------|------|
| Python SDK 进阶 | `tell_async`、`tell_stream`、章节/NPC 管理、内部组件访问 |
| 互动剧情深度 | 玩家视角注入、自定义 prompt 模板 |
| 傻瓜模式 SDK | `AutoNarrator` API、`AutoIntent` 字段、交互循环模板 |
| AI 总编剧 SDK | `StoryGenerator` 同步/异步 API、显式 `LLMBackend` 配置 |
| HTTP API 详细 | 请求/响应格式、SSE 流式细节 |
| 记忆系统 | 两层架构、淘汰策略、编程接口 |
| Prompt 策略 | Temperature 动态调整、NPC Persona 注入、自适应重试 |
| 环境变量完整参考 | 全部 8 个环境变量 + `LLMBackend` 字段对照 |
| 高级配置 | Structured Output 模式、Reasoning Model、过滤器、缓存、ConfigInterpreter |
