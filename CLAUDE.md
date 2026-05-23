# CLAUDE.md

给 Claude Code（或任何 AI 协作工具）的项目级约定。

## 项目定位

通用 AI 互动叙事引擎。**底层中间件**：输入结构化 GameState，输出结构化叙事内容（dialogue/event/description），通过 `apply_choice()` 把玩家选择反馈进 state，构成完整互动闭环。

不绑定任何具体题材——`stories/seaside_town/` 只是参考实现，作者按目录约定（`story.yaml` / `npcs.yaml` / `chapters/*.yaml`）写自己的故事即可，不改 `src/` 任何代码。改引擎代码时要保持这条边界，不要把 seaside_town 的题材假设硬编码进去（克苏鲁、相机、照片数等都属于游戏侧概念，不该出现在引擎或 prompt 模板里）。

## 关键命令

```bash
# 装环境（含 API + TUI + dev extras）
pip install -e ".[api,tui,dev]"
# 或 uv sync

# 跑全部测试（默认跳过 integration 标记）
pytest

# 跑真实 LLM 集成测试（需要 NARRATIVE_API_KEY）
pytest -m integration

# 三表面启动验证（CLI/HTTP/TUI smoke）
.claude/skills/run/driver.sh           # 全跑
.claude/skills/run/driver.sh cli       # 只验单个表面
.claude/skills/run/driver.sh http
.claude/skills/run/driver.sh tui
```

## 验证策略

- **改逻辑** → `pytest` + 视情况手动跑 examples/ 里相关 demo
- **改 routes / cli / tui / 装配代码** → 必跑 `.claude/skills/run/driver.sh`，因为 import / 路由装配 / TUI mount 这类回归 pytest 接不住
- **改 prompt 模板或 LLM 链路** → `pytest -m integration` 配真实 API key 验一次

## 代码约定

- Python ≥ 3.11，全链路 `from __future__ import annotations`
- 全链路 async/await，磁盘 I/O 用 `asyncio.to_thread` 包装
- LLM 调用走 litellm + instructor，强制 Pydantic schema 结构化输出
- 公开 API 写中文 docstring，简短说明 why 而不是 what
- 测试默认 mock LLM；真实 LLM 测试放 `tests/integration/`，加 `pytestmark = [pytest.mark.integration, skipif(no key)]`
- 故事内容（题材、NPC、beat 文案）只在 `stories/*/` 里维护，不进 `src/`

## 提交规范

参考 `git log` 风格：中文标题 + 空行 + 中文正文，正文说清"为什么"。一次 commit 聚焦一个主题，跨多个独立改动时拆开。

提交时优先用具名文件 `git add path/to/file`，避免 `git add -A` 误带未跟踪垃圾。

## 隐私 / 安全

- API key 永远走 `NARRATIVE_API_KEY` 环境变量或 TUI 持久化的 `~/.narrative_engine/config.json`（仓库外），不进代码
- `.env` / `.cache/` / `stories/*/.state/` 都已在 `.gitignore` 里，不要 force-add
- 提交前确认 `git status` 干净，没有偶然带入的本地缓存或 IDE 文件

## 目录速查

```
src/narrative_engine/
├── core/         # 引擎核心：engine / director / beat_manager / cache / memory / story_loader / interpreter
├── api/          # FastAPI app + routes + schemas
├── tui/          # Textual 管理面板（5 个 screen）
├── models/       # Pydantic 数据模型（state / config / narrative / memory / generated）
├── generators/   # AI 总编剧（一句灵感 → 完整故事目录）
├── prompts/      # Jinja2 prompt 模板
├── filters/      # 关键词黑名单
└── cli.py        # 命令行入口

stories/<故事名>/
├── story.yaml      # 故事元信息 + default_world + default_fallback
├── npcs.yaml       # NPC 定义（性格、情绪、preset_memories）
└── chapters/*.yaml # 章节级 world 覆盖 + beats

.claude/skills/run/  # CLI/HTTP/TUI 三表面 smoke driver（详见 SKILL.md）
docs/                # guide.md（完整指南）+ storybeat-syntax.md（触发器语法）
examples/            # 五个 demo：basic / interactive / streaming / http_client / generate_story
tests/integration/   # 真实 LLM 测试，pytest -m integration 触发
```

## 常见误区

- **不要给 BeatManager 加题材特定的 `_虚拟字段`**（如曾经存在的 `_photos_count`，已删）。游戏特定计数走 `player.attributes.<key>`。
- **不要在 prompt 模板里写"克苏鲁"/"现代科技词汇"等题材关键词**——这些应该由 `story.yaml` 的 `default_world.tone` / `setting` 注入。
- **`apply_choice()` 只记 recent_actions 和 history**，物品消耗 / 属性变化 / 解锁标志由游戏层根据 `event.consequences` 自行处理，引擎不越界。
