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

import sys
import platform
import argparse
import subprocess
import time
import requests


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


def _open_app(app_name: str):
    """Open an application (cross-platform)."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
        elif system == "Windows":
            subprocess.run(
                ["powershell", "-Command", f'Start-Process "{app_name}"'],
                shell=False, capture_output=True, text=True, timeout=10
            )
        else:
            subprocess.Popen([app_name])
        time.sleep(2)
    except Exception as e:
        print(f"Warning: failed to open app: {e}")


def run_task(task: str, expected_result: str = None, minimize: bool = False,
             max_steps: int = None, local: bool = False, model_path: str = None,
             url: str = None, app: str = None):
    """Run an automation task"""
    from visual.config.visual_config import BASE_URL, AUTOMATION_CONFIG, API_HEADERS
    from visual.computer.computer_use_util import get_or_create_device_id

    # Open app/URL before starting (both modes)
    if app:
        _open_app(app)
    if url:
        _open_url_in_browser(url)

    if local:
        # --- Local mode ---
        try:
            from visual.agents.local import LocalAgent
        except ImportError as e:
            print(f"Error: Local mode dependencies not installed: {e}")
            print("Install with: pip install mlx-vlm Pillow")
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
                "platform": platform.system()
            }
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
        return 0

    print("Usage: mano-cua config [--list | --get KEY | --set KEY VALUE]")
    return 1


def cmd_check(args):
    """Check local mode dependencies"""
    ok = True

    # 1. Check mlx-vlm
    try:
        import mlx_vlm
        print(f"  mlx-vlm: OK ({mlx_vlm.__version__ if hasattr(mlx_vlm, '__version__') else 'installed'})")
    except ImportError:
        print("  mlx-vlm: MISSING — pip install mlx-vlm")
        ok = False

    # 2. Check vlm_service (inference engine from cider)
    try:
        from vlm_service import custom_generate
        print(f"  vlm_service: OK")
    except ImportError:
        print("  vlm_service: MISSING — pip install git+https://github.com/Mininglamp-AI/cider.git")
        ok = False

    # 3. Check cider W8A8
    try:
        from cider import is_available
        if is_available():
            print("  W8A8: available (M5+)")
        else:
            print("  W8A8: not available (requires M5+, will use standard inference)")
    except Exception:
        print("  W8A8: unknown")

    # 4. Check model path
    from visual.config.user_config import get_config
    model_path = get_config("default-model-path")
    if model_path:
        import os
        expanded = os.path.expanduser(model_path)
        if os.path.isdir(expanded):
            print(f"  model: OK ({expanded})")
        else:
            print(f"  model: path not found ({expanded})")
            ok = False
    else:
        print("  model: not configured — mano-cua config --set default-model-path ~/path/to/model")
        ok = False

    if ok:
        print("\nLocal mode is ready.")
    else:
        print("\nSome dependencies are missing. Fix the items above.")
    return 0 if ok else 1


def cmd_install_sdk(args):
    """Install local inference SDK (mlx-vlm + cider) into the current environment."""
    import subprocess

    pip_cmd = [sys.executable, "-m", "pip"]

    packages = [
        ("mlx_vlm", "mlx-vlm"),
        ("cider", "git+https://github.com/Mininglamp-AI/cider.git"),
    ]

    for module_name, install_spec in packages:
        try:
            __import__(module_name)
            label = install_spec.split("/")[-1].replace(".git", "") if "/" in install_spec else install_spec
            print(f"  {label}: already installed")
            continue
        except ImportError:
            pass

        print(f"  Installing {install_spec}...")
        result = subprocess.run(pip_cmd + ["install", install_spec])
        if result.returncode != 0:
            print(f"  Installation failed.")
            return 1
        print(f"  Installed.")

    print("\nSDK ready. Run 'mano-cua check' to verify.")
    return 0


def cmd_install_model(args):
    """Download model weights from HuggingFace"""
    model_name = args.name or "Mininglamp-2718/Mano-P"
    print(f"Downloading model: {model_name}")
    try:
        from huggingface_hub import snapshot_download
        path = snapshot_download(model_name)
        print(f"Model downloaded to: {path}")
        print(f"Set as default: mano-cua config --set default-model-path {path}")
        return 0
    except ImportError:
        print("Error: huggingface_hub not installed. pip install huggingface_hub")
        return 1
    except Exception as e:
        print(f"Download failed: {e}")
        return 1


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
    install_parser.add_argument("name", nargs="?", help="Model name (default: Mininglamp-2718/Mano-P)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "stop":
        return stop_session()

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
