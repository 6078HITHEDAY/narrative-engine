# narrative-engine

**通用 AI 互动叙事引擎**。输入结构化游戏状态，输出结构化叙事内容（对话/事件/场景描述）；锚点系统让作者保留剧情控制权，AI 填充剩余血肉。任何 "固定骨架 + AI 血肉" 的叙事项目都能复用——文字冒险、视觉小说、生活模拟、TRPG 跑团辅助、克苏鲁/恐怖叙事。

## 这是什么

narrative-engine 是一个**底层叙事中间件**。

> 接收结构化的游戏状态（玩家属性、世界参数、NPC 列表、持有物、历史），返回结构化的叙事内容；通过 `apply_choice()` 把玩家选择反馈进状态，驱动下一轮生成，构成完整的互动循环。

引擎不绑定任何具体游戏——`stories/seaside_town/` 是参考实现，作者按目录约定（`story.yaml` / `npcs.yaml` / `chapters/`）写自己的故事即可，无需改 `src/` 任何代码。

## 目标场景

| 项目类型 | 引擎能做的 |
|----------|-----------|
| 文字冒险 / 视觉小说 | NPC 对话生成、分支事件 + choice 闭环 |
| 生活模拟 | 场景描述、随机支线事件、NPC 关系记忆 |
| TRPG 跑团辅助 | DM 视角的事件推进 + NPC 反应生成 |
| 克苏鲁 / 恐怖叙事 | 氛围描述、随状态恶化的扭曲文本 |
| 嵌入既有游戏引擎 | 作为 Python 库供 Godot/Unity/Web 后端调用 |

## 两种用法

**独立运行**（开箱即用）：

```bash
narrative-engine tui                                    # TUI 管理面板
narrative-engine serve --story stories/seaside_town     # HTTP API
python examples/interactive_demo.py stories/<your>      # 终端交互 demo
```

**作为库引入**（嵌入你的游戏）：

```python
from narrative_engine import NarrativeEngine
engine = NarrativeEngine.from_story("stories/<your_story>")
result = engine.tell(state, kind="dialogue", npc_id="...")
engine.apply_choice(state, result.event, choice_text)   # choice 反馈
```

## 核心设计

```
GameState ──→ StoryBeat 锚点命中？ ──→ 返回手写文案
   ↑            │ 否
   │            ▼
   │          缓存命中？ ──→ 返回缓存结果
   │            │ 否
   │            ▼
   │          LLM 生成 ──→ 关键词过滤 ──→ 写入缓存 ──→ 返回
   │            │ 失败
   │            ▼
   │        降级保底文案
   │
   └── apply_choice(state, event, choice) ←── 玩家选了选项
```

### 四级流水线

| 优先级 | 阶段 | 说明 |
|--------|------|------|
| 1 | **StoryBeat 锚点** | 手写内容，100% 可控。支持精确匹配、比较运算符、正则、$or/$not 组合条件 |
| 2 | **缓存** | 相同 state + context + kind + model 命中 diskcache，零成本返回 |
| 3 | **LLM 生成** | 通过 litellm + instructor 调用大模型，结构化输出自动 schema 校验 |
| 4 | **Fallback** | 所有路径失败时返回配置的保底文案池 |

## 多后端支持

通过 litellm 统一接口，支持两种 API 格式：

| API 格式 | 适用服务 | base_url 示例 |
|----------|---------|---------------|
| **OpenAI 兼容** | DeepSeek, Ollama, vLLM, 等 | `https://api.deepseek.com` |
| **Anthropic 兼容** | Claude 系列 | `https://api.anthropic.com` |

只需选择 API 格式，填入 base_url、API Key 和 model 即可。不再硬编码特定提供商。

## 安装

```bash
# 基础安装
pip install -e .

# 含 TUI 管理面板
pip install -e ".[tui]"

# 含 HTTP API
pip install -e ".[api]"

# 全部可选依赖
pip install -e ".[tui,api,dev]"
```

