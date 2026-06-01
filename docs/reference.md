# Narrative Engine API 与配置参考

进阶主题参考文档。新手路径见 [guide.md](guide.md)。

## 目录

1. [Python SDK 进阶](#python-sdk-进阶)
2. [互动剧情深度](#互动剧情深度)
3. [傻瓜模式 SDK](#傻瓜模式-sdk)
4. [AI 总编剧 SDK](#ai-总编剧-sdk)
5. [HTTP API 详细](#http-api-详细)
6. [启动验证详情](#启动验证详情)
7. [记忆系统](#记忆系统)
8. [Prompt 策略](#prompt-策略)
9. [环境变量完整参考](#环境变量完整参考)
10. [高级配置](#高级配置)

---

## Python SDK 进阶

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

流式模式下，锚点命中直接 yield 完整 `NarrativeOutput` 对象（只 yield 一次），不命中则逐步 yield instructor `partial` 对象。

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

`switch_chapter()` 会替换 `BeatManager` 的 beats、覆盖 `world_setting` 和 `fallback_pool`。`reload_npcs()` 从 `npcs.yaml` 重新读取 NPC 定义。

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

### 编程式构造 EngineConfig

```python
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

---

## 互动剧情深度

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

`PromptTemplates` 的三个字段对应三种 `kind`，留空就回退到内置 `.j2`。变量集与内置一致：`world_setting / state / state_json / context / session_context / memory_context / npc`。

### `apply_choice()` 方法签名

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

---

## 傻瓜模式 SDK

### AutoNarrator 编程接口

```python
from narrative_engine import NarrativeEngine
from narrative_engine.core.auto_narrator import AutoNarrator
from narrative_engine.models.state import GameState, PlayerState, WorldState

engine = NarrativeEngine.from_story("stories/seaside_town")
engine.reset_beats()

state = GameState(
    player=PlayerState(name="悠悠", inventory=["相机"]),
    world=WorldState(area="grandma_house", time="早晨"),
)
narrator = AutoNarrator(engine, state)

# 单轮
intent, result = await narrator.respond("跟鱼贩老李聊聊")
print(intent.kind)          # "dialogue"
print(intent.npc_id)        # "fishmonger_li"
print(result.dialogue.text) # 生成的对话文本

# 检查是否有待处理的 event 选项
if narrator.pending_event:
    for i, c in enumerate(narrator.pending_event.choices, 1):
        print(f"{i}. {c}")
    narrator.reset_pending()  # 手动清除待处理项
```

### AutoIntent 字段

`AutoNarrator.respond()` 返回 `(AutoIntent, NarrativeOutput)` 元组：

| AutoIntent 字段 | 类型 | 说明 |
|------|------|------|
| `kind` | `"dialogue" \| "event" \| "description"` | 意图路由判定的叙事类型 |
| `npc_id` | `str` | 匹配到的 NPC ID，无则为空 |
| `new_area` | `str` | 用户想去的区域，无则为空（不切换） |
| `choice_index` | `int` | 用户选中的选项序号（0-based），-1 表示未选 |
| `rewritten_context` | `str` | 改写后的上下文，传给 `tell()` 的 `context` 参数 |
| `reasoning` | `str` | LLM 路由决策的理由（调试用） |

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `narrator.state` | `GameState` | 当前 GameState（可随时修改 player/world） |
| `narrator.pending_event` | `Event \| None` | 上一轮生成的待处理 event（带 choices），`None` 表示没有待选项 |

### 交互循环模板

```python
import asyncio
from narrative_engine import NarrativeEngine
from narrative_engine.core.auto_narrator import AutoNarrator

engine = NarrativeEngine.from_story("stories/seaside_town")
engine.reset_beats()
narrator = AutoNarrator(engine)

async def loop():
    while True:
        line = input("> ").strip()
        if line.lower() in ("quit", "exit", "q"):
            return
        intent, result = await narrator.respond(line)
        if result.dialogue:
            print(f"[{intent.npc_id}] {result.dialogue.text}")
        elif result.event:
            print(f"事件: {result.event.title}")
            for i, c in enumerate(result.event.choices, 1):
                print(f"  {i}. {c}")
        elif result.description:
            print(result.description.text)

asyncio.run(loop())
```

完整示例见 `examples/auto_demo.py`。

### 路由容错

路由失败的极端情况（如 LLM 不可用）`narrator.respond()` 会抛出异常，调用方应 catch 并做降级处理。CLI play 命令已内置错误捕获，打印错误信息后继续等待下一轮输入。

---

## AI 总编剧 SDK

### StoryGenerator 编程接口

```python
from narrative_engine.generators import StoryGenerator

gen = StoryGenerator()

# 同步生成
path = gen.generate(
    idea="一个退休的星际快递员在边境星球开了间茶馆，某天收到一份不该出现的包裹",
    out_dir="stories/star_tea",
    num_npcs=4,
    num_beats=6,
    overwrite=False,  # 目录已存在时抛 FileExistsError
)

# 异步生成
path = await gen.generate_async(
    idea="古代书院里，一本禁书在学生间秘密流传",
    out_dir="stories/academy_secret",
)

print(f"故事已生成: {path}")
# 直接加载
engine = NarrativeEngine.from_story(str(path))
```

### 方法签名

```python
def generate(
    self,
    idea: str,
    out_dir: str | Path,
    *,
    num_npcs: int = 3,
    num_beats: int = 5,
    overwrite: bool = False,
) -> Path
```

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `idea` | `str` | 故事灵感（自然语言） | (必填) |
| `out_dir` | `str \| Path` | 输出目录 | (必填) |
| `num_npcs` | `int` | 生成 NPC 数量 | `3` |
| `num_beats` | `int` | 每章生成 StoryBeat 数量 | `5` |
| `overwrite` | `bool` | 强制覆盖已存在的目录 | `False` |

### 显式 LLMBackend

`StoryGenerator` 构造时自动从环境变量读取 API 配置。也可显式传入 `LLMBackend`：

```python
from narrative_engine.models.config import LLMBackend, ProviderKind

backend = LLMBackend(
    provider=ProviderKind.openai,
    api_key="sk-xxxx",
    model="deepseek-v4-pro",
)
gen = StoryGenerator(backend)
```

生成质量取决于模型能力——推荐用参数较大的模型（如 `deepseek-v4-pro`、`claude-sonnet-4-6`），并通过 `NARRATIVE_GENERATOR_MAX_TOKENS` 环境变量控制输出长度（默认 8192）。

完整示例见 `examples/generate_story.py`。

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

---

## HTTP API 详细

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

`state` 中所有字段均可选——最少只需 `{"world": {"area": "..."}}`。

### 流式响应 (SSE)

把请求体里的 `stream` 设成 `true`：

```bash
curl -N -X POST http://localhost:8000/tell \
  -H "Content-Type: application/json" \
  -d '{"state":{"world":{"area":"marketplace"}},"kind":"dialogue","context":"你好","stream":true}'
```

事件流格式：

- 中间帧：`data: {"partial": {"text": "..."}}\n\n`（instructor partial 的 model_dump）
- 锚点命中（一次性完整输出）：`data: {"kind":"description","description":{...},"backend":"storybeat",...}\n\n` + `data: [DONE]\n\n`
- 结束标记：`data: [DONE]\n\n`

### 完整端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查，返回 `{"status": "ok"}` |
| `/tell` | POST | 叙事生成（非流式 / 流式由 body 中 `stream: true` 切换） |
| `/story` | GET | 当前故事标题、章节、NPC 列表 |
| `/story/load` | POST | 加载/切换到指定 story_dir（body: `{"story_dir": "...", "chapter": "..."}`） |
| `/story/chapters` | GET | 所有章节列表 |
| `/story/chapter/switch` | POST | 切换到指定章节（body: `{"chapter": "<name>"}`） |
| `/story/npcs/reload` | POST | 从 npcs.yaml 热重载 NPC |

### 响应格式

`/tell` 非流式返回完整的 `NarrativeOutput` JSON：

```json
{
  "kind": "dialogue",
  "dialogue": {"text": "今天的鱼不新鲜。", "mood_change": 0, "unlock_hint": null},
  "event": null,
  "description": null,
  "tokens_used": 42,
  "cached": false,
  "degraded": false,
  "backend": "openai/deepseek-v4-pro",
  "raw": "...",
  "error": ""
}
```

`degraded: true` 表示触发降级（fallback）；`cached: true` 表示命中缓存。

---

## 启动验证详情

### Driver 环境变量

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

### 自动记录

引擎每次 `tell()` 返回后会调用 `_record_turn()`，自动：
1. 把本轮输出写入 session 上下文
2. 把生成内容作为 NPC 记忆持久化（importance 默认低）

降级文案（fallback）不写入记忆，避免污染后续 AI 调用。

---

## Prompt 策略

### Temperature 动态调整

`TemperatureProfile` 根据叙事类型和 NPC 情绪微调 temperature：

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

最终 temperature = `base_temp + kind_adj + mood_adj`，钳制在 `[0.1, 2.0]`。

可在 `LLMBackend` 中禁用：
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

LLM 调用失败后自动以 `temperature × 0.6` 重试一次，处理网络超时等临时性错误。两次均失败后抛 `DirectorError`，引擎层 catch 并返回 fallback。

### Structured Output 自动降级

除重试外，`AIDirector` 还会自动探测模型是否支持 Tool Calling。如果首次调用失败且错误信息匹配 `_TOOLS_UNSUPPORTED_PATTERNS`（如 "does not support tools"、"tool_choice" 等），自动从 `TOOLS` 降级到 `JSON` 模式并立即重试。

---

## 环境变量完整参考

引擎所有可配置环境变量一览：

### API 与模型

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NARRATIVE_BACKEND` | API 格式：`openai`（OpenAI 兼容）或 `anthropic` | `openai` |
| `NARRATIVE_API_KEY` | API 密钥 | (空) |
| `NARRATIVE_API_BASE` | API 端点 URL（如 `https://api.deepseek.com`） | (空) |
| `NARRATIVE_MODEL` | 模型名称（如 `deepseek-v4-pro`） | (空，使用默认) |

### Structured Output 与 Reasoning

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NARRATIVE_STRUCTURED_OUTPUT_MODE` | 结构化输出模式：`tools`（Tool Calling）或 `json`（JSON Mode）。留空自动探测——先用 TOOLS，失败后降级为 JSON | (空) |
| `NARRATIVE_REASONING_MODEL` | 设为 `1`/`true`/`yes` 启用 reasoning 模式（适用 DeepSeek 等支持思考链的模型） | (空) |
| `NARRATIVE_REASONING_MAX_TOKENS` | reasoning 模式最大 token 数，覆盖 `max_tokens` 配置 | (空) |

### 故事生成器

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NARRATIVE_GENERATOR_MAX_TOKENS` | StoryGenerator 调 LLM 时的 `max_tokens`，控制输出长度 | `8192` |

### LLMBackend 字段对照

以上所有环境变量对应 `LLMBackend` 构造参数：

```python
from narrative_engine.models.config import LLMBackend, ProviderKind

backend = LLMBackend(
    provider=ProviderKind.openai,       # NARRATIVE_BACKEND
    api_key="sk-xxxx",                  # NARRATIVE_API_KEY
    api_base="https://api.deepseek.com", # NARRATIVE_API_BASE
    model="deepseek-v4-pro",            # NARRATIVE_MODEL
    structured_output_mode="tools",     # NARRATIVE_STRUCTURED_OUTPUT_MODE
    reasoning_model=True,               # NARRATIVE_REASONING_MODEL
    reasoning_max_tokens=8192,          # NARRATIVE_REASONING_MAX_TOKENS
    max_tokens=4096,                    # NARRATIVE_GENERATOR_MAX_TOKENS
)
```

---

## 高级配置

### Structured Output 模式

引擎默认用 instructor 的 `TOOLS` 模式（Tool Calling）做结构化输出。如果所用模型不支持 Tool Calling（如部分 Ollama 本地模型），引擎会自动探测失败并降级为 `JSON` 模式。

手动指定模式：

```python
# 方式一：环境变量
export NARRATIVE_STRUCTURED_OUTPUT_MODE=json

# 方式二：LLMBackend
backend = LLMBackend(
    structured_output_mode="json",  # 或 "tools" 或 "auto"
)
```

`LLMBackend.structured_output_mode` 接受三个值：

| 值 | 行为 |
|------|------|
| `"auto"`（默认） | 先试 TOOLS，失败后自动降级 JSON |
| `"tools"` | 强制使用 TOOLS，失败即报错不降级 |
| `"json"` | 强制使用 JSON，跳过探测 |

两种模式的区别：

| 模式 | 原理 | 适用场景 |
|------|------|---------|
| `tools` (Tool Calling) | 声明 function schema，LLM 按 schema 填参 | 大部分商业 API（DeepSeek、Claude、GPT） |
| `json` (JSON Mode) | 在 prompt 中要求 LLM 输出 JSON，instructor 解析 | 不支持 Tool Calling 的模型（Ollama、部分国产模型） |

### Reasoning Model

DeepSeek V4 等模型支持"思考链"模式——模型在输出答案前先做推理。启用后引擎用 `reasoning_max_tokens` 覆盖 `max_tokens`，给推理留足空间。

```bash
export NARRATIVE_REASONING_MODEL=1
export NARRATIVE_REASONING_MAX_TOKENS=8192
```

或在代码中：

```python
backend = LLMBackend(
    reasoning_model=True,
    reasoning_max_tokens=8192,
)
```

### enable_logging()

`narrative_engine.enable_logging()` 配置全局日志（`logging.basicConfig`），方便排查 fallback 降级等问题：

```python
import narrative_engine
narrative_engine.enable_logging()

# 之后的所有引擎调用都会输出日志到 stderr
engine = NarrativeEngine.from_story("stories/seaside_town")
```

引擎在 import 时已自动压制 litellm 的冗余日志。`enable_logging()` 只需调用一次，适合开发调试；生产环境建议用自定义 logging 配置。

### 过滤器系统

`KeywordFilter` 对 LLM 输出做关键词审核，命中黑名单的词直接拦截并降级到保底文案。默认启用，黑名单包含常见 AI 暴露语（如"作为一个人工智能"、"as an AI language model"等），防止 LLM 自报身份破坏沉浸感：

```python
# 默认黑名单（EngineConfig.filter_blacklist 默认值）
["CPU", "GPU", "你好我是AI", "作为一个人工智能",
 "according to my training", "as an AI language model"]

# 自定义黑名单
config = EngineConfig(
    filter_enabled=True,
    filter_blacklist=["敏感词A", "敏感词B"],
)
engine = NarrativeEngine(config)

# 如果你的题材确实需要 AI/科技词汇，可以关掉或清空黑名单
config = EngineConfig(filter_enabled=False)
```

过滤发生在 LLM 输出之后、返回给调用方之前。被拦截的内容会打 WARNING 日志，不会写入缓存和记忆。

### 缓存系统

diskcache 持久化缓存，相同 `(state_json, context, kind, model)` 组合命中后零成本返回：

```python
config = EngineConfig(
    cache_enabled=True,             # 默认开启
    cache_dir=".cache/narrative",   # 缓存目录，默认 .cache/narrative_engine
)
```

```python
# 运行时操作
engine._cache.clear()     # 清空全部缓存
```

缓存 key 包含 model 名称，换模型后旧缓存不会命中（避免 A 模型缓存被 B 模型误用）。

### ConfigInterpreter（配置解释器）

除了 `stories/` 目录格式，引擎还支持 `config/` 目录格式——按文件名约定自动识别类型，合并为统一的 `RuntimeConfig`：

```
config/
├── engine.yaml     # LLMBackend 配置
├── world.yaml      # WorldConfig（世界观设定）
├── npcs.yaml       # NPC 列表
├── beats.yaml      # StoryBeat 列表
├── templates.yaml  # 自定义 PromptTemplates
└── fallback.yaml   # FallbackPool
```

```python
engine = NarrativeEngine.from_config_dir("config")
```

文件名对应解析规则：`world.yaml` → `RuntimeConfig.world`，`beats.yaml` → `RuntimeConfig.beats`，等等。也支持一个文件内含多个顶层 key（如 `story.yaml` 同时含 `world` + `beats` + `fallback`），`ConfigInterpreter._merge` 按顶层 key 自动分发。

### NarrativeOutput 完整字段

```python
class NarrativeOutput(BaseModel):
    kind: str                              # "dialogue" | "event" | "description"
    dialogue: Dialogue | None = None
    event: Event | None = None
    description: Description | None = None
    tokens_used: int = 0                   # LLM 调用消耗的 token 数（缓存/锚点命中为 0）
    cached: bool = False                   # 是否命中缓存
    degraded: bool = False                 # 是否降级到 fallback
    backend: str = ""                      # 实际来源："storybeat" | "openai/xxx" | "fallback"
    raw: str = ""                          # LLM 原始返回文本（调试用）
    error: str = ""                        # 降级时的错误信息
```
