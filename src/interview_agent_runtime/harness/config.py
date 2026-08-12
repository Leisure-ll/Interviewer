from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class HarnessConfig:
    mode: str = "mock"
    skills_dir: Optional[Path] = None
    checkpoint_dir: Optional[Path] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None

    @classmethod
    def mock(cls) -> "HarnessConfig":
        return cls(mode="mock")

    @classmethod
    def development(cls, checkpoint_dir: Optional[Path] = None) -> "HarnessConfig":
        return cls(mode="development", checkpoint_dir=checkpoint_dir)

    @classmethod
    def production(cls, skills_dir: Path, checkpoint_dir: Path) -> "HarnessConfig":
        return cls(mode="production", skills_dir=skills_dir, checkpoint_dir=checkpoint_dir)
