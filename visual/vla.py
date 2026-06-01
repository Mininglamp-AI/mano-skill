#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "pynput",
#     "mss",
#     "customtkinter",
# ]
# ///

import os
import sys
import platform
import argparse
import subprocess
import time
import requests

# Windows: emoji / non-ASCII output crashes on legacy GBK/CP936 consoles
# (mano-skill issues #1, #2, #3 — UnicodeEncodeError on cleanup print).
# Reconfigure stdout/stderr to UTF-8 with replace to keep mac/Linux untouched.
# The reconfigure() method only exists on TextIOWrapper (Python 3.7+ stdout/
# stderr); when the streams have been redirected (capsys, GUI console, daemon
# launchers, etc.) it may be missing or raise. All errors are swallowed since
# this is best-effort and must never block CLI startup.
if platform.system() == "Windows":
    for _stream in (sys.stdout, sys.stderr):
        if _stream is None:
            continue
        reconfigure = getattr(_stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            # Stream already locked (e.g. wrapped by pytest capture) or
            # underlying buffer doesn't support reconfigure — fine, fall back
            # to whatever encoding was active before. Subsequent emoji prints
            # will surface as UnicodeEncodeError but won't be worse than
            # before this patch.
            pass


def stop_session():
    """Stop the current active session for this device"""
    from visual.config.visual_config import BASE_URL
    from visual.computer.computer_use_util import get_or_create_device_id

    device_id = get_or_create_device_id()

    try:
        resp = requests.post(
            f"{BASE_URL}/v1/devices/{device_id}/stop",
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("ok"):
            print(f"Session stopped: {data.get('session_id')}")
            return 0
        else:
            print(f"No active session: {data.get('message')}")
            return 1
    except Exception as e:
        print(f"Failed to stop session: {e}")
        return 1


def _open_url_in_browser(url: str):
    """Open a URL in the default browser (cross-platform)."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", url])
        elif system == "Windows":
            subprocess.Popen(f'start "" "{url}"', shell=True)
        else:
            subprocess.Popen(["xdg-open", url])
        time.sleep(4)
    except Exception as e:
        print(f"Warning: failed to open URL: {e}")


# Windows alias map: lazy-loaded to avoid importing on macOS/Linux.
_WINDOWS_APP_ALIASES = None

def _get_win_aliases():
    global _WINDOWS_APP_ALIASES
    if _WINDOWS_APP_ALIASES is None:
        from visual.win_app_aliases import WIN_APP_ALIASES
        _WINDOWS_APP_ALIASES = WIN_APP_ALIASES
    return _WINDOWS_APP_ALIASES


def _bring_window_to_front_windows(process_name_hint: str) -> bool:
    """Try to bring a freshly-launched app to the foreground on Windows.

    Many Win11 apps (Notepad, Calculator, Settings) are UWP-wrapped and the
    initial Start-Process / startfile call returns before the real window
    surfaces — or the window opens behind the current foreground app.
    Without forcing focus, the GUI agent screenshots the previous app and
    reports "Notepad doesn't seem to have appeared yet" (mano-skill #5
    follow-up).

    Strategy:
      a) Walk all top-level windows; match by exe basename of the owning
         process (more reliable than title substring — freshly created
         windows may have empty titles for ~1 second on Win11).
      b) Fall back to title substring match.

    Returns True iff a matching window was brought to front.
    """
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowText = user32.GetWindowTextW
        GetWindowTextLength = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        SetForegroundWindow = user32.SetForegroundWindow
        ShowWindow = user32.ShowWindow
        OpenProcess = kernel32.OpenProcess
        CloseHandle = kernel32.CloseHandle
        GetModuleBaseNameW = psapi.GetModuleBaseNameW
        # SW_RESTORE=9: undo minimize without changing maximized state.
        SW_RESTORE = 9
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        hint = process_name_hint.lower().strip()
        # Prefer exe-name match: "notepad" → "notepad.exe".
        exe_target = hint if hint.endswith(".exe") else f"{hint}.exe"

        target_hwnd = []

        def _enum_cb(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            # a) match by owning process exe name
            pid = wintypes.DWORD(0)
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                hproc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                if hproc:
                    try:
                        buf = ctypes.create_unicode_buffer(260)
                        if GetModuleBaseNameW(hproc, None, buf, 260) > 0:
                            exe = buf.value.lower()
                            if exe == exe_target or exe.startswith(hint):
                                target_hwnd.append(hwnd)
                                return False
                    finally:
                        CloseHandle(hproc)
            # b) fallback: title substring
            length = GetWindowTextLength(hwnd)
            if length > 0:
                tbuf = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, tbuf, length + 1)
                if hint in tbuf.value.lower():
                    target_hwnd.append(hwnd)
                    return False
            return True

        EnumWindows(EnumWindowsProc(_enum_cb), 0)
        if not target_hwnd:
            return False
        hwnd = target_hwnd[0]
        ShowWindow(hwnd, SW_RESTORE)
        # SetForegroundWindow is denied on Win10/11 when the calling process
        # is not the current foreground (Microsoft's anti focus-stealing).
        # Workaround: AttachThreadInput to the foreground thread, set focus,
        # detach. This is a documented stable technique.
        if SetForegroundWindow(hwnd):
            return True
        try:
            GetForegroundWindow = user32.GetForegroundWindow
            AttachThreadInput = user32.AttachThreadInput
            GetCurrentThreadId = kernel32.GetCurrentThreadId
            fg_hwnd = GetForegroundWindow()
            fg_thread = GetWindowThreadProcessId(fg_hwnd, None)
            cur_thread = GetCurrentThreadId()
            if fg_thread and fg_thread != cur_thread:
                AttachThreadInput(cur_thread, fg_thread, True)
                try:
                    SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                finally:
                    AttachThreadInput(cur_thread, fg_thread, False)
                return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def _open_app(app_name: str) -> str:
    """Open an application (cross-platform).

    Returns a window-title hint (lowercase substring) that can be used
    later to re-foreground the app after the GUI overlay initializes
    (Tk steals focus when its window appears, so a one-shot bring-to-
    front during launch isn't enough on Windows).

    On Windows, three layers of fallback:
      1. alias table ("Notepad" → notepad.exe) launched via os.startfile —
         this is the most reliable path for classic Win32 apps because it
         goes through ShellExecute + handles PATH-resolved exes.
      2. raw `Start-Process "<name>"` for anything not in the alias table
         (covers UWP apps registered with display names, custom installs).
      3. After launch, wait briefly and force the window to the foreground
         so the GUI agent's first screenshot actually contains the app.
    """
    system = platform.system()
    hint = app_name.strip().lower()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
            time.sleep(2)
            return hint
        if system == "Windows":
            key = app_name.strip().lower()
            launched = False
            # Layer 1: alias table → os.startfile
            target = _get_win_aliases().get(key)
            if target:
                try:
                    os.startfile(target)
                    launched = True
                except OSError:
                    launched = False
            # Layer 2: PowerShell Start-Process (handles UWP, display names)
            if not launched:
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         f'Start-Process "{app_name}"'],
                        shell=False, capture_output=True, text=True, timeout=10,
                    )
                    launched = True
                except Exception as e:
                    print(f"Warning: Start-Process failed: {e}")
            # Hint = exe stem (notepad.exe → "notepad") falls back to user
            # input. Used for both the initial bring-to-front and the
            # re-foreground call after Tk UI initializes.
            hint = (target or app_name).rsplit(".", 1)[0].strip().lower()
            # Layer 3: wait for window, force foreground (best-effort).
            # Win11 Notepad cold-starts via UWP-style broker and the window
            # can take 1-3 seconds to actually exist after os.startfile
            # returns. Poll up to 6 seconds.
            for _ in range(60):  # ~6s max @ 100ms
                time.sleep(0.1)
                if _bring_window_to_front_windows(hint):
                    break
            return hint
        # Linux / other Unix
        subprocess.Popen([app_name])
        time.sleep(2)
        return hint
    except Exception as e:
        print(f"Warning: failed to open app: {e}")
        return hint


def run_task(task: str, expected_result: str = None, minimize: bool = False,
             max_steps: int = None, local: bool = False, model_path: str = None,
             url: str = None, app: str = None):
    """Run an automation task"""
    from visual.config.visual_config import BASE_URL, AUTOMATION_CONFIG, API_HEADERS
    from visual.computer.computer_use_util import get_or_create_device_id

    # Open app/URL before starting (both modes)
    app_hint = None
    if app:
        app_hint = _open_app(app)
    if url:
        _open_url_in_browser(url)

    if local:
        # --- Local mode ---
        # Local inference (MLX + cider) is Apple Silicon only. Fail fast on
        # Windows / Linux so users don't sit through a doomed pip install.
        if platform.system() != "Darwin":
            print("Error: --local mode requires macOS with Apple Silicon (mlx-vlm + cider).")
            print("On Windows / Linux, use cloud mode (omit --local).")
            return 2
        try:
            from visual.agents.local import LocalAgent
        except ImportError as e:
            print(f"Error: Local mode dependencies not available: {e}")
            print("Run: mano-cua install-sdk")
            return 1

        resolved_path = model_path
        if not resolved_path:
            from visual.config.user_config import get_config
            resolved_path = get_config("default-model-path")
        if not resolved_path:
            print("Error: No model path specified. Use --model-path or run:")
            print("  mano-cua config --set default-model-path ~/path/to/model")
            return 1

        agent = LocalAgent(model_path=resolved_path)
    else:
        # --- Cloud mode (default, existing behavior) ---
        device_id = get_or_create_device_id()
        try:
            body = {
                "task": task,
                "device_id": device_id,
                "platform": platform.system(),
            }
            # Add bash capability unless disabled
            from visual.config.user_config import get_config
            if get_config("disable-bash") != "true":
                body["capabilities"] = ["bash"]
            if expected_result:
                body["expected_result"] = expected_result

            resp = requests.post(
                f"{BASE_URL}/v1/sessions",
                json=body,
                headers=API_HEADERS,
                timeout=AUTOMATION_CONFIG["SESSION_TIMEOUT"]
            )
            if resp.status_code == 409:
                print(f"Error: Another task is already running on this device.")
                print(f"Use 'mano-cua stop' to stop it first.")
                return 1

            resp.raise_for_status()
            data = resp.json()

            session_id = data["session_id"]
            print(f"Session created: {session_id}")

        except Exception as e:
            print(f"Failed to create session: {e}")
            return 1

        from visual.agents.cloud import CloudAgent
        agent = CloudAgent(server_url=BASE_URL, session_id=session_id, device_id=device_id)

    # Initialize UI and run
    from visual.view_model.task_view_model import TaskViewModel

    view_model = TaskViewModel()

    # Start minimized if requested
    if minimize and view_model.view and view_model.view._ui_initialized:
        view_model.view.root.after(200, view_model.view._toggle_minimize)

    if not view_model.init_task(task, agent, expected_result=expected_result, max_steps=max_steps):
        print("Failed to initialize visualization overlay.")
        # Run task directly without UI
        view_model.model.init_task(task, agent, expected_result=expected_result, max_steps=max_steps)
        view_model.model.run_automation_task()
        return 0 if view_model.model.state.status == "completed" else 1

    # Run task
    success = view_model.run_task()
    # Clean up resources
    view_model.close()
    return 0 if success else 1


# ========== Config / Check / Install subcommands ==========

def cmd_config(args):
    """Manage persistent config (~/.mano/config.json)"""
    from visual.config.user_config import get_config, set_config, list_config

    if args.config_list:
        list_config()
        return 0
    if args.get:
        val = get_config(args.get)
        if val is not None:
            print(val)
        else:
            print(f"(not set)")
        return 0
    if args.set:
        if len(args.set) != 2:
            print("Usage: mano-cua config --set KEY VALUE")
            return 1
        set_config(args.set[0], args.set[1])
        print(f"Set {args.set[0]} = {args.set[1]}")
        # Setting python-path: verify deps in that environment
        if args.set[0] == "python-path":
            py = args.set[1]
            if os.path.isfile(py):
                result = subprocess.run(
                    [py, "-c", "from vlm_service import custom_generate; from cider import is_available; import torch; print('OK')"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    set_config("sdk-installed", "true")
                    print("  Dependencies verified. sdk-installed = true")
                else:
                    err = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown error"
                    print(f"  Warning: dependencies missing in that environment — {err}")
                    print("  You may need to install: mlx-vlm, torch, cider (compiled from git)")
            else:
                print(f"  Warning: {py} not found")
        # Setting default-model-path: verify model exists and is MLX format
        if args.set[0] == "default-model-path":
            expanded = os.path.expanduser(args.set[1])
            if not os.path.isdir(expanded):
                print(f"  Error: path not found — {expanded}")
                return 1
            # Check for MLX format (should have weights/*.safetensors or *.npz, NOT model-*.safetensors in root)
            has_mlx_weights = os.path.isdir(os.path.join(expanded, "weights")) or \
                any(f.endswith(".npz") for f in os.listdir(expanded))
            has_hf_shards = any(f.startswith("model-") and f.endswith(".safetensors") for f in os.listdir(expanded))
            if has_hf_shards and not has_mlx_weights:
                print(f"  Error: model at {expanded} appears to be HuggingFace fp16 format, not MLX.")
                print(f"  Local mode requires MLX w8a16 quantized weights.")
                print(f"  Convert with:")
                print(f"    python -m mlx_vlm.convert --hf-path {expanded} --mlx-path {expanded}_mlx_w8a16 -q --q-bits 8 --dtype float16")
                print(f"  Then set the converted path:")
                print(f"    mano-cua config --set default-model-path {expanded}_mlx_w8a16")
                return 1
            set_config("model-installed", "true")
            print(f"  Model verified. model-installed = true")
        return 0

    print("Usage: mano-cua config [--list | --get KEY | --set KEY VALUE]")
    return 1


def cmd_check(args):
    """Check local mode dependencies"""
    from visual.config.user_config import get_config, set_config

    sdk_installed = get_config("sdk-installed") == "true"
    model_installed = get_config("model-installed") == "true"

    # If not marked, try to verify and update
    if not sdk_installed:
        python_path = get_config("python-path")
        py = python_path if python_path and os.path.isfile(python_path) else sys.executable
        result = subprocess.run(
            [py, "-c", "from vlm_service import custom_generate; from cider import is_available; import torch"],
            capture_output=True
        )
        if result.returncode == 0:
            set_config("sdk-installed", "true")
            sdk_installed = True

    if not model_installed:
        model_path = get_config("default-model-path")
        if model_path and os.path.isdir(os.path.expanduser(model_path)):
            set_config("model-installed", "true")
            model_installed = True

    # Report
    if sdk_installed:
        python_path = get_config("python-path") or sys.executable
        print(f"  sdk: OK (python: {python_path})")
    else:
        print("  sdk: NOT READY — run: mano-cua install-sdk")
        print("       or set python-path to an environment with deps:")
        print("       mano-cua config --set python-path /path/to/python")

    if model_installed:
        print(f"  model: OK ({get_config('default-model-path')})")
    else:
        print("  model: NOT READY — run: mano-cua install-model")
        print("       or set model path manually:")
        print("       mano-cua config --set default-model-path /path/to/model")

    if sdk_installed and model_installed:
        print("\nLocal mode is ready.")
        return 0
    else:
        print("\nLocal mode is not ready. Fix the items above.")
        return 1


def cmd_install_sdk(args):
    """Install local inference SDK into a persistent venv at ~/.mano/venv."""
    import subprocess

    # Local SDK (mlx-vlm + cider) is Apple Silicon only — fail fast.
    if platform.system() != "Darwin":
        print("Error: install-sdk targets local mode (mlx-vlm + cider), which is")
        print("macOS Apple Silicon only. On Windows / Linux, use cloud mode")
        print("(no install-sdk needed) — just run: mano-cua run \"...\"")
        return 2

    venv_dir = os.path.expanduser("~/.mano/venv")
    # macOS / Linux: bin/python3; Windows: Scripts\python.exe (kept for symmetry)
    if platform.system() == "Windows":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python3")

    # Create persistent venv if not exists
    if not os.path.isfile(venv_python):
        print(f"  Creating persistent venv at {venv_dir}...")
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)

    pip_cmd = [venv_python, "-m", "pip"]

    # 1. Base deps (same as brew venv — needed for mano-cua to run)
    print(f"  Installing base dependencies...")
    result = subprocess.run(pip_cmd + ["install", "requests", "mss", "pynput", "customtkinter", "Pillow", "huggingface_hub"], capture_output=True)
    if result.returncode != 0:
        print(f"  Base dependencies installation failed.")
        return 1

    # 2. mlx-vlm (includes mlx, transformers, etc.)
    print(f"  Installing mlx-vlm...")
    result = subprocess.run(pip_cmd + ["install", "mlx-vlm"])
    if result.returncode != 0:
        print(f"  mlx-vlm installation failed.")
        return 1

    # 3. torch (required by vlm_service)
    print(f"  Installing torch...")
    result = subprocess.run(pip_cmd + ["install", "torch"])
    if result.returncode != 0:
        print(f"  torch installation failed.")
        return 1

    # 4. cider — always from GitHub (must compile C++ extension)
    print(f"  Installing cider from GitHub (compiling C++ extension)...")
    result = subprocess.run(pip_cmd + ["install", "--force-reinstall", "--no-deps", "git+https://github.com/Mininglamp-AI/cider.git"])
    if result.returncode != 0:
        print(f"  cider installation failed. Ensure CMake >= 3.27 and Xcode CLI tools are installed.")
        return 1
    print(f"  cider: installed")

    # Set python-path to the persistent venv
    from visual.config.user_config import set_config
    set_config("python-path", venv_python)
    set_config("sdk-installed", "true")

    print(f"\nSDK ready. Python path set to: {venv_python}")
    print("Run 'mano-cua check' to verify.")
    return 0
    return 0


def cmd_install_model(args):
    """Download model weights from HuggingFace"""
    import subprocess

    # Model is for local mode only; same Apple-Silicon-only constraint.
    if platform.system() != "Darwin":
        print("Error: install-model is for local mode (macOS Apple Silicon only).")
        print("On Windows / Linux, use cloud mode — no model download needed.")
        return 2

    model_name = args.name or "Mininglamp-2718/Mano-CUA-4B-Thinking-1.1-MLX-8bit"
    model_dir = os.path.expanduser("~/.mano/models/Mano-CUA-4B-Thinking-1.1-MLX-8bit")

    print(f"Downloading model: {model_name}\n")
    print("Option 1: Download from webpage")
    print(f"  https://huggingface.co/{model_name}")
    print(f"  Download all files, then:")
    print(f"  mano-cua config --set default-model-path /path/to/model\n")
    print("Option 2: Download via CLI (requires HuggingFace token)")
    print("  1. Create a token at https://huggingface.co/settings/tokens ")
    print("  2. Run: hf auth login")
    print(f"  3. Downloading now...\n")

    result = subprocess.run(
        ["hf", "download", model_name, "--local-dir", model_dir]
    )
    if result.returncode != 0:
        print(f"\nDownload failed. Make sure you are logged in:")
        print(f"  hf auth login")
        print(f"  Then run: mano-cua install-model")
        print(f"\nOr download manually and set path:")
        print(f"  mano-cua config --set default-model-path /path/to/model")
        return 1

    model_path = model_dir

    from visual.config.user_config import set_config
    set_config("default-model-path", model_path)
    set_config("model-installed", "true")
    print(f"\nModel ready: {model_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="VLA Desktop Automation Client")
    subparsers = parser.add_subparsers(dest="command")

    # --- run ---
    run_parser = subparsers.add_parser("run", help="Run an automation task")
    run_parser.add_argument("task", help="Task description")
    run_parser.add_argument("--expected-result", help="Expected result description for validation", default=None)
    run_parser.add_argument("--minimize", help="Start with minimized UI panel", action="store_true", default=False)
    run_parser.add_argument("--max-steps", help="Maximum number of steps", type=int, default=100)
    run_parser.add_argument("--local", help="Use local model inference (MLX)", action="store_true", default=False)
    run_parser.add_argument("--model-path", help="Local model weights path (overrides config)", default=None)
    run_parser.add_argument("--url", help="Open URL in browser before starting task", default=None)
    run_parser.add_argument("--app", help="Open app before starting task (use macOS app name, e.g. 'Notes', 'Safari', 'Google Chrome')", default=None)

    # --- stop ---
    subparsers.add_parser("stop", help="Stop the current running task")

    # --- config ---
    config_parser = subparsers.add_parser("config", help="Manage persistent config")
    config_parser.add_argument("--list", dest="config_list", action="store_true", help="List all config values")
    config_parser.add_argument("--get", metavar="KEY", help="Get a config value")
    config_parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a config value")

    # --- check ---
    subparsers.add_parser("check", help="Check local mode dependencies")

    # --- install-sdk ---
    subparsers.add_parser("install-sdk", help="Install local inference SDK (mlx-vlm + cider)")

    # --- install-model ---
    install_parser = subparsers.add_parser("install-model", help="Download model from HuggingFace")
    install_parser.add_argument("name", nargs="?", help="Model name (default: Mininglamp-2718/Mano-CUA-4B-Thinking-1.1-MLX-8bit)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "stop":
        # Write stop flag (picked up by local task loop between steps)
        flag = os.path.expanduser("~/.mano/stop.flag")
        os.makedirs(os.path.dirname(flag), exist_ok=True)
        open(flag, "w").close()
        print("Stop signal sent. Local task will stop after current step completes.")
        # Also attempt cloud session stop
        ret = stop_session()
        return ret

    if args.command == "config":
        return cmd_config(args)

    if args.command == "check":
        return cmd_check(args)

    if args.command == "install-sdk":
        return cmd_install_sdk(args)

    if args.command == "install-model":
        return cmd_install_model(args)

    if args.command == "run":
        if not args.task:
            print("Error: task is required for 'run' command")
            return 1
        return run_task(
            args.task,
            expected_result=args.expected_result,
            minimize=args.minimize,
            max_steps=args.max_steps,
            local=args.local,
            model_path=args.model_path,
            url=args.url,
            app=args.app,
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())