依赖：Python ≥ 3.11，pydantic ≥ 2.0，litellm ≥ 1.0，instructor ≥ 1.0，diskcache ≥ 5.0，jinja2 ≥ 3.0。

## 快速开始

### 1. 配置 API

**方式一：环境变量**

```bash
export NARRATIVE_BACKEND=openai          # openai 或 anthropic
export NARRATIVE_API_KEY=sk-xxxx
export NARRATIVE_API_BASE=https://api.deepseek.com
export NARRATIVE_MODEL=deepseek-v4-pro
```

**方式二：TUI 管理面板**

```bash
narrative-engine tui
# 进入 API 配置页 (按键 1)，填入信息后点"测试连接"
```

### 2. 命令行

```bash
narrative-engine dialogue --area "旧码头" --npc "鱼贩老李" --context "钓上旧靴子"
narrative-engine event --area "海边" --context "捡到漂流瓶"
narrative-engine describe --area "废弃灯塔"
narrative-engine shell   # 交互模式
narrative-engine tui     # TUI 管理面板
narrative-engine serve --story stories/seaside_town  # HTTP API
```

### 3. Python SDK

```python
from narrative_engine import NarrativeEngine, GameState, WorldState, NPCState

# 从故事目录一行启动
engine = NarrativeEngine.from_story("stories/seaside_town")

state = GameState(
    world=WorldState(area="old_dock", time="夜晚"),
    npcs={"fishmonger_li": NPCState(id="fishmonger_li", name="鱼贩老李")},
)

result = engine.tell(state, kind="dialogue", npc_id="fishmonger_li",
                     context="玩家把旧靴子拿给鱼贩看")
print(result.dialogue.text)
```

## TUI 管理面板

```
┌──────────────────────────────────────────┐
│  Narrative Engine TUI  v0.1.0            │
├──────────┬───────────────────────────────┤
│  API配置 │       内容区域                 │
│  故事管理 │     (Screen 切换)              │
│  NPC编辑 │                               │
│  交互测试 │                               │
│  记忆查看 │                               │
├──────────┴───────────────────────────────┤
│  Status: API Ready | Story: seaside_town │
└──────────────────────────────────────────┘
```

5 个功能页面，键盘 `1`-`5` 切换，`q` 退出：

| 页面 | 功能 |
|------|------|
| API 配置 | 选择 API 格式、填入 Key/Base URL/Model、测试连接、保存配置 |
| 故事管理 | 加载/新建故事、章节切换、NPC 热重载 |
| NPC 编辑 | NPC 列表、属性编辑、写入 npcs.yaml |
| 交互测试 | 参数化叙事生成、流式/非流式、对话历史 |
| 记忆查看 | 长期记忆/会话历史、清空/导出 |

## 故事目录结构

```
stories/<故事名>/
├── story.yaml          # 故事元信息 + 默认世界观 + 保底文案
├── npcs.yaml           # NPC 定义（性格、情绪、预设记忆）
└── chapters/
    ├── chapter_1.yaml  # 章节：标题、世界观覆盖、beats、保底文案
    └── chapter_2.yaml
```

### story.yaml

```yaml
title: 海边小镇

default_world:
  setting: 一个克苏鲁题材的海边小镇，诡异与日常并存。
  tone: eerie

default_fallback:
  dialogue:
    - "……"
    - "风吹过，没有人说话。"
  event:
    - "远处有什么东西动了一下，但你没看清。"
  description:
    - "海风带着咸味和淡淡的腥味。"
```

### npcs.yaml

```yaml
npcs:
  fishmonger_li:
    name: 鱼贩老李
    mood: grumpy
    traits:
      - 沉默寡言
      - 认识奶奶
      - 二十年老摊主
    preset_memories:
      - content: 二十年前欠奶奶一碗汤，至今记得那个味道
        importance: 8
```

### 章节文件 (chapters/chapter_1.yaml)

```yaml
title: 第一章 · 抵达

world:
  area: grandma_house
  time: 黄昏

beats:
  - id: prologue_arrival
    kind: description
    priority: 100
    trigger:
      world.area: grandma_house
    text: "你站在奶奶的老房子前。相机挂在脖子上……"
    mood: eerie
```

