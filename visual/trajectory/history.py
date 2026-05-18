"""Append enhanced lines to trajectory history.jsonl."""

import json
import os
import time
from typing import Any, Dict, List, Optional

from visual.trajectory.action_styles import infer_action_kind


def append_history_line(
    trajectory_dir: str,
    *,
    step: int,
    action_desc: str,
    reasoning: str = "",
    actions: Optional[List[Dict[str, Any]]] = None,
    phase: str = "action",
    status: Optional[str] = None,
    screenshot: Optional[str] = None,
) -> None:
    """Append one JSON line to history.jsonl with the enhanced schema."""
    actions = actions or []
    line: Dict[str, Any] = {
        "step": step,
        "reasoning": reasoning or "",
        "action_desc": action_desc,
        "actions": [
            {
                "name": a.get("name"),
                "input": a.get("input"),
                "action_type": a.get("action_type"),
            }
            for a in actions
        ],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phase": phase,
        "action_kind": infer_action_kind(action_desc, actions),
    }
    if status is not None:
        line["status"] = status
    if screenshot is not None:
        line["screenshot"] = screenshot

    history_path = os.path.join(trajectory_dir, "history.jsonl")
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
