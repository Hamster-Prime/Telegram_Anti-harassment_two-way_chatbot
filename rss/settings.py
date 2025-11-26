import json
from pathlib import Path
from typing import Any, Dict
from config import config

SETTINGS_FILE = Path(__file__).parent.parent / "data" / "rss_settings.json"

_state: Dict[str, Any] = {
    "enabled": config.RSS_ENABLED,
    "data_file": config.RSS_DATA_FILE,
    "check_interval": config.RSS_CHECK_INTERVAL,
    "authorized_users": config.RSS_AUTHORIZED_USER_IDS.copy(),
}


def _load_state() -> None:
    if not SETTINGS_FILE.exists():
        return
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            loaded = json.load(file)
            if isinstance(loaded, dict):
                _state.update(loaded)
    except Exception as exc:
        print(f"加载 RSS 设置失败: {exc}")


def _save_state() -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(_state, file, indent=2, ensure_ascii=False)


def is_enabled() -> bool:
    return bool(_state.get("enabled", False))


def set_enabled(value: bool) -> None:
    _state["enabled"] = bool(value)
    _save_state()


def get_data_file() -> str:
    data_file = _state.get("data_file") or config.RSS_DATA_FILE
    return str(data_file)


def get_check_interval() -> int:
    try:
        return int(_state.get("check_interval", config.RSS_CHECK_INTERVAL))
    except (TypeError, ValueError):
        return config.RSS_CHECK_INTERVAL


def set_check_interval(seconds: int) -> None:
    _state["check_interval"] = int(seconds)
    _save_state()


def set_data_file(path: str) -> None:
    _state["data_file"] = path
    _save_state()


def get_authorized_users() -> list[int]:
    return list({int(user_id) for user_id in _state.get("authorized_users", [])})


def add_authorized_user(user_id: int) -> bool:
    user_id = int(user_id)
    users = set(get_authorized_users())
    if user_id in users:
        return False
    users.add(user_id)
    _state["authorized_users"] = sorted(users)
    _save_state()
    return True


def remove_authorized_user(user_id: int) -> bool:
    user_id = int(user_id)
    users = set(get_authorized_users())
    if user_id not in users:
        return False
    users.remove(user_id)
    _state["authorized_users"] = sorted(users)
    _save_state()
    return True


_load_state()

