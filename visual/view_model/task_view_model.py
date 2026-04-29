import threading
from typing import Optional

from visual.agents.base import BaseAgent
from visual.config.visual_config import ANIMATION_CONFIG, TASK_STATUS, AUTOMATION_CONFIG
from visual.model.task_model import TaskModel
from visual.view.task_overlay_view import TaskOverlayView


class TaskViewModel:
    """ViewModel layer: connects Model and View"""

    def __init__(self):
        # Initialize Model and View
        self.model = TaskModel()
        self.view = TaskOverlayView()

        # Bind View commands to ViewModel
        self.view.on_stop_command = self.on_stop_command
        self.view.on_close_command = self.on_close_command
        self.view.on_continue_command = self.on_continue_command  # Bind agree and continue command

        # Bind Model state changes to View updates
        self.model.set_state_changed_callback(self.on_model_state_changed)

        # Background thread reference
        self._task_thread = None
        self._is_running = False

    # ========== Model State Change Callback ==========
    def on_model_state_changed(self, task_state):
        """Update View when Model state changes"""
        self.view.root.after(0, lambda: self.view.update_task_state(task_state))

    # ========== View Command Handling ==========
    def on_stop_command(self):
        """Handle stop command"""
        if self._is_running:
            self.view.root.after(0, lambda: self.view.stop_button.configure(
                text="Stopping…",
                state="disabled"
            ))
            self.view.root.after(ANIMATION_CONFIG["STOP_DELAY"], self.model.stop_task)

    def on_close_command(self):
        """Handle close command"""
        self._is_running = False
        self.model.stop_task()
        self.view.close()

    # ========== Core Change: Ensure API call succeeds before resuming thread ==========
    def on_continue_command(self):
        """Handle user click 'agree and continue' — delegates to agent"""
        if not self._is_running:
            print("Task not running, cannot continue")
            self.view.root.after(0, lambda: self.view.continue_button.configure(
                text="Agree and Continue", state="normal"
            ))
            return

        agent = self.model.agent
        if not agent:
            self._handle_continue_error("No agent available")
            return

        def call_agree():
            try:
                self.view.root.after(0, lambda: [
                    self.view.continue_button.configure(text="Submitting confirmation...", state="disabled"),
                    self.view.stop_button.configure(state="disabled"),
                ])

                agent.agree_to_continue()

                self.model.resume_task()
                self.model.state.status = TASK_STATUS["RUNNING"]
                self.model.state.is_running = True
                self.on_model_state_changed(self.model.state)

                self.view.root.after(0, lambda: [
                    self.view.status_label.configure(text="Resuming..."),
                    self.view.stop_button.configure(state="normal"),
                ])

            except Exception as e:
                self._handle_continue_error(f"Continue command failed: {e}")

        threading.Thread(target=call_agree, daemon=True).start()

    # ========== New: Unified Error Handling Method ==========
    def _handle_continue_error(self, error_msg):
        """Unified handling of agree and continue error scenarios"""
        self.view.root.after(0, lambda: [
            self.view.continue_button.configure(text="Agree and Continue", state="normal"),
            self.view.stop_button.configure(state="normal"),
            self.view.log_text.insert("1.0", f"❌ {error_msg}\n{self.view.log_text.get('1.0', 'end')}"),
            self.view.status_label.configure(text="Confirmation failed")
        ])

    # ========== Thread Polling Wrapper (Reusable Logic) ==========
    def _start_thread_polling(self):
        """Start thread state polling (extracted for reuse)"""

        def poll_thread():
            if self._task_thread and self._task_thread.is_alive():
                self.view.root.after(ANIMATION_CONFIG["POLL_INTERVAL"], poll_thread)
                return

            # Handle state after thread ends
            if self.model.state.status in (TASK_STATUS["COMPLETED"], TASK_STATUS["ERROR"], TASK_STATUS["STOPPED"], TASK_STATUS["MAX_STEP_REACHED"]):
                self.on_model_state_changed(self.model.state)
            elif self.model.stop_event.is_set():
                self.model.mark_stopped()

        self.view.root.after(ANIMATION_CONFIG["POLL_INTERVAL"], poll_thread)

    # ========== Business Methods ==========
    def init_task(self, task_name: str, agent: BaseAgent, expected_result: Optional[str] = None, max_steps: int = None) -> bool:
        """Initialize automation task"""
        try:
            import customtkinter as ctk
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")

            # Wire minimize callback from model to view (only minimize, never expand)
            def _minimize_if_needed():
                if not self.view._minimized:
                    self.view._toggle_minimize()
            self.model.on_minimize_panel = lambda: self.view.root.after(0, _minimize_if_needed)

            # Initialize Model
            self.model.init_task(task_name, agent, expected_result=expected_result, max_steps=max_steps)

            # Initialize View
            self.view.show()
            self._is_running = True
            return True
        except ImportError:
            print("CustomTkinter not installed, skipping visualization")
            return False
        except Exception as e:
            print(f"Failed to initialize task: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_task(self):
        """Run automation task"""
        if not self._is_running:
            return False

        # Start Model's automation task
        def worker():
            self.model.run_automation_task()

        self._task_thread = threading.Thread(target=worker, daemon=True)
        self._task_thread.start()

        # Start thread polling (using wrapped method)
        self._start_thread_polling()

        # Run UI main loop
        try:
            self.view.run_mainloop()
        except Exception as e:
            print(f"UI runtime exception: {e}")
            self._is_running = False
            self.model.mark_error(str(e))
        finally:
            if self._task_thread and self._task_thread.is_alive():
                self._task_thread.join(timeout=2)

        return self.model.state.status == TASK_STATUS["COMPLETED"]

    def close(self):
        """Close ViewModel"""
        self.on_close_command()