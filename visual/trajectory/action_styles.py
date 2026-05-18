"""Map action descriptions to report styling kinds."""

from typing import Any, List, Optional

ACTION_KIND_INITIALIZING = "initializing"
ACTION_KIND_OPEN_APP = "open_app"
ACTION_KIND_KEY = "key"
ACTION_KIND_CLICK = "click"
ACTION_KIND_TYPE = "type"
ACTION_KIND_DONE = "done"
ACTION_KIND_FAIL = "fail"
ACTION_KIND_OTHER = "other"


def infer_action_kind(
    action_desc: str,
    actions: Optional[List[dict]] = None,
) -> str:
    """Derive action_kind from human-readable action_desc and optional structured actions."""
    desc = (action_desc or "").strip()
    desc_lower = desc.lower()

    if desc == "Initializing" or desc_lower == "initializing":
        return ACTION_KIND_INITIALIZING
    if desc == "DONE" or desc_lower == "done":
        return ACTION_KIND_DONE
    if desc == "FAIL" or desc_lower == "fail":
        return ACTION_KIND_FAIL
    if desc_lower.startswith("open app:") or desc_lower.startswith("open app "):
        return ACTION_KIND_OPEN_APP
    if desc_lower.startswith("key:"):
        return ACTION_KIND_KEY
    if "click" in desc_lower:
        return ACTION_KIND_CLICK
    if desc_lower.startswith("type:") or desc_lower.startswith("type "):
        return ACTION_KIND_TYPE

    if actions:
        first = actions[0] or {}
        name = (first.get("name") or "").lower()
        if name == "open_app":
            return ACTION_KIND_OPEN_APP
        if name == "computer":
            inp = first.get("input") or {}
            act = (inp.get("action") or "").lower()
            if act == "key":
                return ACTION_KIND_KEY
            if act in ("click", "left_click", "right_click", "double_click"):
                return ACTION_KIND_CLICK
            if act == "type":
                return ACTION_KIND_TYPE

    return ACTION_KIND_OTHER


def css_class_for_kind(action_kind: str) -> str:
    """Return CSS class name for an action_kind."""
    return f"action-{action_kind.replace('_', '-')}"
