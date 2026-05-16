"""Platform-aware key normalization for actions (ported from mano-afk-public)."""

import platform
from copy import deepcopy


def normalize_actions(actions):
    """Normalize key/modifier names for the current platform."""
    is_macos = platform.system() == "Darwin"
    click_actions = {"left_click", "right_click", "double_click", "middle_click", "triple_click"}

    normalized = []
    for a in actions or []:
        item = deepcopy(a)
        tool_input = item.get("input") or {}
        action = str(tool_input.get("action") or "").strip().lower()

        if action == "key":
            mods, mains = _normalize_combo_to_mods_and_mains(tool_input.get("text"), is_macos)
            tool_input["modifiers"] = mods
            tool_input["mains"] = mains

        elif action in click_actions:
            mods, _ = _normalize_combo_to_mods_and_mains(tool_input.get("text"), is_macos)
            tool_input["modifiers"] = mods

        item["input"] = tool_input
        normalized.append(item)

    return normalized


def _normalize_combo_to_mods_and_mains(combo, is_macos):
    parts = _split_combo(combo)
    modifiers = []
    mains = []
    for p in parts:
        k = _normalize_key_token(p, is_macos)
        if not k:
            continue
        if _is_modifier(k):
            modifiers.append(k)
        else:
            mains.append(k)
    return modifiers, mains


def _split_combo(combo):
    if combo is None:
        return []
    if isinstance(combo, list):
        return [str(x).strip() for x in combo if str(x).strip()]
    s = str(combo).strip()
    if "+" in s:
        return [x.strip() for x in s.split("+") if x.strip()]
    return [x.strip() for x in s.split() if x.strip()]


def _is_modifier(k):
    return k in {
        "cmd", "ctrl", "alt", "shift",
        "cmd_l", "cmd_r", "ctrl_l", "ctrl_r",
        "alt_l", "alt_r", "alt_gr", "shift_l", "shift_r",
    }


def _normalize_key_token(k, is_macos):
    k = str(k).strip().lower()
    k = k.replace("-", "_").replace(" ", "_")

    # "command" / "cmd" — macOS Cmd, Windows uses Ctrl as Cmd-equivalent.
    if k in ("command", "cmd"):
        return "cmd" if is_macos else "ctrl"
    # "win" / "meta" / "super" — these refer to the Windows / Super key on
    # Linux/Windows, which pynput exposes as Key.cmd. On macOS we still want
    # cmd. Previously this collapsed to Ctrl on Windows, which broke shortcuts
    # like Win+E / Win+R.
    if k in ("win", "meta", "super"):
        return "cmd"
    if k in ("control", "ctl", "ctrl"):
        return "cmd" if is_macos else "ctrl"
    if k in ("option", "opt"):
        return "alt"

    if k in ("command_l", "cmd_l"):
        return "cmd_l" if is_macos else "ctrl_l"
    if k in ("command_r", "cmd_r"):
        return "cmd_r" if is_macos else "ctrl_r"
    if k in ("meta_l", "super_l", "win_l"):
        return "cmd_l"
    if k in ("meta_r", "super_r", "win_r"):
        return "cmd_r"
    if k in ("control_l", "ctl_l", "ctrl_l"):
        return "cmd_l" if is_macos else "ctrl_l"
    if k in ("control_r", "ctl_r", "ctrl_r"):
        return "cmd_r" if is_macos else "ctrl_r"
    if k in ("option_l", "opt_l"):
        return "alt_l"
    if k in ("option_r", "opt_r"):
        return "alt_r"
    if k == "altgr":
        return "alt_gr"

    alias_map = {
        "return": "enter",
        "escape": "esc",
        "spacebar": "space",
        "arrowup": "up", "arrow_up": "up",
        "arrowdown": "down", "arrow_down": "down",
        "arrowleft": "left", "arrow_left": "left",
        "arrowright": "right", "arrow_right": "right",
        "pageup": "page_up", "pgup": "page_up",
        "pagedown": "page_down", "pgdn": "page_down",
        "delete": "backspace",
        "del": "backspace",
        # Extras commonly emitted by Windows-leaning prompts.
        "backspace": "backspace",
        "forward_delete": "delete",
        "home": "home",
        "end": "end",
        "insert": "insert",
        "ins": "insert",
        "printscreen": "print_screen",
        "prtsc": "print_screen",
        "prtscr": "print_screen",
        "caps": "caps_lock",
        "capslock": "caps_lock",
        "numlock": "num_lock",
        "scrolllock": "scroll_lock",
        "contextmenu": "menu",
        "app": "menu",
        # Function keys (no remapping needed, but keep here for documentation).
        **{f"f{i}": f"f{i}" for i in range(1, 25)},
        # Numpad aliases used by some prompts (pynput exposes plain digits).
        **{f"numpad{i}": str(i) for i in range(0, 10)},
        "numpadenter": "enter",
        "numpad_add": "+", "numpad_subtract": "-",
        "numpad_multiply": "*", "numpad_divide": "/",
        "numpad_decimal": ".",
    }
    return alias_map.get(k, k)
