import platform
import threading
import time
import uuid
from typing import Optional, Callable, Dict, Any, List

import requests

from visual.computer.computer_action_executor import ComputerActionExecutor
from visual.config.visual_config import AUTOMATION_CONFIG, TASK_STATUS
from visual.model.task_progress import TaskProgress
from visual.model.task_state import TaskState
from visual.computer.computer_use_util import screenshot_to_bytes, get_or_create_device_id, \
    make_tool_result


class TaskModel:
    """Automation task core model"""

    def __init__(self):
        # State data
        self.state = TaskState()
        self.stop_event = threading.Event()

        self.pause_event = None

        # Callback functions
        self._on_state_changed: Optional[Callable[[TaskState], None]] = None

        # Business components
        self.executor: Optional[ComputerActionExecutor] = None
        self.server_url = AUTOMATION_CONFIG["BASE_URL"]
        self.expected_result = None
        self.eval_result = None

    # ========== Data Monitoring ==========
    def set_state_changed_callback(self, callback: Callable[[TaskState], None]):
        """Set state change callback"""
        self._on_state_changed = callback

    def _notify_state_changed(self):
        """Notify state change"""
        if self._on_state_changed:
            self._on_state_changed(self.state)

    # ========== Initialization Methods ==========
    def init_task(self, task_name: str, server_url: Optional[str] = None, expected_result: Optional[str] = None, session_id: Optional[str] = None):
        """Initialize automation task"""
        # Basic configuration
        self.state.task_name = task_name
        self.expected_result = expected_result
        self.state.status = TASK_STATUS["RUNNING"]
        self.state.is_running = True
        self.state.error_msg = None
        self.state.step_idx = 0

        # Device and platform information
        self.state.device_id = get_or_create_device_id()
        self.state.platform_tag = platform.system()
        
        # Pre-created session (from vla.py)
        if session_id:
            self.state.session_id = session_id

        # Server URL
        if server_url:
            self.server_url = server_url

        # Initialize executor
        self.executor = ComputerActionExecutor()

        # Reset stop signal
        self.stop_event.clear()

        # Notify state change
        self._notify_state_changed()

    # ========== Progress Update ==========
    def update_progress(self, step_idx: int, action_desc: str, reasoning: str = "", meta: Dict[str, Any] = None):
        """Update task progress"""
        if not self.state.is_running:
            return

        self.state.progress = TaskProgress(
            step_idx=step_idx,
            action=action_desc,
            reasoning=reasoning,
            action_meta=meta or {}
        )
        print(f"[step {step_idx}] Action: {action_desc}")
        if reasoning:
            print(f"[step {step_idx}] Reasoning: {reasoning}")
        self._notify_state_changed()

    # ========== State Management ==========
    def mark_completed(self):
        """Mark task as completed"""
        self.state.status = TASK_STATUS["COMPLETED"]
        self.state.is_running = False
        self.stop_event.set()
        self._print_summary("COMPLETED")
        self._notify_state_changed()

    def mark_stopped(self):
        """Mark task as stopped"""
        self.state.status = TASK_STATUS["STOPPED"]
        self.state.is_running = False
        self.stop_event.set()
        # Immediately tell server to stop, don't wait for step loop to finish
        self._stop_device_session()
        self._print_summary("STOPPED_BY_USER")
        self._notify_state_changed()

    def _stop_device_session(self):
        """Tell server to stop the active session for this device immediately"""
        try:
            requests.post(
                f"{self.server_url}/v1/devices/{self.state.device_id}/stop",
                json={},
                timeout=5
            )
        except Exception:
            pass  # Best effort

    def mark_error(self, error_msg: str):
        """Mark task as error"""
        self.state.status = TASK_STATUS["ERROR"]
        self.state.error_msg = error_msg
        self.state.is_running = False
        self.stop_event.set()
        self._print_summary("ERROR", error_msg)
        self._notify_state_changed()

    def _print_summary(self, final_status: str, error_msg: str = ""):
        """Print task summary to stdout for agent consumption"""
        import json
        print(f"\n{'='*50}")
        print(f"Task: {self.state.task_name}")
        print(f"Status: {final_status}")
        print(f"Total steps: {self.state.progress.step_idx}")
        if self.state.progress.action:
            print(f"Last action: {self.state.progress.action}")
        if self.state.progress.reasoning:
            print(f"Last reasoning: {self.state.progress.reasoning}\n")
        if error_msg:
            print(f"Error: {error_msg}")
        if self.eval_result:
            print(f"Evaluation result: {json.dumps(self.eval_result, indent=2, ensure_ascii=False)}")
        print(f"{'='*50}\n")

    def _mark_evaluating(self):
        """Mark task as evaluating - only changes status label, keeps log text"""
        self.state.status = TASK_STATUS["EVALUATING"]
        print("Evaluating task result...")
        self._notify_state_changed()

    def mark_call_user(self):
        """Mark task requires user intervention"""
        self.state.status = TASK_STATUS["CALL_USER"]
        self._notify_state_changed()
        self.pause_task()
        self.pause_event.wait()
        self.state.status = TASK_STATUS["RUNNING"]

    # ========== Current Thread Calls: Control Task Thread ==========

    def stop_task(self):
        """Stop task"""
        if self.state.is_running:
            self.mark_stopped()

    def pause_task(self):
        """Current thread call: pause task (reversible)"""
        if self.state.is_running and not self.stop_event.is_set():
            self.pause_event = threading.Event()
            self.pause_event.clear()  # Set pause signal
            self._notify_state_changed()
            print(f"[Current thread-{threading.current_thread().name}] Send pause signal")

    def resume_task(self):
        """Current thread call: resume task"""
        self.pause_event.set()  # Clear pause signal
        self._notify_state_changed()
        print(f"[Current thread-{threading.current_thread().name}] Send resume signal")

    # ========== Core Business Logic: Run Automation Task ==========
    def run_automation_task(self):
        """Run complete automation task"""
        if not self.state.is_running:
            return

        print(f"Expected result: {self.expected_result}")

        try:
            # 1. Create session (skip if already created by vla.py)
            if not self.state.session_id:
                self._create_session()

            if not self.state.session_id:
                raise RuntimeError("Failed to create session, session_id not obtained")
            
            self.update_progress(0, "Initializing", "Initializing session connection")

            # 2. Execute task step loop
            self._execute_task_steps()

            # 3. Normal completion
            if self.state.is_running and self.state.status != TASK_STATUS["ERROR"]:
                if self.expected_result:
                    self._mark_evaluating()
                    self._close_session()
                    self.mark_completed()
                else:
                    self.mark_completed()
                    self._close_session()
                return

        except Exception as e:
            self.mark_error(f"Task execution failed: {str(e)}")
        # Close session for error/stopped cases (skip eval)
        self._close_session(skip_eval=True)

    def _create_session(self):
        """Create server session"""
        try:
            body = {
                "device_id": self.state.device_id,
                "platform": self.state.platform_tag,
                "task": self.state.task_name
            }
            if self.expected_result:
                body["expected_result"] = self.expected_result
            resp = requests.post(
                f"{self.server_url}/v1/sessions",
                json=body,
                timeout=AUTOMATION_CONFIG["SESSION_TIMEOUT"]
            )
            if resp.status_code == 409:
                raise RuntimeError("Another task is already running on this device. Use 'mano-cua stop' to stop it first.")

            resp.raise_for_status()
            data = resp.json()

            self.state.session_id = data["session_id"]
            print(f"Session created: {self.state.session_id}")

        except Exception as e:
            raise RuntimeError(f"Failed to create session: {e}")

    def _execute_task_steps(self):
        """Execute task step loop"""
        tool_results: List[Dict[str, Any]] = []
        step_idx = 0

        while self.state.is_running and not self.stop_event.is_set():
            # 1. Check stop signal
            if self.stop_event.is_set():
                self.mark_stopped()
                break

            # 2. Build request payload (screenshots flow through tool_results only)
            payload = {
                "request_id": str(uuid.uuid4()),
                "tool_results": tool_results,
            }

            # 4. Request next operation
            try:
                resp = requests.post(
                    f"{self.server_url}/v1/sessions/{self.state.session_id}/step",
                    json=payload,
                    timeout=AUTOMATION_CONFIG["STEP_TIMEOUT"]
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"Request step failed: {e}")

            # 5. Parse response data
            reasoning = data.get("reasoning", "")
            actions = data.get("actions", [])
            status = (data.get("status") or "RUNNING").upper()
            action_desc = data.get("action_desc", "")

            # 6. Handle stop status
            if status == "STOP":
                self.mark_stopped()
                break

            # 7. Update UI progress
            self.update_progress(step_idx, action_desc, reasoning)

            # 8. Handle terminal status
            if status == "DONE":
                break
            elif status == "FAIL":
                self.mark_error("Server marked task as failed")
                break
            elif status == "CALL_USER":
                self.mark_call_user()
                continue

            # 9. Execute actions
            tool_results = []
            if not actions:
                continue

            for i, a in enumerate(actions):
                tool_use_id = a.get("id")

                if not tool_use_id:
                    continue

                # Execute single action
                result = self.executor.run_one(a)

                # Delay after action
                time.sleep(AUTOMATION_CONFIG["ACTION_DELAY"])

                # Build tool result
                include_screenshot = (i == len(actions) - 1)
                after_shot = screenshot_to_bytes() if include_screenshot else None

                tool_results.append(
                    make_tool_result(
                        tool_use_id=tool_use_id,
                        ok=bool(result["ok"]),
                        message=result["message"],
                        include_screenshot=include_screenshot,
                        screenshot_bytes=after_shot,
                        meta=result.get("meta"),
                    )
                )

            step_idx += 1

    def _close_session(self, skip_eval: bool = False):
        """Close server session"""
        if not self.state.session_id:
            return

        try:
            resp = requests.post(
                f"{self.server_url}/v1/sessions/{self.state.session_id}/close?skip_eval={str(skip_eval).lower()}",
                json={},
                timeout=AUTOMATION_CONFIG["CLOSE_SESSION_TIMEOUT"]
            )
            resp.raise_for_status()
            data = resp.json()
            self.eval_result = data.get("eval_result")
        except Exception as e:
            print(f"Failed to close session: {e}")