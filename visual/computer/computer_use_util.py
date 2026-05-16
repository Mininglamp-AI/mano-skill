import base64
import os
import uuid
from typing import Any, Dict, Optional

import mss
import mss.tools
from pynput import mouse

from visual.config.visual_config import AUTOMATION_CONFIG


def get_primary_monitor(sct: "mss.base.MSSBase") -> Dict[str, Any]:
    """Return the primary monitor descriptor from an open mss instance.

    mss exposes monitors[0] as the virtual screen (all monitors merged) and
    monitors[1..N] as individual displays. monitors[1] is *not* guaranteed to
    be the primary one — in multi-monitor setups (Mano-P issue #16) the user
    can re-mark any display as primary.

    Selection strategy (independent of mss version):
      1. Pick the monitor that contains the origin (0, 0). On Windows the
         primary monitor is the one with ``(left, top) == (0, 0)``; secondary
         displays have negative or positive offsets. On macOS the primary
         display also anchors at (0, 0). On Linux/X11 the primary is exposed
         the same way under mss. This rule is OS-level and holds across mss
         versions, including releases that don't expose ``is_primary``.
      2. If no monitor contains (0, 0) (extremely unusual, e.g. all displays
         have non-zero offsets in some virtual setups), opportunistically use
         the modern ``is_primary`` flag if mss exposes it.
      3. Final fallback: ``monitors[1]`` (legacy assumption — same behaviour
         as the original code, so a worst-case selection equals a no-op).
    """
    monitors = sct.monitors
    if len(monitors) <= 1:
        return monitors[0]

    # Strategy 1: monitor that contains (0, 0)
    for m in monitors[1:]:
        left = m.get("left", 0)
        top = m.get("top", 0)
        width = m.get("width", 0)
        height = m.get("height", 0)
        if left <= 0 < left + width and top <= 0 < top + height:
            return m

    # Strategy 2: explicit is_primary flag (mss >= 10.2 exposes this)
    for m in monitors[1:]:
        if m.get("is_primary"):
            return m

    # Strategy 3: legacy fallback (== original sct.monitors[1] behaviour)
    return monitors[1]


def screenshot_to_bytes():
    """Capture the primary screen and return PNG bytes."""
    with mss.mss() as sct:
        primary = get_primary_monitor(sct)
        screenshot = sct.grab(primary)
        return mss.tools.to_png(screenshot.rgb, screenshot.size)

def b64_png(png_bytes: bytes) -> str:
    """Encode PNG bytes to base64 string"""
    return base64.b64encode(png_bytes).decode("utf-8")

def make_tool_result(tool_use_id: str, ok: bool, message: str,
                     include_screenshot: bool, screenshot_bytes: Optional[bytes],
                     meta: Optional[Dict[str, Any]]=None):
    """Build tool result"""
    tr: Dict[str, Any] = {
        "tool_use_id": tool_use_id,
        "status": "success" if ok else "error",
        "output": message,
        "error": None if ok else message,
        "include_screenshot": bool(include_screenshot),
        "meta": meta or {},
    }
    if include_screenshot and screenshot_bytes:
        tr["screenshot_b64"] = b64_png(screenshot_bytes)
    return tr

def focus_on_primary_screen():
    """Focus mouse on primary screen center"""
    with mss.mss() as sct:
        primary = get_primary_monitor(sct)
        mouse_controller = mouse.Controller()
        mouse_controller.position = (
            primary["left"] + primary["width"] // 2,
            primary["top"] + primary["height"] // 2
        )

def get_or_create_device_id():
    """Get or create device ID"""
    device_file = os.path.expanduser(AUTOMATION_CONFIG["DEVICE_FILE"])
    if os.path.exists(device_file):
        with open(device_file, "r") as f:
            return f.read().strip()

    device_id = str(uuid.uuid4())
    with open(device_file, "w") as f:
        f.write(device_id)
    return device_id