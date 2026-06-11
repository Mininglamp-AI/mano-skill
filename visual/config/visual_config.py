import platform as _platform
import subprocess as _subprocess

BASE_URL = "https://mano.mininglamp.com"

# Client version — keep in sync with brew formula
CLIENT_VERSION = "1.1.3"

def _get_chip_model() -> str:
    """Get Apple chip model (e.g. 'Apple M4 Pro') on macOS, empty string otherwise."""
    # Guard the sysctl call on non-macOS to avoid noisy FileNotFoundError stderr.
    if _platform.system() != "Darwin":
        return ""
    try:
        result = _subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=2
        )
        chip = result.stdout.strip()
        return chip if chip.startswith("Apple") else ""
    except Exception:
        return ""

def build_user_agent() -> str:
    """Build User-Agent: mano-cua/1.0.5 (macOS 26.3; arm64; Apple M4 Pro) Python/3.13.5"""
    os_ver = _platform.mac_ver()[0] or _platform.release()
    arch = _platform.machine()
    py_ver = _platform.python_version()
    system = _platform.system()
    if system == "Darwin":
        chip = _get_chip_model()
        chip_tag = f"; {chip}" if chip else ""
        os_tag = f"macOS {os_ver}"
    elif system == "Windows":
        os_tag = f"Windows NT {os_ver}"
        chip_tag = ""
    else:
        os_tag = f"{system} {os_ver}"
        chip_tag = ""
    return f"mano-cua/{CLIENT_VERSION} ({os_tag}; {arch}{chip_tag}) Python/{py_ver}"

API_HEADERS = {"User-Agent": build_user_agent()}
# Keep existing window/animation/text configurations unchanged
WINDOW_CONFIG = {
    "WIDTH": 320,
    "MINIMIZED_WIDTH": 110,
    "MINIMIZED_HEIGHT": 28,
    "MIN_HEIGHT": 240,
    "MAX_HEIGHT": 400,
    "MARGIN": 18,
    "ALPHA": 0.92,
    "BG_COLOR": "#1e1e1e",
    "LOG_BG_COLOR": "#000000",
    "TEXT_COLOR": "#eaeaea",
    "TITLE_FONT_SIZE": 12,
    "LOG_FONT_SIZE": 11,
    "CORNER_RADIUS": 14,
    "BUTTON_RADIUS": 10,
    "BUTTON_HEIGHT": 32,
    "STOP_BTN_COLOR": "#ff5050",
    "STOP_BTN_HOVER": "#ff7070"
}

ANIMATION_CONFIG = {
    "BLINK_INTERVAL": 500,
    "POLL_INTERVAL": 200,
    "STOP_DELAY": 1000,
    "HEIGHT_ADJUST_DELAY": 10
}

TEXT_CONSTANTS = {
    "WINDOW_TITLE": "VLA Task Monitor",
    "RUNNING_TEXT": "Running",
    "EVALUATING_TEXT": "Evaluating",
    "DONE_TEXT": "Done ✅",
    "STOPPED_TEXT": "Stopped ⏹",
    "ERROR_TEXT": "Error ❌",
    "STEP_PREFIX": "Step: ",
    "TASK_PREFIX": "Task: ",
    "STOP_BUTTON_TEXT": "Stop",
    "STOPPING_BUTTON_TEXT": "Stopping…",
    "CLOSE_BUTTON_TEXT": "Close",
    "ACTION_PREFIX": "Action: ",
    "REASONING_PREFIX": "Reasoning: "
}

TASK_STATUS = {
    "RUNNING": "running",
    "COMPLETED": "completed",
    "STOPPED": "stopped",
    "ERROR": "error",
    "CALL_USER": "call_user",
    "EVALUATING": "evaluating",
    "MAX_STEP_REACHED": "max_step_reached"
}

# ========== New: Automation Business Configuration ==========
AUTOMATION_CONFIG = {
    "BASE_URL": BASE_URL,
    "DEVICE_FILE": "~/.myapp_device_id",
    "SCREEN_SCALE_WIDTH": 1280,   # Server screenshot width
    "SCREEN_SCALE_HEIGHT": 720,  # Server screenshot height
    "SCROLL_MULTIPLIER": 5,      # Scroll multiplier
    "ACTION_DELAY": 2,           # Delay after action (seconds)
    "APP_START_DELAY": 1,        # App start delay (seconds)
    "MOUSE_MOVE_STEPS_PER_SEC": 30,  # Mouse movement smooth steps
    "MOUSE_CLICK_DELAY": 0.1,    # Delay before click
    "HOTKEY_DELAY": 0.08,        # Hotkey delay
    "SESSION_TIMEOUT": 60,       # Session request timeout (seconds)
    "STEP_TIMEOUT": 600,         # Step request timeout (seconds)
    "CLOSE_SESSION_TIMEOUT": 120  # Close session timeout (seconds), includes eval time
}