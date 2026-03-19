import threading
from typing import Optional
import requests  # New: import requests library for API calls

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
        """Handle user click 'agree and continue' business logic (call go_no API)"""
        # Quick failure: task not running, return directly
        if not self._is_running:
            print("❌ Task not running, cannot continue")
            self.view.root.after(0, lambda: self.view.continue_button.configure(
                text="Agree and Continue", state="normal"
            ))
            return

        # 1. Validate required parameters
        session_id = self.model.state.session_id
        if not session_id:
            error_msg = "Session ID not obtained, cannot continue task"
            print(f"❌ {error_msg}")
            self.view.root.after(0, lambda: [
                self.view.continue_button.configure(text="Agree and Continue", state="normal"),
                self.view.log_text.insert("1.0", f"❌ Error: {error_msg}\n{self.view.log_text.get('1.0', 'end')}")
            ])
            return

        # Define core logic for API call (extracted as internal function for exception handling)
        def call_go_no_api():
            try:
                # 2. Update UI button state (prevent duplicate clicks)
                self.view.root.after(0, lambda: [
                    self.view.continue_button.configure(text="Submitting confirmation...", state="disabled"),
                    self.view.stop_button.configure(state="disabled"),
                    self.view.log_text.insert(
                        "1.0",
                        f"🔄 Submitting user confirmation, session ID: {session_id}\n{self.view.log_text.get('1.0', 'end')}"
                    )
                ])

                # 3. [First step] Call go_no API (prioritize ensuring server state update)
                server_url = self.model.server_url or AUTOMATION_CONFIG["BASE_URL"]
                api_url = f"{server_url}/v1/sessions/{session_id}/go_no"

                # Configure request timeout and retry (enhance robustness)
                response = requests.post(
                    api_url,
                    timeout=AUTOMATION_CONFIG["SESSION_TIMEOUT"],
                    headers={"Content-Type": "application/json"}  # Explicitly specify Content-Type
                )
                response.raise_for_status()  # Throw HTTP exceptions (4xx/5xx)

                # 4. 【第二步】解析并校验接口响应（确认服务端处理成功）
                resp_data = response.json() if response.content else {"ok": True}
                if not resp_data.get("ok"):
                    raise RuntimeError(f"接口返回失败：{resp_data.get('detail', '未知错误')}")

                print(f"✅ API调用成功，服务端会话 {session_id} 已更新为RUNNING状态")

                # 5. 【第三步】仅当API调用完全成功后，再恢复客户端线程
                self.model.resume_task()  # 清空stop_event，唤醒阻塞的任务线程

                # 6. 同步Model状态（确保客户端与服务端状态一致）
                self.model.state.status = TASK_STATUS["RUNNING"]
                self.model.state.is_running = True

                # 7. 通知View更新状态（切换回单按钮布局）
                self.on_model_state_changed(self.model.state)

                # 8. 更新UI日志和状态
                self.view.root.after(0, lambda: [
                    self.view.log_text.insert(
                        "1.0",
                        f"✅ 用户确认成功，会话 {session_id} 已恢复运行\n{self.view.log_text.get('1.0', 'end')}"
                    ),
                    self.view.status_label.configure(text="继续执行中..."),
                    # 恢复停止按钮状态（继续按钮由View自动切换）
                    self.view.stop_button.configure(state="normal")
                ])

                print(f"✅ 客户端线程已恢复，会话 {session_id} 继续执行后续步骤")

            except requests.exceptions.RequestException as e:
                # 网络/接口异常：不恢复线程，直接提示错误
                error_msg = f"调用go_no接口失败：{str(e)}"
                print(f"❌ {error_msg} → 不恢复客户端线程")
                self._handle_continue_error(error_msg)

            except Exception as e:
                # 通用异常：不恢复线程，直接提示错误
                error_msg = f"处理继续命令失败：{str(e)}"
                print(f"❌ {error_msg} → 不恢复客户端线程")
                import traceback
                traceback.print_exc()
                self._handle_continue_error(error_msg)

        # Start API call (asynchronous execution, avoid blocking UI thread)
        threading.Thread(target=call_go_no_api, daemon=True).start()

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
            if self.model.state.status in (TASK_STATUS["COMPLETED"], TASK_STATUS["ERROR"], TASK_STATUS["STOPPED"]):
                self.on_model_state_changed(self.model.state)
            elif self.model.stop_event.is_set():
                self.model.mark_stopped()

        self.view.root.after(ANIMATION_CONFIG["POLL_INTERVAL"], poll_thread)

    # ========== Business Methods ==========
    def init_task(self, task_name: str, server_url: Optional[str] = None) -> bool:
        """Initialize automation task"""
        try:
            import customtkinter as ctk
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")

            # Initialize Model
            self.model.init_task(task_name, server_url)

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