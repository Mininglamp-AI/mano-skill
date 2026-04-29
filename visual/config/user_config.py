"""User-level persistent config (~/.mano/config.json)."""

import json
import os

USER_CONFIG_DIR = os.path.expanduser("~/.mano")
USER_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, "config.json")

CONFIG_DEFAULTS = {
    "max-steps": "100",
    "minimize": "false",
}

CONFIG_KEYS = {
    "default-model-path": "Local model weights directory (required for --local)",
    "w8a8":               "W8A8 INT8 acceleration: 'auto', 'on', or 'off' (default: auto, requires M5+)",
    "max-steps":          f"Maximum steps per task (default: {CONFIG_DEFAULTS['max-steps']})",
    "minimize":           f"Start with minimized UI panel: true/false (default: {CONFIG_DEFAULTS['minimize']})",
}


def load_user_config() -> dict:
    if not os.path.isfile(USER_CONFIG_FILE):
        return {}
    with open(USER_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_user_config(config: dict):
    os.makedirs(USER_CONFIG_DIR, exist_ok=True)
    with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_config(key: str):
    cfg = load_user_config()
    value = cfg.get(key)
    if value is None:
        value = CONFIG_DEFAULTS.get(key)
    return value


def set_config(key: str, value: str):
    cfg = load_user_config()
    cfg[key] = value
    save_user_config(cfg)


def list_config():
    cfg = load_user_config()
    print("Config (~/.mano/config.json):\n")
    for key, desc in CONFIG_KEYS.items():
        val = cfg.get(key) or CONFIG_DEFAULTS.get(key) or "(not set)"
        source = "config" if key in cfg else ("default" if key in CONFIG_DEFAULTS else "")
        print(f"  {key}: {val}  [{source}]  — {desc}")
