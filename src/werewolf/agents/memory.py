import json
from pathlib import Path
from typing import Protocol

import yaml


class MemoryStore(Protocol):
    def load(self, seat: int) -> tuple[str, ...]: ...


class SimpleMemoryStore:
    """Optional per-seat text; it is player recollection, never game truth."""

    def __init__(self, root: Path | None = None):
        self.root = root

    def load(self, seat: int) -> tuple[str, ...]:
        if self.root is None:
            return ()
        for suffix in (".json", ".yaml", ".md"):
            path = self.root / f"{seat}{suffix}"
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if suffix == ".md":
                return tuple(line.lstrip("- ").strip() for line in text.splitlines() if line.strip())
            data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
            values = data.get("memories", [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError(f"Invalid memories in {path}")
            return tuple(values)
        return ()

