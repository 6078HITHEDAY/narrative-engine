"""API 配置存储：内存 + 本地文件双模式。"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

CONFIG_FILE = Path.home() / ".narrative_engine" / "config.json"


def save_to_file(config: dict, include_key: bool = False) -> None:
    """写入配置到 ~/.narrative_engine/config.json。

    include_key=False（默认）时不写入 api_key，只保存 provider/api_base/model/temperature。
    include_key=True 时连同 api_key 一起写入；首次创建文件时 chmod 600 限制读权限。
    """
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(config)
    if not include_key:
        safe.pop("api_key", None)
    CONFIG_FILE.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def load_from_file() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
