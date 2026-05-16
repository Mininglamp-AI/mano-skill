"""Unified Windows application alias table.

Single source of truth for mapping friendly app names to launch targets.
Both the model-tool executor (``computer_action_executor``) and the CLI
``--app`` entry point (``vla.py``) import from here.

Design rules:
  - Prefer Win32 exe names (``notepad.exe``) over UWP URI schemes — exe
    paths are more reliable for foreground control on Win11.
  - Keep URI / shell paths only for apps that have *no* classic exe
    (``ms-settings:``, ``ms-photos:``, etc.).
  - Keys are lowercase.  Callers must ``.lower()`` before lookup.
"""

WIN_APP_ALIASES: dict[str, str] = {
    # ── Settings & system ──────────────────────────────────────────────
    "settings": "ms-settings:",
    "system settings": "ms-settings:",
    "control panel": "control",
    "task manager": "taskmgr.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "finder": "explorer.exe",           # macOS Finder → Windows Explorer
    "run": "explorer.exe shell:::{2559a1f3-21d7-11d4-bdaf-00c04f60b9f0}",

    # ── Built-in classic apps ──────────────────────────────────────────
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",               # Windows Terminal
    "snipping tool": "ms-screenclip:",

    # ── UWP / Store apps (no classic exe available) ────────────────────
    "sticky notes": (
        "explorer.exe shell:AppsFolder\\"
        "Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe!App"
    ),
    "notes": (
        "explorer.exe shell:AppsFolder\\"
        "Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe!App"
    ),
    "mail": "outlookmail:",
    "calendar": "outlookcal:",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
    "clock": "ms-clock:",

    # ── Browsers ───────────────────────────────────────────────────────
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "safari": "msedge.exe",             # macOS Safari → Edge as proxy
}
