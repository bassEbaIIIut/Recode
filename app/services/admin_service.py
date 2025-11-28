import json
from pathlib import Path


class AdminPasswordService:
    def __init__(self, path: Path):
        self.path = path
        self._passwords: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        try:
            with self.path.open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            data = {}
        passwords: dict[str, int] = {}
        if isinstance(data, dict):
            for password, level in data.items():
                try:
                    lvl = int(level)
                except Exception:
                    continue
                if lvl in (1, 2, 3):
                    passwords[str(password)] = lvl
        self._passwords = passwords

    def reload(self) -> None:
        self._load()

    def get_level_for_password(self, password: str) -> int | None:
        if not password:
            return None
        return self._passwords.get(password)
