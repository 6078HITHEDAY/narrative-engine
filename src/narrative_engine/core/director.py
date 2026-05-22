from __future__ import annotations

import logging

import instructor
from instructor import Mode
from litellm import completion, acompletion

from narrative_engine.models.config import LLMBackend

logger = logging.getLogger(__name__)


class DirectorError(Exception):
    """LLM 调用错误，携带调试信息。"""

    def __init__(self, message: str, model: str = "", provider: str = "",
                 status_code: int = 0) -> None:
        super().__init__(message)
        self.model = model
        self.provider = provider
        self.status_code = status_code


_TOOLS_UNSUPPORTED_PATTERNS = (
    "tool_choice",
    "tool calling",
    "tool call",
    "function call",
    "does not support tools",
    "thinking mode does not support",
)


class AIDirector:
    def __init__(self, backend: LLMBackend) -> None:
        self._backend = backend
        if backend.structured_output_mode == "json":
            self._mode = Mode.JSON
            self._mode_probed = True
        elif backend.structured_output_mode == "tools":
            self._mode = Mode.TOOLS
            self._mode_probed = True
        else:
            self._mode = Mode.TOOLS
            self._mode_probed = False
        self._client = instructor.from_litellm(completion, mode=self._mode)
        self._async_client = instructor.from_litellm(acompletion, mode=self._mode)

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
        max_tokens = self._backend.reasoning_max_tokens if self._backend.reasoning_model else self._backend.max_tokens
        kwargs: dict = dict(
            model=self._backend.resolve_model(),
            messages=[
                {"role": "system", "content": "You are a narrative engine. Output exactly the requested JSON structure."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self._backend.timeout,
        )
        if self._backend.api_key:
            kwargs["api_key"] = self._backend.api_key
        if self._backend.api_base:
            kwargs["api_base"] = self._backend.api_base
        return kwargs

    def _is_tools_unsupported_error(self, error: Exception) -> bool:
        haystack = (str(error) + " " + getattr(error, "message", "")).lower()
        return any(p in haystack for p in _TOOLS_UNSUPPORTED_PATTERNS)

    def _probe_mode(self, error: Exception) -> bool:
        if self._mode_probed:
            return False
        if self._is_tools_unsupported_error(error):
            self._mode = Mode.JSON
            self._client = instructor.from_litellm(completion, mode=Mode.JSON)
            self._async_client = instructor.from_litellm(acompletion, mode=Mode.JSON)
            self._mode_probed = True
            logger.info("Mode downgraded from TOOLS to JSON due to provider rejection")
            return True
        return False

    def _log_attempt_failure(self, t: float, e: Exception, async_label: str = "") -> None:
        level = logging.DEBUG if (not self._mode_probed and self._is_tools_unsupported_error(e)) else logging.WARNING
        logger.log(level, "AI generate%s attempt failed (temp=%.2f): %s", async_label, t, e)

    def _wrap_error(self, e: Exception) -> DirectorError:
        msg = str(e)
        return DirectorError(
            message=msg,
            model=self._backend.resolve_model(),
            provider=self._backend.provider.value,
            status_code=getattr(e, "status_code", 0),
        )

    def generate(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = "") -> tuple:
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
                self._mode_probed = True
                tokens = raw.usage.total_tokens if raw and raw.usage else 0
                raw_text = raw.choices[0].message.content if raw and raw.choices else ""
                return result, raw_text, tokens
            except Exception as e:
                self._log_attempt_failure(t, e)
                if self._probe_mode(e):
                    try:
                        kwargs = self._build_kwargs(prompt, temperature=t)
                        result, raw = self._client.create_with_completion(
                            response_model=output_schema,
                            **kwargs,
                        )
                        tokens = raw.usage.total_tokens if raw and raw.usage else 0
                        raw_text = raw.choices[0].message.content if raw and raw.choices else ""
                        return result, raw_text, tokens
                    except Exception as e2:
                        last_error = e2
                        continue
                last_error = e

        logger.error("All retries exhausted: %s", last_error)
        raise self._wrap_error(last_error)  # type: ignore[arg-type]

    def generate_stream(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = ""):
        kwargs = self._build_kwargs(prompt, kind=kind, npc_mood=npc_mood)
        started = False
        try:
            for partial in self._client.create_partial(response_model=output_schema, **kwargs):
                started = True
                yield partial
        except Exception as e:
            if not started and self._probe_mode(e):
                yield from self._client.create_partial(response_model=output_schema, **kwargs)
            else:
                raise self._wrap_error(e)

    async def generate_async(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = "") -> tuple:
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
                self._mode_probed = True
                tokens = raw.usage.total_tokens if raw and raw.usage else 0
                raw_text = raw.choices[0].message.content if raw and raw.choices else ""
                return result, raw_text, tokens
            except Exception as e:
                self._log_attempt_failure(t, e, async_label=" async")
                if self._probe_mode(e):
                    try:
                        kwargs = self._build_kwargs(prompt, temperature=t)
                        result, raw = await self._async_client.create_with_completion(
                            response_model=output_schema,
                            **kwargs,
                        )
                        tokens = raw.usage.total_tokens if raw and raw.usage else 0
                        raw_text = raw.choices[0].message.content if raw and raw.choices else ""
                        return result, raw_text, tokens
                    except Exception as e2:
                        last_error = e2
                        continue
                last_error = e

        logger.error("All async retries exhausted: %s", last_error)
        raise self._wrap_error(last_error)  # type: ignore[arg-type]

    async def generate_stream_async(self, prompt: str, output_schema: type, kind: str = "", npc_mood: str = ""):
        kwargs = self._build_kwargs(prompt, kind=kind, npc_mood=npc_mood)
        started = False
        try:
            async for partial in self._async_client.create_partial(
                response_model=output_schema,
                **kwargs,
            ):
                started = True
                yield partial
        except Exception as e:
            if not started and self._probe_mode(e):
                async for partial in self._async_client.create_partial(
                    response_model=output_schema,
                    **kwargs,
                ):
                    yield partial
            else:
                raise self._wrap_error(e)