## StoryBeat 触发系统

锚点触发器是引擎区别于"纯 AI 生成"的关键——作者在特定条件下插入手写内容，确保关键剧情节点不走 AI。

### 触发条件类型

| 类型 | 语法 | 示例 |
|------|------|------|
| 精确匹配 | `field: value` | `world.area: grandma_house` |
| 比较运算符 | `field: "<=80"` | `player.attributes.san: "<=80"` |
| 正则 | `field: "/pattern/"` | `world.area: "/dock\|码头/"` |
| $or 组合 | `$or: [{...}, {...}]` | 任一子条件满足即触发 |
| $not 取反 | `$not: {...}` | 排除特定场景 |

### 虚拟字段

| 字段 | 说明 |
|------|------|
| `_history_count` | history 条数 |
| `_inventory_count` | 背包物品数量 |
| `_npc_id` | 当前交互 NPC 的 ID |

### 完整示例

```yaml
beats:
  - id: night_encounter
    kind: event
    priority: 60
    once: true
    trigger:
      $or:
        - world.area: "/dock|码头/"
          world.time: night
        - world.area: "/cemetery|墓地/"
          world.time: dusk
      player.attributes.san: "<=80"
    event_title: 暗处有东西在看你
    text: "水面下有什么巨大的轮廓缓缓滑过..."
    event_choices:
      - 举起相机
      - 慢慢后退
    unlocks:
      - deep_one_sighted
```

## 结构化输出

使用 instructor 强制 LLM 输出符合 Pydantic schema 的 JSON：

```python
class Dialogue(BaseModel):
    text: str           # 对话内容，≤200 字
    mood_change: int    # 情绪变化，-10 ~ 10
    unlock_hint: str    # 可选解锁线索

class Event(BaseModel):
    title: str          # 事件标题，≤60 字
    description: str    # 事件描述，≤500 字
    choices: list[str]  # 玩家可选行动
    consequences: dict  # 每个行动的后果描述

class Description(BaseModel):
    text: str           # 场景描述，≤200 字
    mood: str           # neutral / peaceful / eerie / tense / dread
```

## Prompt 策略

- **Temperature 动态调整** — 按叙事类型 (dialogue -0.05, event +0.1) 和 NPC 情绪 (angry +0.15, calm -0.1) 微调
- **NPC Persona 注入** — 对话 prompt 自动注入 NPC 性格、情绪、与玩家关系值
- **自适应重试** — LLM 调用失败后以 temperature×0.6 重试一次

## HTTP API

```bash
narrative-engine serve --story stories/seaside_town --port 8000
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/tell` | POST | 叙事生成（流式由 body 的 `stream: true` 切换） |
| `/story` | GET | 当前故事信息 |
| `/story/load` | POST | 加载/切换到指定故事目录 |
| `/story/chapters` | GET | 章节列表 |
| `/story/chapter/switch` | POST | 切换章节（body: `{"chapter": "<name>"}`） |
| `/story/npcs/reload` | POST | 热重载 NPC |

## 启动验证

改完代码、提 PR 前，跑一次 `run` skill 把三个表面都点一遍——`pytest` 通过不代表 import / 路由装配 / TUI mount 不会回归。

```bash
.claude/skills/run/driver.sh           # CLI + HTTP + TUI 全跑
.claude/skills/run/driver.sh cli       # 只验 CLI
.claude/skills/run/driver.sh http      # serve + /health + /story + /tell（beat-anchored，无需 LLM key）
.claude/skills/run/driver.sh tui       # textual headless smoke

PORT=19000 STORY=stories/seaside_town .claude/skills/run/driver.sh http
NO_TELL=1 .claude/skills/run/driver.sh http        # 跳过 /tell（用于非 seaside_town 故事）
```

退出码非零代表至少一个表面挂了，详见 `.claude/skills/run/SKILL.md`。

## 项目结构

