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


def run_task(task: str, expected_result: str = None, minimize: bool = False, max_steps: int = None):
    """Run an automation task"""
    from visual.config.visual_config import BASE_URL, AUTOMATION_CONFIG, API_HEADERS
    from visual.computer.computer_use_util import get_or_create_device_id
    
    # 1. Try to create session BEFORE initializing UI
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
    
    # 3. Session created successfully, now initialize UI
    from visual.view_model.task_view_model import TaskViewModel
    
    view_model = TaskViewModel()

    # Start minimized if requested
    if minimize and view_model.view and view_model.view._ui_initialized:
        view_model.view.root.after(200, view_model.view._toggle_minimize)

    # Initialize task with existing session_id
    if not view_model.init_task(task, BASE_URL, expected_result=expected_result, session_id=session_id, max_steps=max_steps):
        print("Failed to initialize visualization overlay.")
        # Run task directly without UI
        view_model.model.init_task(task, BASE_URL, expected_result=expected_result, session_id=session_id, max_steps=max_steps)
        view_model.model.run_automation_task()
        return 0 if view_model.model.state.status == "completed" else 1

    # Run task
    success = view_model.run_task()
    # Clean up resources
    view_model.close()
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description="VLA Desktop Automation Client")
    parser.add_argument("command", choices=["run", "stop"], help="Command to execute")
    parser.add_argument("task", nargs="?", help="Task description (required for 'run')")
    parser.add_argument("--expected-result", help="Expected result description for validation", default=None)
    parser.add_argument("--minimize", help="Start with minimized UI panel", action="store_true", default=False)
    parser.add_argument("--max-steps", help="Maximum number of steps before auto-closing", type=int, default=100)

    args = parser.parse_args()

    if args.command == "stop":
        return stop_session()

    if args.command == "run":
        if not args.task:
            print("Error: task is required for 'run' command")
            return 1
        return run_task(args.task, args.expected_result, minimize=args.minimize, max_steps=args.max_steps)

    return 1


if __name__ == "__main__":
    sys.exit(main())
