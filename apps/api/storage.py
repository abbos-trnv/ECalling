import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4


class Storage(Protocol):
    def path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise ValueError("Invalid storage key")
        return candidate

    def temporary(self) -> Path:
        target = self.path(f".incoming/{uuid4().hex}.tmp")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def publish(self, temporary: Path, key: str) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)
