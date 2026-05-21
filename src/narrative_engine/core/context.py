from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, select_autoescape

from narrative_engine.models.state import GameState

if TYPE_CHECKING:
    from narrative_engine.models.config import PromptTemplates
    from narrative_engine.models.state import NPCState


class ContextManager:
    def __init__(self, world_setting: str = "", templates: PromptTemplates | None = None) -> None:
        self._world_setting = world_setting
        self._templates = templates
        self._env = Environment(
            loader=PackageLoader("narrative_engine", "prompts"),
            autoescape=select_autoescape(),
        )

    def update_world_setting(self, world_setting: str) -> None:
        self._world_setting = world_setting

    def build(
        self, state: GameState, kind: str, context: str,
        session_context: str = "", memory_context: str = "",
        npc: NPCState | None = None,
    ) -> str:
        render_kwargs = {
            "world_setting": self._world_setting,
            "state": state,
            "state_json": state.model_dump_json(indent=2),
            "context": context,
            "session_context": session_context,
            "memory_context": memory_context,
            "npc": npc,
        }

        # 配置模板覆盖优先
        if self._templates:
            override = getattr(self._templates, kind, "")
            if override:
                template = self._env.from_string(override)
                return template.render(**render_kwargs)

        # 回退到内置 .j2 文件
        template_name = f"{kind}.j2"
        try:
            template = self._env.get_template(template_name)
        except Exception:
            template = self._env.from_string("{{ context }}\n\n{{ state_json }}")

        return template.render(**render_kwargs)
