import json
from pathlib import Path


class GroupResolver:
    def __init__(self, groups_path: Path, aliases_path: Path):
        self._map = {}
        self._load_groups(groups_path)
        self._load_aliases(aliases_path)

    def _normalize(self, value: str) -> str:
        if value is None:
            return ""
        s = value.strip().upper()
        s = s.replace(" ", "")
        s = s.replace("–", "-")
        s = s.replace("—", "-")
        return s

    def _load_groups(self, path: Path) -> None:
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        if isinstance(data, dict):
            for canonical in data.keys():
                norm = self._normalize(canonical)
                if norm:
                    self._map[norm] = canonical

    def _load_aliases(self, path: Path) -> None:
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        if not isinstance(data, dict):
            return
        for canonical, aliases in data.items():
            canonical_norm = self._normalize(canonical)
            if canonical_norm:
                self._map[canonical_norm] = canonical
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_norm = self._normalize(alias)
                    if alias_norm:
                        self._map[alias_norm] = canonical

    def resolve(self, raw_value: str | None) -> str | None:
        norm = self._normalize(raw_value or "")
        if not norm:
            return None
        return self._map.get(norm)
