# Examples — narrative-engine 完整功能示范

每个示例都基于 `stories/<dir>` 参数化，**不绑定任何具体故事**。

| 示例 | 涵盖能力 | 运行 |
|------|---------|------|
| [basic_usage.py](basic_usage.py) | 四级流水线（StoryBeat 锚点 / 缓存 / LLM / fallback）单回合调用 | `python examples/basic_usage.py` |
| [interactive_demo.py](interactive_demo.py) | 互动循环：look / talk / event / **choose** + apply_choice + inventory | `python examples/interactive_demo.py [story_dir]` |
| [generate_story.py](generate_story.py) | **AI 总编剧**：一段灵感生成完整 stories/<name>/ 立即可玩 | `python examples/generate_story.py "<灵感>"` |
| [streaming_demo.py](streaming_demo.py) | 流式生成（同步 + 异步） | `python examples/streaming_demo.py [story_dir]` |
| [http_client_demo.py](http_client_demo.py) | 用 httpx 调用 `narrative-engine serve` 暴露的 REST + SSE | `python examples/http_client_demo.py` |

## 准备

所有需要 LLM 调用的示例（除 basic_usage 中的锚点路径外）都通过环境变量配置后端：

```bash
export NARRATIVE_BACKEND=openai            # openai | anthropic
export NARRATIVE_API_KEY=sk-xxxx
export NARRATIVE_API_BASE=https://api.deepseek.com
export NARRATIVE_MODEL=deepseek-v4-pro
```

或 `cp .env.example .env` 后填入。

## 推荐顺序

1. **basic_usage.py** — 5 分钟看懂四级流水线
2. **interactive_demo.py** — 体验作为玩家的互动循环
3. **generate_story.py** — 见证"一句话生成完整故事"
4. **streaming_demo.py** + **http_client_demo.py** — 集成到自己项目时用得上