```
narrative-engine/
├── config/
│   └── engine.yaml
├── src/narrative_engine/
│   ├── core/
│   │   ├── engine.py            # NarrativeEngine 主入口
│   │   ├── director.py          # AIDirector — LLM 调用封装
│   │   ├── beat_manager.py      # StoryBeat 触发求值器
│   │   ├── context.py           # ContextManager — prompt 构建
│   │   ├── cache.py             # CacheManager — diskcache 封装
│   │   ├── memory.py            # MemoryManager — 两层记忆管理
│   │   ├── story_loader.py      # StoryLoader — 故事目录解析
│   │   └── interpreter.py       # ConfigInterpreter — YAML 配置解释
│   ├── api/
│   │   ├── app.py               # FastAPI 应用工厂
│   │   ├── routes.py            # REST + SSE 流式路由
│   │   └── schemas.py           # 请求/响应模型
│   ├── tui/
│   │   ├── app.py               # NarrativeTUI — 主 App
│   │   ├── state.py             # TUI 全局状态
│   │   ├── config_store.py      # API key 存储（内存 + 文件）
│   │   ├── screens/             # 5 个功能页面
│   │   └── widgets/             # 流式输出等组件
│   ├── models/
│   │   ├── config.py            # EngineConfig, LLMBackend, ProviderKind
│   │   ├── state.py             # GameState, PlayerState, WorldState, NPCState
│   │   ├── memory.py            # MemoryRecord, SessionTurn
│   │   └── narrative.py         # StoryBeat, Dialogue, Event, Description
│   ├── filters/
│   │   └── keyword.py           # 关键词过滤
│   ├── prompts/
│   │   ├── dialogue.j2          # 对话 prompt 模板
│   │   ├── event.j2             # 事件 prompt 模板
│   │   └── description.j2       # 描述 prompt 模板
│   └── cli.py                   # 命令行入口
├── stories/
│   └── seaside_town/
│       ├── story.yaml
│       ├── npcs.yaml
│       └── chapters/
├── examples/
│   └── basic_usage.py
├── docs/                        # 详细文档
├── tests/
├── .claude/skills/run/          # 三表面启动验证 skill（CLI/HTTP/TUI smoke）
└── pyproject.toml
```

## 当前进度

### 已完成 (v0.1.0)

- [x] **四级叙事流水线**：StoryBeat 锚点 → 缓存 → LLM 生成 → fallback
- [x] **StoryBeat 触发系统**：精确匹配、比较运算符、正则、$or/$not、虚拟字段、优先级、once 语义
- [x] **多后端 LLM**：OpenAI 兼容 / Anthropic 兼容，litellm + instructor 结构化输出
- [x] **缓存层**：diskcache 持久化，相同参数命中
- [x] **关键词过滤**：可配置黑名单
- [x] **配置解释器**：YAML 自动解析 world / npcs / beats / fallback
- [x] **CLI 工具**：dialogue / event / describe / shell / serve / tui 六个子命令
- [x] **TUI 管理面板**：5 个功能页面（API 配置、故事管理、NPC 编辑、交互测试、记忆查看）
- [x] **Prompt 模板**：Jinja2 渲染，支持配置覆盖
- [x] **NPC 记忆系统**：两层记忆（session + memory），重要性淘汰、内容去重、JSON 持久化
- [x] **故事架构**：章节独立文件、NPC 独立配置、运行时切换章节、NPC 热重载、预设记忆
- [x] **HTTP API**：FastAPI REST（/tell /story/* /health）+ SSE 流式
- [x] **异步支持**：全链路 async/await，asyncio.to_thread 包装磁盘 I/O
- [x] **Prompt 策略**：Temperature 动态调整、NPC persona 注入、自适应重试
- [x] **完整测试**：133 个测试，覆盖引擎、触发器、AI 链路、记忆、流式、API、异步、prompt 策略
- [x] **示例故事**：seaside_town（克苏鲁题材，含 beats、NPC 预设记忆、保底文案）

### 待完成

- [ ] **详细文档**：完善 `docs/` 目录下的使用指南
- [ ] **更多故事模板**：提供不同题材的示例故事

## License

MIT
