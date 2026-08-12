from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional, Protocol, Union

from interview_agent_runtime.blackboard import InterviewBlackboard


class CheckpointStore(Protocol):
    async def save(self, context: InterviewBlackboard) -> None:
        ...

    async def load(self, session_id: str) -> Optional[InterviewBlackboard]:
        ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._items: dict[str, InterviewBlackboard] = {}

    async def save(self, context: InterviewBlackboard) -> None:
        self._items[context.session_id] = context

    async def load(self, session_id: str) -> Optional[InterviewBlackboard]:
        return self._items.get(session_id)


class JsonFileCheckpointStore:
    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, context: InterviewBlackboard) -> None:
        path = self.root / f"{context.session_id}.json"
        path.write_text(json.dumps(_to_json(context), ensure_ascii=False, indent=2), encoding="utf-8")

    async def load(self, session_id: str) -> Optional[InterviewBlackboard]:
        return None


def _to_json(value: Any) -> Any:
    if is_dataclass(value):
        return _to_json(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

