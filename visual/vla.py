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
        # Setting default-model-path: verify model exists
        if args.set[0] == "default-model-path":
            expanded = os.path.expanduser(args.set[1])
            if os.path.isdir(expanded):
                set_config("model-installed", "true")
                print(f"  Model verified. model-installed = true")
            else:
                print(f"  Warning: path not found — {expanded}")
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

    venv_dir = os.path.expanduser("~/.mano/venv")
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

    model_name = args.name or "Mininglamp-2718/Mano-P"
    model_dir = os.path.expanduser("~/.mano/models/Mano-P")

    print(f"Downloading model: {model_name}\n")
    print("Option 1: Download from webpage")
    print(f"  https://huggingface.co/{model_name}/tree/main/w8a16")
    print(f"  Download all files, then:")
    print(f"  mano-cua config --set default-model-path /path/to/w8a16\n")
    print("Option 2: Download via CLI (requires HuggingFace token)")
    print("  1. Create a token at https://huggingface.co/settings/tokens ")
    print("  2. Run: hf auth login")
    print(f"  3. Downloading now...\n")

    result = subprocess.run(
        ["hf", "download", model_name, "--include", "w8a16/*", "--local-dir", model_dir]
    )
    if result.returncode != 0:
        print(f"\nDownload failed. Make sure you are logged in:")
        print(f"  hf auth login")
        print(f"  Then run: mano-cua install-model")
        print(f"\nOr download manually and set path:")
        print(f"  mano-cua config --set default-model-path /path/to/model")
        return 1

    model_path = os.path.join(model_dir, "w8a16")
    if not os.path.isdir(model_path):
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
    install_parser.add_argument("name", nargs="?", help="Model name (default: Mininglamp-2718/Mano-P)")

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
