"""API 配置存储：内存 + 本地文件双模式。"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".narrative_engine" / "config.json"


def save_to_file(config: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in config.items() if k != "api_key"}
    CONFIG_FILE.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")


def load_from_file() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
