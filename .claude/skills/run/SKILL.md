---
name: run
description: Launch and drive narrative-engine's CLI / HTTP / TUI surfaces to confirm a change actually works in the real app (not just tests). Use when asked to run, start, smoke-test, or verify the engine end-to-end.
---

# run — narrative-engine 三表面驱动

narrative-engine 暴露三个独立表面，**任何一个跑不起来都算回归**：

| 表面 | 入口 | 验证方式 |
|------|------|---------|
| CLI  | `narrative-engine` (`src/narrative_engine/cli.py`) | 无参运行 → stdout 含 `narrative-engine v` |
| HTTP | `narrative-engine serve` → FastAPI + uvicorn (`src/narrative_engine/api/`) | 轮询 `GET /health` → `{"status":"ok"}`，再 `GET /story` 拉一次故事元信息 |
| TUI  | `narrative-engine tui` → Textual 应用 (`src/narrative_engine/tui/app.py`) | 非 TTY 环境用 `App.run_test()` 跑一次事件循环，能 mount 五个 screen 即通过 |

## 触发条件

用户说"跑一下"/"起来"/"smoke test"/"verify the engine"/"看看 CLI/HTTP/TUI 能不能起"/"我改了 routes / cli / tui，确认下没炸"——都走这个 skill。**只跑 pytest 不算**：测试通过、应用起不来的回归就是这个 skill 要兜的兜底。

不要触发：用户问纯代码问题、只读探查、或者明确只要单元测试。

## 一键流程

```bash
.claude/skills/run/driver.sh           # 三个全跑
.claude/skills/run/driver.sh cli       # 只验 CLI
.claude/skills/run/driver.sh http      # 只验 HTTP
.claude/skills/run/driver.sh tui       # 只验 TUI（headless）

# 改端口 / 故事
PORT=19000 STORY=stories/seaside_town .claude/skills/run/driver.sh http
```

退出码非零代表至少一个表面挂了。脚本会自杀掉 HTTP 子进程并清理临时日志，不会留僵尸。

## 前置条件

- `.venv` 存在并已装好依赖（`pip install -e ".[api,tui,dev]"` 或 `uv sync`）。脚本不会替你 `pip install`，缺依赖直接报 exit 2。
- 默认故事路径 `stories/seaside_town`——repo 里附带了一份完整示例，开箱可用。改用别的故事时通过 `STORY=` 覆盖。
- `curl` 在 PATH 上（验 HTTP 用）。
- HTTP 默认绑 `127.0.0.1:18234`，端口已占就 `PORT=...` 换。

## 各表面要点

### CLI
单进程跑完即出。`narrative-engine` 无参时不调 LLM，所以无需 `NARRATIVE_API_KEY`。要真正跑 `dialogue/event/describe`，必须先配 `NARRATIVE_BACKEND` / `NARRATIVE_API_KEY` / `NARRATIVE_API_BASE` / `NARRATIVE_MODEL`（见 `.env.example`）——driver 不替你做这步。

### HTTP
启动会有 ~3-8s 的 litellm 冷启动 warning（远端 model_cost_map 拉取超时是已知现象，会自动 fallback 到本地，**不是错误**）。driver 依次跑：

1. 30 次 × 0.5s 轮询 `/health`，最多 15s
2. `GET /story` 拉故事元信息
3. `POST /tell` 用一份 beat-anchored payload（`world.area=grandma_house` + `world.chapter=第一章`）命中 `prologue_arrival` 锚点，端到端走完 request → state → beat resolver → response 全链路，**无需 LLM key**

`/tell` 失败判定：返回 `kind != description`（多半是 payload 编码挂了）或 `degraded=true`（锚点没命中且没 API key 可降级）→ exit 1 并打印排查提示。

**逃生口**：

```bash
NO_TELL=1            .claude/skills/run/driver.sh http   # 跳过 /tell（仅 /health + /story）
TELL_PAYLOAD_FILE=…  .claude/skills/run/driver.sh http   # 用自己的 JSON 文件，story 不是 seaside_town 时必备
```

payload 通过 heredoc 写到临时文件再 `curl -d @file`，避免 `env -i` 把 UTF-8 字面量打成 `?`。

### TUI
`App.run_test()` 只验 mount 期不抛异常——也就是 5 个 screen 的 `compose()` 都没事。**不能验交互行为**。要真用：开真 tty 跑 `narrative-engine tui`，按 `1`-`5` 切页，`q` 退。

## 自检清单（写完代码后 / PR 前）

- [ ] `driver.sh cli` 通过 → 起码 CLI 入口没 import 炸
- [ ] `driver.sh http` 通过 → routes/schemas/app factory 都能装配
- [ ] `driver.sh tui` 通过 → 五个 screen 全部能 mount
- [ ] 改了 `api/routes.py` 时，额外 `curl` 自己改的端点确认行为
- [ ] 改了 `tui/screens/*.py` 时，开真 tty 手动按一下，driver 只能挡 import 错

## 失败排查

| 症状 | 多半是 |
|------|--------|
| `.venv not found` | 还没装环境，先 `pip install -e ".[api,tui,dev]"` |
| `需要安装 API 依赖` | 装的是基础 extras，补 `[api]` |
| `/health` 15s 超时 | 端口被占 / 别的 uvicorn 没退干净 → `lsof -i:18234` |
| TUI smoke 抛 `ImportError: textual` | 缺 `[tui]` extras |
| TUI smoke 抛 `compose()` 异常 | 改坏了某个 screen，看 traceback 定位 `src/narrative_engine/tui/screens/*.py` |
