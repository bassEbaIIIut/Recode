import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    bot_token: str
    db_path: Path
    groups_path: Path
    group_aliases_path: Path
    url_path: Path
    passwords_path: Path
    times_path: Path
    models_path: Path
    homeworks_dir: Path
    freeimage_api_key: str | None
    telegraph_token: str | None


def load_config() -> AppConfig:
    base_dir = Path(__file__).resolve().parents[2]
    cfg_dir = base_dir / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "bot_config.json"
    with cfg_path.open(encoding="utf-8") as f:
        data = json.load(f)
    bot_token = data["bot_token"]
    freeimage_api_key = data.get("freeimage_api_key")
    telegraph_token = data.get("telegraph_token")
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    db_path = config_dir / "nmk_bot.db"
    groups_path = config_dir / "groups.json"
    group_aliases_path = config_dir / "group_aliases.json"
    url_path = config_dir / "url.json"
    for path in (groups_path, group_aliases_path, url_path):
        if not path.exists():
            with path.open("w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
    passwords_path = cfg_dir / "passwords.json"
    if not passwords_path.exists():
        with passwords_path.open("w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    categories_path = config_dir / "categories.json"
    if not categories_path.exists():
        with categories_path.open("w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    broadcast_blocklist_path = config_dir / "broadcast_blocklist.json"
    if not broadcast_blocklist_path.exists():
        with broadcast_blocklist_path.open("w", encoding="utf-8") as f:
            json.dump({"ids": [], "usernames": []}, f, ensure_ascii=False, indent=2)
    bot_log_path = config_dir / "bot.log"
    if not bot_log_path.exists():
        bot_log_path.touch()
    user_errors_log_path = config_dir / "user_errors.log"
    if not user_errors_log_path.exists():
        user_errors_log_path.touch()
    times_path = config_dir / "times.json"
    if not times_path.exists():
        with times_path.open("w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    models_path = cfg_dir / "models.json"
    if not models_path.exists():
        with models_path.open("w", encoding="utf-8") as f:
            json.dump({"models": [], "updated_at": None}, f, ensure_ascii=False, indent=2)
    homeworks_dir = config_dir / "homeworks"
    homeworks_dir.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        bot_token=bot_token,
        db_path=db_path,
        groups_path=groups_path,
        group_aliases_path=group_aliases_path,
        url_path=url_path,
        passwords_path=passwords_path,
        times_path=times_path,
        models_path=models_path,
        homeworks_dir=homeworks_dir,
        freeimage_api_key=freeimage_api_key,
        telegraph_token=telegraph_token,
    )
