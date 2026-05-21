from __future__ import annotations

import instructor
from litellm import completion

from narrative_engine.models.config import LLMBackend


class AIDirector:
    def __init__(self, backend: LLMBackend) -> None:
        self._backend = backend
        self._client = instructor.from_litellm(completion)

    @property
    def model_name(self) -> str:
        return self._backend.resolve_model()

    def generate(self, prompt: str, output_schema: type) -> tuple:
        """调用 LLM，instructor 自动处理：结构化输出、schema 校验、失败重试。

        Returns:
            (pydantic_model, raw_text, tokens_used)
        """
        kwargs: dict = dict(
            model=self._backend.resolve_model(),
            messages=[
                {"role": "system", "content": "You are a narrative engine. Output exactly the requested JSON structure."},
                {"role": "user", "content": prompt},
            ],
            temperature=self._backend.temperature,
            max_tokens=self._backend.max_tokens,
            timeout=self._backend.timeout,
            max_retries=2,
        )
        if self._backend.api_key:
            kwargs["api_key"] = self._backend.api_key
        if self._backend.api_base:
            kwargs["api_base"] = self._backend.api_base

        result, raw = self._client.create_with_completion(
            response_model=output_schema,
            **kwargs,
        )
        tokens = raw.usage.total_tokens if raw and raw.usage else 0
        raw_text = raw.choices[0].message.content if raw and raw.choices else ""
        return result, raw_text, tokens

    def generate_stream(self, prompt: str, output_schema: type):
        """流式生成，yield 部分 Pydantic 模型。"""
        kwargs: dict = dict(
            model=self._backend.resolve_model(),
            messages=[
                {"role": "system", "content": "You are a narrative engine. Output exactly the requested JSON structure."},
                {"role": "user", "content": prompt},
            ],
            temperature=self._backend.temperature,
            max_tokens=self._backend.max_tokens,
            timeout=self._backend.timeout,
            max_retries=2,
        )
        if self._backend.api_key:
            kwargs["api_key"] = self._backend.api_key
        if self._backend.api_base:
            kwargs["api_base"] = self._backend.api_base

        return self._client.create_partial(response_model=output_schema, **kwargs)
