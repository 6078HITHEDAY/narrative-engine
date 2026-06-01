"""自然语言驱动的叙事包装器（傻瓜模式）。

调用方只喂自然语言，AutoNarrator 调一次 LLM 做意图路由：
判定 kind / 选 npc_id / 推 world.area / 响应 pending event 选项，
再调 engine.tell_async 出文。引擎核心不变。
"""

from __future__ import annotations

from typing import Literal

from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel

from narrative_engine.core.engine import NarrativeEngine
from narrative_engine.models.narrative import Event, NarrativeOutput
from narrative_engine.models.state import GameState


class AutoIntent(BaseModel):
    kind: Literal["dialogue", "event", "description"] = "description"
    npc_id: str = ""
    rewritten_context: str = ""
    new_area: str = ""
    choice_index: int = -1
    reasoning: str = ""


class AutoNarrator:
    def __init__(self, engine: NarrativeEngine, state: GameState | None = None) -> None:
        self._engine = engine
        self._state = state if state is not None else GameState()
        self._pending_event: Event | None = None
        self._env = Environment(
            loader=PackageLoader("narrative_engine", "prompts"),
            autoescape=select_autoescape(),
        )

    @property
    def state(self) -> GameState:
        return self._state

    @property
    def pending_event(self) -> Event | None:
        return self._pending_event

    def reset_pending(self) -> None:
        self._pending_event = None

    async def respond(self, user_input: str) -> tuple[AutoIntent, NarrativeOutput]:
        """单轮入口：自然语言 → (intent, NarrativeOutput)。"""
        intent = await self._route(user_input)

        # 1. 选项响应优先
        if (
            self._pending_event
            and intent.choice_index >= 0
            and intent.choice_index < len(self._pending_event.choices)
        ):
            choice = self._pending_event.choices[intent.choice_index]
            self._engine.apply_choice(self._state, self._pending_event, choice)
            self._pending_event = None
            result = await self._engine.tell_async(
                self._state,
                kind="description",
                context=f"刚做出选择「{choice}」之后",
            )
            return intent, result

        # 2. 场景切换
        if intent.new_area:
            self._state.world.area = intent.new_area

        # 3. 走主流程
        result = await self._engine.tell_async(
            self._state,
            kind=intent.kind,
            context=intent.rewritten_context or user_input,
            npc_id=intent.npc_id,
        )

        # 4. 新 event 覆盖 pending；否则保留旧的（玩家可以暂时忽略选项）
        if result.event and result.event.choices:
            self._pending_event = result.event

        return intent, result

    async def _route(self, user_input: str) -> AutoIntent:
        prompt = self._build_prompt(user_input)
        result, _, _ = await self._engine.director.generate_async(
            prompt, AutoIntent, kind="dialogue",
        )
        return result

    def _build_prompt(self, user_input: str) -> str:
        template = self._env.get_template("auto_route.j2")
        return template.render(
            world_setting=self._engine.config.world_setting,
            current_chapter=self._engine.current_chapter,
            state=self._state,
            npcs=list(self._engine.npcs.values()),
            pending_event=self._pending_event,
            user_input=user_input,
        )
