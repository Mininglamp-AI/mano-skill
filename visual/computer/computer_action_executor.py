import os
import platform
import shutil
import subprocess
import time
from typing import Any, Dict

import mss
from pynput import mouse, keyboard
from pynput.keyboard import Key
from pynput.mouse import Button

from visual.config.visual_config import AUTOMATION_CONFIG
from visual.computer.computer_use_util import get_primary_monitor


# Common Git-for-Windows install locations to probe when bash is not on PATH.
# Covers default Program Files (64/32-bit), the per-user installer, and scoop.
_WINDOWS_BASH_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\git\current\bin\bash.exe"),
)


def _find_windows_bash():
    """Locate a bash.exe on Windows. AGENT_SHELL override, then PATH, then known
    Git-for-Windows paths. Returns None if none found (caller surfaces an error)."""
    override = os.environ.get("AGENT_SHELL", "")
    if override:
        return override if os.path.isfile(override) else None
    on_path = shutil.which("bash")
    if on_path:
        return on_path
    for cand in _WINDOWS_BASH_CANDIDATES:
        if cand and os.path.isfile(cand):
            return cand
    return None


class ComputerActionExecutor:
    """Automation action executor"""

    def __init__(self, on_minimize_panel=None):
        self.on_minimize_panel = on_minimize_panel
        with mss.mss() as sct:
            monitor = get_primary_monitor(sct)
            actual_width = monitor["width"]
            actual_height = monitor["height"]

        # Calculate coordinate scaling ratio
        self.scale_x = actual_width / AUTOMATION_CONFIG["SCREEN_SCALE_WIDTH"]
        self.scale_y = actual_height / AUTOMATION_CONFIG["SCREEN_SCALE_HEIGHT"]

        # Initialize controllers
        self.mouse_controller = mouse.Controller()
        self.keyboard_controller = keyboard.Controller()

    def run_one(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute single action"""
        tool_name = action.get("name", "")
        tool_input = (action.get("input") or {})
        action = (tool_input.get("action") or "").strip()
        start_time = time.time()

        try:
            if tool_name == "bash":
                result = self._run_bash(tool_input)
                return result
            elif tool_name == "minimize_panel":
                if self.on_minimize_panel:
                    self.on_minimize_panel()
                msg = "panel minimized"
            elif tool_name == "open_app":
                app_name = tool_input.get("app_name", "")
                if app_name:
                    self._open_app(app_name)
                    msg = f"open app {app_name} ok"
                else:
                    msg = "Missing app name"
            elif tool_name == "open_url":
                url = tool_input.get("url", "")
                if url:
                    self._open_url(url)
                    msg = f"open url {url} ok"
                else:
                    msg = "Missing url"
            elif tool_name == "computer":
                if action in ("left_click", "right_click", "double_click", "middle_click", "triple_click"):
                    self._do_click(action, tool_input)
                    msg = f"{action} ok"

                elif action in ("type",):
                    text = tool_input.get("text")
                    self._type_text(text)
                    msg = f"type {text} ok"

                elif action in ("key",):
                    self._do_hotkey(tool_input)
                    msg = f"hotkey ok"

                elif action in ("mouse_move",):
                    x, y = self._mouse_move(tool_input)
                    msg = f"mouse_move ({x},{y}) ok"

                elif action in ("left_click_drag",):
                    start = tool_input.get("start_coordinate")
                    if start:
                        sx, sy = self._xy(start)
                        self.mouse_controller.position = (sx, sy)
                        time.sleep(0.2)
                    # Start drag
                    self.mouse_controller.press(Button.left)
                    x, y = self._mouse_move(tool_input)
                    time.sleep(0.2)
                    self.mouse_controller.release(Button.left)
                    msg = f"drag_to ({x},{y}) ok"

                elif action == "scroll":
                    self._do_scroll(tool_input)
                    msg = "scroll ok"

                elif action == "wait":
                    time.sleep(0.5)
                    msg = "wait ok"

                elif action == "screenshot":
                    msg = "screenshot requested"

                elif action in ("done", "finish_task", "fail", "call_user"):
                    msg = action

                else:
                    raise ValueError(f"Unknown action: {action}")

            dt = time.time() - start_time
            return {
                "ok": action != "fail",
                "message": msg,
                "meta": {"action": action, "elapsed_time": dt},
            }

        except Exception as e:
            dt = time.time() - start_time
            return {
                "ok": False,
                "message": f"{type(e).__name__}: {e}",
                "meta": {"action": action, "elapsed_time": dt},
            }

    def _mouse_move(self, tool_input):
        """Smooth mouse movement"""
        coord = tool_input.get("coordinate")
        dur = tool_input.get("duration") or 0.3
        x, y = self._xy(coord)

        current_pos = self.mouse_controller.position
        steps = max(10, int(dur * AUTOMATION_CONFIG["MOUSE_MOVE_STEPS_PER_SEC"]))

        for i in range(steps + 1):
            t = i / steps
            new_x = current_pos[0] + (x - current_pos[0]) * t
            new_y = current_pos[1] + (y - current_pos[1]) * t
            self.mouse_controller.position = (new_x, new_y)
            time.sleep(dur / steps)
        return x, y

    def _do_click(self, action: str, tool_input: Dict[str, Any]):
        """Execute click operation"""
        coord = tool_input.get("coordinate")
        if coord:
            x, y = self._xy(coord)
            self.mouse_controller.position = (x, y)
            time.sleep(AUTOMATION_CONFIG["MOUSE_CLICK_DELAY"])

        mods = tool_input.get("modifiers") or []
        for k in mods:
            self.keyboard_controller.press(getattr(Key, k))

        if action == "left_click":
            self.mouse_controller.click(Button.left)
        elif action == "right_click":
            self.mouse_controller.click(Button.right)
        elif action == "double_click":
            self.mouse_controller.click(Button.left, 2)
        elif action == "triple_click":
            self.mouse_controller.click(Button.left, 3)
        elif action == "middle_click":
            self.mouse_controller.click(Button.middle)
        else:
            raise ValueError(action)

        for k in reversed(mods):
            self.keyboard_controller.release(getattr(Key, k))

    def _type_text(self, text: str):
        """Type text: direct keypress for safe chars (digits/punctuation), clipboard paste otherwise."""
        if self._is_safe_for_direct_type(text):
            for char in text:
                self.keyboard_controller.type(char)
                time.sleep(0.02)
        else:
            self._paste_from_clipboard(text)

    def _is_safe_for_direct_type(self, text: str) -> bool:
        """Characters that have direct keycodes and are never intercepted by IME."""
        safe = set('0123456789.-+_@#$/\\() ')
        return all(c in safe for c in text)

    def _paste_from_clipboard(self, text: str):
        """Type text via clipboard paste (avoids input method conflicts)."""
        system = platform.system()
        if system == "Darwin":
            env = os.environ.copy()
            env["LANG"] = "en_US.UTF-8"
            env["LC_ALL"] = "en_US.UTF-8"
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), env=env, check=True)
        elif system == "Windows":
            subprocess.run(["clip"], input=text.encode("utf-16le"), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)

        time.sleep(0.05)
        paste_key = Key.cmd if system == "Darwin" else Key.ctrl
        self.keyboard_controller.press(paste_key)
        self.keyboard_controller.press("v")
        self.keyboard_controller.release("v")
        self.keyboard_controller.release(paste_key)

    def _do_hotkey(self, tool_input):
        """Execute hotkey"""
        mods = tool_input.get("modifiers") or []
        mains = tool_input.get("mains") or []

        if not mains:
            return

        for m in mods:
            self.keyboard_controller.press(getattr(Key, m))
        time.sleep(AUTOMATION_CONFIG["HOTKEY_DELAY"])

        for k in mains:
            key_obj = getattr(Key, k) if hasattr(Key, k) else k
            self.keyboard_controller.press(key_obj)
            self.keyboard_controller.release(key_obj)

        time.sleep(0.02)
        for m in reversed(mods):
            self.keyboard_controller.release(getattr(Key, m))

    def _do_scroll(self, tool_input: Dict[str, Any]):
        """Execute scroll operation"""
        direction = tool_input.get("scroll_direction")
        scroll_amount = tool_input.get("scroll_amount") or 10
        coord = tool_input.get("coordinate")

        scroll_amount = scroll_amount * AUTOMATION_CONFIG["SCROLL_MULTIPLIER"]

        if coord:
            x, y = self._xy(coord)
            self.mouse_controller.position = (x, y)
            time.sleep(AUTOMATION_CONFIG["MOUSE_CLICK_DELAY"])

        if direction in ("up", "down"):
            delta_y = scroll_amount if direction == "up" else -scroll_amount
            self.mouse_controller.scroll(0, delta_y)
        elif direction in ("left", "right"):
            delta_x = scroll_amount if direction == "right" else -scroll_amount
            self.mouse_controller.scroll(delta_x, 0)
        else:
            raise ValueError(f"scroll_direction invalid: {direction}")

    def _xy(self, coord):
        """Convert coordinates to actual screen"""
        if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
            raise ValueError(f"coordinate must be [x,y], got {coord}")

        x = int(coord[0] * self.scale_x)
        y = int(coord[1] * self.scale_y)

        with mss.mss() as sct:
            primary = get_primary_monitor(sct)
            x = primary["left"] + x
            y = primary["top"] + y
        return x, y
    
    def _move_to_primary(self, app_name):
        """Move app's front window to the primary screen (macOS only)"""
        try:
            script = (
                f'tell application "System Events"\n'
                f'    tell process "{app_name}"\n'
                f'        set position of window 1 to {{0, 25}}\n'
                f'    end tell\n'
                f'end tell'
            )
            subprocess.run(["osascript", "-e", script], timeout=3, capture_output=True)
        except Exception:
            pass  # Best effort, don't fail the action

    def _open_app(self, app_name):
        """Cross-platform app launcher"""
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", "-a", app_name])
                time.sleep(1)
                self._move_to_primary(app_name)
            elif system == "Windows":
                self._open_app_windows(app_name)
            else:
                subprocess.Popen([app_name])
        except Exception as e:
            raise RuntimeError(f"Failed to open {app_name}: {e}")

    # ---- Windows app launcher helpers (kept private; no impact on macOS) ----

    def _open_app_windows(self, app_name: str):
        """Open a Windows app, with alias support for UWP / system pages.

        Order of attempts:
          1. Alias lookup (covers ms-settings:, calculator:, AppsFolder, etc.).
          2. ``os.startfile`` (handles registry-known executables, URI handlers,
             and absolute paths uniformly without spawning a shell).
          3. PowerShell ``Start-Process`` fallback (legacy behaviour).
        """
        original = (app_name or "").strip()
        if not original:
            raise RuntimeError("Missing app name")
        key = original.lower()
        from visual.win_app_aliases import WIN_APP_ALIASES
        target = WIN_APP_ALIASES.get(key, original)

        # 1) explorer.exe shell:... aliases need a shell invocation
        if target.lower().startswith("explorer.exe "):
            subprocess.Popen(target, shell=True)
            return

        # 2) ms-* / calculator: / outlookcal: — URI handlers
        if ":" in target and not (len(target) > 1 and target[1] == ":"):
            # Treat as URI (skip drive letters like C:)
            try:
                os.startfile(target)
                return
            except OSError:
                pass  # fall through

        # 3) plain executable / file path
        try:
            os.startfile(target)
            return
        except OSError:
            pass

        # 4) Last resort: Start-Process via PowerShell (preserves legacy)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f'Start-Process "{target}"'],
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            raise RuntimeError(f"Failed to open '{original}': {err or 'unknown error'}")

    def _open_url(self, url):
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", url])
                time.sleep(1)
                # Move the frontmost app's window to primary screen
                script = (
                    'tell application "System Events"\n'
                    '    set frontApp to name of first application process whose frontmost is true\n'
                    '    tell process frontApp\n'
                    '        set position of window 1 to {0, 25}\n'
                    '    end tell\n'
                    'end tell'
                )
                subprocess.run(["osascript", "-e", script], timeout=3, capture_output=True)
            elif system == "Windows":
                subprocess.Popen(f'start "" "{url}"', shell=True)
            else:
                subprocess.Popen(["xdg-open", url])
        except Exception as e:
            raise RuntimeError(f"Failed to open {url}: {e}")

    def _run_bash(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute shell command and return output.

        On Windows: Git-for-Windows bash (errors clearly if not found).
        On macOS/Linux: /bin/sh via shell=True.
        """
        start_time = time.time()
        command = tool_input.get("command")
        restart = tool_input.get("restart", False)

        if restart:
            # Stateless subprocess — no persistent session to restart.
            # Return success so model doesn't retry, but log a warning.
            print("  [bash] Warning: restart requested but sessions are stateless (no-op)")
            return {
                "ok": True,
                "message": "Bash session restarted",
                "meta": {"action": "bash_restart", "elapsed_time": time.time() - start_time},
                "is_bash": True,
            }

        if not command:
            return {
                "ok": False,
                "message": "No command provided",
                "meta": {"action": "bash", "elapsed_time": time.time() - start_time},
                "is_bash": True,
            }

        try:
            if platform.system() == "Windows":
                # Run through Git-for-Windows bash: the model emits bash far more
                # reliably than PowerShell, and routing every platform through bash
                # keeps behaviour uniform. [bash, "-c", cmd] handles a bash path
                # with spaces (C:\Program Files\Git\...) without shell=True.
                bash = _find_windows_bash()
                if not bash:
                    return {
                        "ok": False,
                        "message": (
                            "Error: no bash interpreter found. This client runs commands "
                            "through bash on Windows. Install Git for Windows (provides "
                            "bash.exe) or set the AGENT_SHELL environment variable to a "
                            "bash path."
                        ),
                        "meta": {"action": "bash", "command": command, "elapsed_time": time.time() - start_time},
                        "is_bash": True,
                    }
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                result = subprocess.run(
                    [bash, "-c", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    cwd=os.path.expanduser("~"),
                    env=env,
                )
            else:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.expanduser("~"),
                )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            # Truncate large output
            if len(output) > 10000:
                output = output[:10000] + f"\n\n... Output truncated ({len(output)} total chars) ..."
            ok = result.returncode == 0
            dt = time.time() - start_time
            return {
                "ok": ok,
                "message": output if output else ("Success" if ok else f"Exit code: {result.returncode}"),
                "meta": {"action": "bash", "command": command, "exit_code": result.returncode, "elapsed_time": dt},
                "is_bash": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": f"Error: Command timed out after 30 seconds",
                "meta": {"action": "bash", "command": command, "elapsed_time": time.time() - start_time},
                "is_bash": True,
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"Error: {type(e).__name__}: {e}",
                "meta": {"action": "bash", "command": command, "elapsed_time": time.time() - start_time},
                "is_bash": True,
            }
