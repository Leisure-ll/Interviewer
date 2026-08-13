from __future__ import annotations

from typing import Any


class TraceSanitizer:
    """Keeps trace metadata useful without storing sensitive interview content."""

    blocked_keys = {
        "answer",
        "answer_text",
        "content",
        "messages",
        "prompt",
        "raw_resume",
        "resume",
        "tool_result",
        "transcript",
    }

    def sanitize(self, metadata: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            lowered = key.lower()
            if lowered in self.blocked_keys or lowered.endswith("_text"):
                clean[f"{key}_length"] = len(str(value))
                continue
            clean[key] = self._safe_value(value)
        return clean

    def _safe_value(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, tuple, set)):
            return [self._safe_value(item) for item in list(value)[:20]]
        if isinstance(value, dict):
            return self.sanitize(value)
        return str(value)
