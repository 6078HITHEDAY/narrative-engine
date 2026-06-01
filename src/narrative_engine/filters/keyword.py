from __future__ import annotations

import re


class KeywordFilter:
    def __init__(self, blacklist: list[str] | None = None) -> None:
        self._blacklist = blacklist or []

    def validate(self, text: str) -> bool:
        """返回 True 表示文本通过过滤。"""
        if not self._blacklist:
            return True
        for word in self._blacklist:
            if re.search(re.escape(word), text, re.IGNORECASE):
                return False
        return True

    def sanitize(self, text: str) -> str:
        for word in self._blacklist:
            text = re.sub(re.escape(word), "", text, flags=re.IGNORECASE)
        return text.strip()
