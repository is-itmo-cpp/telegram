import json
import logging
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel


logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class Storage:
    def __init__(self, storage_dir: Path):
        self._dir = storage_dir
        self._cache: dict[str, BaseModel] = {}

    def get(self, name: str, model_cls: type[T]) -> T:
        if name not in self._cache:
            self._cache[name] = self._load(name, model_cls)
        cached = self._cache[name]
        if not isinstance(cached, model_cls):
            raise TypeError(f"Cached state '{name}' is {type(cached).__name__}, but {model_cls.__name__} was requested")
        return cached

    def save(self, name: str) -> None:
        if name not in self._cache:
            return
        state = self._cache[name]
        self._dir.mkdir(parents=True, exist_ok=True)
        file_path = self._dir / f"{name}.json"
        tmp_file = file_path.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            f.write(state.model_dump_json(indent=2))
        tmp_file.replace(file_path)

    def save_all(self) -> None:
        for name in self._cache:
            self.save(name)

    def _load(self, name: str, model_cls: type[T]) -> T:
        file_path = self._dir / f"{name}.json"
        if not file_path.exists():
            return model_cls()
        try:
            with open(file_path) as f:
                return model_cls.model_validate_json(f.read())
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load state from %s, using defaults", file_path)
            return model_cls()
