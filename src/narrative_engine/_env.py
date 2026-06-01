from __future__ import annotations

import logging
import os

from narrative_engine.models.config import LLMBackend, ProviderKind

logger = logging.getLogger(__name__)


def backend_from_env(
    *,
    max_tokens_env: str | None = None,
    default_max_tokens: int | None = None,
) -> LLMBackend | None:
    api_key = os.environ.get("NARRATIVE_API_KEY", "")
    if not api_key:
        return None

    backend_raw = os.environ.get("NARRATIVE_BACKEND", "openai")
    try:
        provider = ProviderKind(backend_raw)
    except ValueError:
        valid = ", ".join(p.value for p in ProviderKind)
        logger.warning(
            "Unknown NARRATIVE_BACKEND=%r, falling back to 'openai' (valid: %s)",
            backend_raw, valid,
        )
        provider = ProviderKind.openai

    kwargs: dict = {
        "provider": provider,
        "api_key": api_key,
        "api_base": os.environ.get("NARRATIVE_API_BASE", ""),
        "model": os.environ.get("NARRATIVE_MODEL", ""),
    }

    if max_tokens_env:
        max_tokens = os.environ.get(
            max_tokens_env,
            str(default_max_tokens) if default_max_tokens is not None else "",
        )
        if max_tokens:
            kwargs["max_tokens"] = int(max_tokens)

    mode = os.environ.get("NARRATIVE_STRUCTURED_OUTPUT_MODE", "")
    if mode:
        kwargs["structured_output_mode"] = mode
    reasoning = os.environ.get("NARRATIVE_REASONING_MODEL", "")
    if reasoning:
        kwargs["reasoning_model"] = reasoning.lower() in ("1", "true", "yes")
    reasoning_max = os.environ.get("NARRATIVE_REASONING_MAX_TOKENS", "")
    if reasoning_max:
        kwargs["reasoning_max_tokens"] = int(reasoning_max)

    return LLMBackend(**kwargs)
