# narrative-engine

通用 AI 驱动的叙事生成引擎。将游戏状态作为输入，产出符合世界观的对话、事件、场景描述——并支持手写剧情锚点覆盖 AI 输出，在可控性与生成自由度之间取平衡。

## 这是什么

narrative-engine 是一个**底层叙事中间件**。

> 接收结构化的游戏状态（玩家属性、世界参数、NPC 列表、历史记录），返回结构化的叙事内容（对话、事件、场景描述）。

其他项目可以作为 Python 库引入，通过配置自己的故事文件来驱动 AI 叙事。

## 核心设计

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

### 四级流水线

| 优先级 | 阶段 | 说明 |
|--------|------|------|
| 1 | **StoryBeat 锚点** | 手写内容，100% 可控。支持精确匹配、比较运算符、正则、$or/$not 组合条件 |
| 2 | **缓存** | 相同 state + context + kind + model 命中 diskcache，零成本返回 |
| 3 | **LLM 生成** | 通过 litellm + instructor 调用大模型，结构化输出自动 schema 校验 |
| 4 | **Fallback** | 所有路径失败时返回配置的保底文案池 |

### StoryBeat 触发系统

锚点触发器是引擎区别于"纯 AI 生成"的关键——作者可以在特定条件下插入手写内容，确保关键剧情节点不走 AI。

```yaml
beats:
  - id: night_encounter
    kind: event
    priority: 60
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
```

支持的触发条件：
- **精确匹配**：`world.area: grandma_house`
- **比较运算符**：`player.attributes.san: "<=80"`
- **正则**：`world.area: "/dock|码头/"`
- **$or 条件组**：任一子条件满足即触发
- **$not 取反**：排除特定场景
- **虚拟字段**：`_inventory_count`、`_photos_count`、`_npc_id` 等派生值

### 多后端支持

通过 litellm 统一接口，支持：
- **DeepSeek** — `deepseek/deepseek-chat`
- **OpenAI** — `openai/gpt-4o-mini`
- **Ollama** — `ollama/llama3:8b` 等本地模型
- 其他 litellm 支持的提供商均可扩展

### 结构化输出

使用 instructor 库强制 LLM 输出符合 Pydantic schema 的 JSON。三种叙事类型各有独立模型：

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

## 安装

```bash
pip install -e .
```

依赖：Python ≥ 3.11，pydantic ≥ 2.0，litellm ≥ 1.0，instructor ≥ 1.0，diskcache ≥ 5.0，jinja2 ≥ 3.0。

## 快速开始

### 1. 配置 API 密钥

```bash
cp .env.example .env
# 编辑 .env，填入 DeepSeek / OpenAI API 密钥
```

### 2. 命令行

```bash
narrative-engine dialogue --area "旧码头" --npc "鱼贩老李" --context "钓上旧靴子"
narrative-engine event --area "海边" --context "捡到漂流瓶"
narrative-engine describe --area "废弃灯塔" --context "玩家站在灯塔前"
narrative-engine shell   # 交互模式
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

## 项目结构

```
narrative-engine/
├── config/
│   └── engine.yaml              # 引擎全局配置（后端、缓存、过滤）
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
│   ├── models/
│   │   ├── config.py            # EngineConfig, LLMBackend, RuntimeConfig
│   │   ├── state.py             # GameState, PlayerState, WorldState, NPCState
│   │   ├── memory.py            # MemoryRecord, SessionTurn
│   │   └── narrative.py         # StoryBeat, Dialogue, Event, Description
│   ├── filters/
│   │   └── keyword.py           # 关键词过滤 / 禁用词黑名单
│   ├── prompts/
│   │   ├── dialogue.j2          # 对话 prompt 模板
│   │   ├── event.j2             # 事件 prompt 模板
│   │   └── description.j2       # 描述 prompt 模板
│   └── cli.py                   # 命令行入口
├── stories/
│   └── seaside_town/
│       ├── story.yaml           # 故事元信息
│       ├── npcs.yaml            # NPC 定义与预设记忆
│       └── chapters/
│           └── chapter_1.yaml   # 章节（含 beats、fallback）
├── examples/
│   └── basic_usage.py           # 完整使用示例
├── tests/
│   ├── test_engine.py           # 引擎集成测试
│   ├── test_beat_manager.py     # 触发器全覆盖测试
│   ├── test_ai_pipeline.py      # AI 链路 mock 测试
│   ├── test_memory.py           # 记忆系统测试
│   ├── test_story_loader.py     # 故事加载测试
│   ├── test_streaming.py        # 流式生成测试
│   └── test_api.py              # HTTP API 测试
└── pyproject.toml
```

## 当前进度

### 已完成 (v0.1.0)

- [x] **四级叙事流水线**：StoryBeat 锚点 → 缓存 → LLM 生成 → fallback，全部通路打通
- [x] **StoryBeat 触发系统**：精确匹配、比较运算符（>= <= > < ==）、正则、$or/$not 组合、虚拟字段、kind 过滤、优先级排序、once 语义
- [x] **多后端 LLM**：DeepSeek / OpenAI / Ollama，litellm 统一接口 + instructor 结构化输出
- [x] **缓存层**：diskcache 持久化，相同 state+context+kind+model 命中
- [x] **关键词过滤**：可配置黑名单，拦截 AI 模板话术
- [x] **配置解释器**：从单个 story.yaml 自动解析 world / npcs / beats / fallback
- [x] **CLI 工具**：dialogue / event / describe / shell / serve 五个子命令
- [x] **Prompt 模板**：Jinja2 渲染，支持配置覆盖
- [x] **保底文案池**：按 narrative kind 配置降级内容
- [x] **状态持久化**：已触发锚点可保存/恢复，支持跨会话
- [x] **NPC 记忆系统**：两层记忆（session 短期 + memory 长期），重要性淘汰、内容去重、JSON 持久化
- [x] **多轮对话上下文**：会话内对话历史自动注入 prompt，NPC 长期记忆跨会话保留
- [x] **故事架构**：章节独立文件、NPC 独立配置、运行时切换章节/故事、NPC 热重载、预设记忆
- [x] **HTTP API**：FastAPI REST 接口（/tell /story/* /health），供非 Python 项目调用
- [x] **流式输出**：SSE (Server-Sent Events) 协议，LLM token 级流式响应
- [x] **完整测试**：110 个测试，覆盖引擎、触发器、AI 链路、记忆系统、故事加载、流式生成、HTTP API
- [x] **示例故事**：seaside_town 包含 NPC 预设记忆、章节 beats、保底文案池

### 待完成

- [ ] **可视化编辑器**：StoryBeat 触发条件的 GUI 编辑工具
- [ ] **更多 prompt 策略**：temperature 动态调整、多采样投票
- [ ] **异步支持**：async/await 接口，支持并发调用

## License

MIT
