from __future__ import annotations

import instructor
from litellm import completion, acompletion

from narrative_engine.models.config import LLMBackend


class AIDirector:
    def __init__(self, backend: LLMBackend) -> None:
        self._backend = backend
        self._client = instructor.from_litellm(completion)
        self._async_client = instructor.from_litellm(acompletion)

    @property
    def model_name(self) -> str:
        return self._backend.resolve_model()

    def _resolve_temperature(self, kind: str = "", npc_mood: str = "") -> float:
        return self._backend.temperature_profile.resolve(
            self._backend.temperature, kind=kind, npc_mood=npc_mood,
        )

    def _build_kwargs(self, prompt: str, kind: str = "", npc_mood: str = "", temperature: float | None = None) -> dict:
        if temperature is None:
            temperature = self._resolve_temperature(kind, npc_mood)
        kwargs: dict = dict(
            model=self._backend.resolve_model(),
            messages=[
                {"role": "system", "content": "You are a narrative engine. Output exactly the requested JSON structure."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=self._backend.max_tokens,
            timeout=self._backend.timeout,
            max_retries=2,
        )
        if self._backend.api_key:
            kwargs["api_key"] = self._backend.api_key
        if self._backend.api_base:
            kwargs["api_base"] = self._backend.api_base
        return kwargs

    def generate(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = "") -> tuple:
        """调用 LLM，自适应重试：第一次用实际 temperature，失败后用更低 temperature。"""
        base_temp = self._resolve_temperature(kind, npc_mood)
        temps = [base_temp, base_temp * 0.6]
        last_error = None

        for t in temps:
            try:
                kwargs = self._build_kwargs(prompt, temperature=t)
                result, raw = self._client.create_with_completion(
                    response_model=output_schema,
                    **kwargs,
                )
                tokens = raw.usage.total_tokens if raw and raw.usage else 0
                raw_text = raw.choices[0].message.content if raw and raw.choices else ""
                return result, raw_text, tokens
            except Exception as e:
                last_error = e

        raise last_error  # type: ignore[misc]

    def generate_stream(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = ""):
        """流式生成，yield 部分 Pydantic 模型。"""
        kwargs = self._build_kwargs(prompt, kind=kind, npc_mood=npc_mood)
        return self._client.create_partial(response_model=output_schema, **kwargs)

    async def generate_async(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = "") -> tuple:
        """异步调用 LLM，自适应重试。"""
        base_temp = self._resolve_temperature(kind, npc_mood)
        temps = [base_temp, base_temp * 0.6]
        last_error = None

        for t in temps:
            try:
                kwargs = self._build_kwargs(prompt, temperature=t)
                result, raw = await self._async_client.create_with_completion(
                    response_model=output_schema,
                    **kwargs,
                )
                tokens = raw.usage.total_tokens if raw and raw.usage else 0
                raw_text = raw.choices[0].message.content if raw and raw.choices else ""
                return result, raw_text, tokens
            except Exception as e:
                last_error = e

        raise last_error  # type: ignore[misc]

    async def generate_stream_async(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = ""):
        """异步流式生成。"""
        kwargs = self._build_kwargs(prompt, kind=kind, npc_mood=npc_mood)
        async for partial in self._async_client.create_partial(
            response_model=output_schema,
            **kwargs,
        ):
            yield partial
