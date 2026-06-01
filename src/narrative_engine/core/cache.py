from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from diskcache import Cache


class CacheManager:
    def __init__(self, cache_dir: str = ".cache/narrative_engine") -> None:
        self._cache = Cache(Path(cache_dir))

    @staticmethod
    def _make_key(state_hash: str, context: str, kind: str, model: str) -> str:
        raw = f"{state_hash}|{context}|{kind}|{model}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _state_hash(state_json: str) -> str:
        return hashlib.sha256(state_json.encode()).hexdigest()[:16]

    def get(
        self, state_json: str, context: str, kind: str, model: str
    ) -> dict | None:
        key = self._make_key(self._state_hash(state_json), context, kind, model)
        return self._cache.get(key)

    def set(
        self, state_json: str, context: str, kind: str, model: str, value: dict
    ) -> None:
        key = self._make_key(self._state_hash(state_json), context, kind, model)
        self._cache.set(key, value)

    def clear(self) -> None:
        self._cache.clear()

    async def aget(
        self, state_json: str, context: str, kind: str, model: str
    ) -> dict | None:
        key = self._make_key(self._state_hash(state_json), context, kind, model)
        try:
            return await asyncio.to_thread(self._cache.get, key)
        except Exception:
            return None

    async def aset(
        self, state_json: str, context: str, kind: str, model: str, value: dict
    ) -> None:
        key = self._make_key(self._state_hash(state_json), context, kind, model)
        try:
            await asyncio.to_thread(self._cache.set, key, value)
        except Exception:
            pass
