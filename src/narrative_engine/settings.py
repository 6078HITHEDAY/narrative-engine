from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_file)
