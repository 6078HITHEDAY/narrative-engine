from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_file)


def get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


NARRATIVE_BACKEND = get("NARRATIVE_BACKEND", "deepseek")
NARRATIVE_MODEL = get("NARRATIVE_MODEL", "")
NARRATIVE_API_KEY = get("NARRATIVE_API_KEY", "")
NARRATIVE_API_BASE = get("NARRATIVE_API_BASE", "")
NARRATIVE_TEMPERATURE = float(get("NARRATIVE_TEMPERATURE", "0.8"))
NARRATIVE_MAX_TOKENS = int(get("NARRATIVE_MAX_TOKENS", "256"))
NARRATIVE_TIMEOUT = float(get("NARRATIVE_TIMEOUT", "10.0"))
NARRATIVE_CACHE_DIR = get("NARRATIVE_CACHE_DIR", ".cache/narrative_engine")
