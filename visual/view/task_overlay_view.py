from typing import Optional
import traceback

import customtkinter as ctk
from visual.config.visual_config import WINDOW_CONFIG, ANIMATION_CONFIG, TEXT_CONSTANTS, TASK_STATUS

# Pre-initialize CustomTkinter (global level, ensure UI rendering foundation)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class TaskOverlayView:
    """View layer: pure UI display, receive data through binding, trigger operations through commands"""

    def __init__(self):
        # Initialization flag: prevent duplicate creation
        self._ui_initialized = False

        # UI widget initialization
        self.root = None
        self._blink = True
        self._blink_job = None
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Command binding (set by ViewModel)
        self.on_stop_command = None
        self.on_close_command = None
        self.on_continue_command = None  # New: agree and continue command

        # Button container (core addition: for managing button layout)
        self.button_frame = None
        # Agree and continue button (new)
        self.continue_button = None

        # Delayed UI initialization (avoid blocking in constructor)
        self._safe_init_ui()

    # ========== Safe UI Initialization (Core Fix) ==========
    def _safe_init_ui(self):
        """Safely initialize UI with complete exception handling"""
        try:
            # 1. Initialize main window
            self.root = ctk.CTk()
            self.root.withdraw()  # Hide first, show after initialization

            # 2. Execute UI configuration process
            self._configure_window()
            self._setup_ui()
            self._setup_dragging()
            self._setup_window_close()

            # 3. Mark initialization complete
            self._ui_initialized = True
            print("UI panel initialized successfully")

        except Exception as e:
            print(f"UI panel initializaition failed: {e}")
            traceback.print_exc()
            self._ui_initialized = False

    # ========== Basic UI Configuration ==========
    def _configure_window(self):
        if not self.root:
            return

        self.root.title(TEXT_CONSTANTS["WINDOW_TITLE"])
        # Key fix: first disable borderless, enable after initialization (avoid invisible window)
        self.root.overrideredirect(False)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", WINDOW_CONFIG["ALPHA"])
        self.root.configure(fg_color=WINDOW_CONFIG["BG_COLOR"])
        self.root.geometry(f"{WINDOW_CONFIG['WIDTH']}x{WINDOW_CONFIG['MIN_HEIGHT']}")

        # Force refresh window properties
        self.root.update_idletasks()
        self._position_top_right()

        # Enable borderless after initialization
        self.root.after(100, lambda: self.root.overrideredirect(True))

    def _position_top_right(self):
        if not self.root:
            return

        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            # Boundary check: prevent window from going off screen
            x = max(WINDOW_CONFIG["MARGIN"], screen_width - WINDOW_CONFIG["WIDTH"] - WINDOW_CONFIG["MARGIN"])
            y = max(WINDOW_CONFIG["MARGIN"], WINDOW_CONFIG["MARGIN"])
            self.root.geometry(f"{WINDOW_CONFIG['WIDTH']}x{WINDOW_CONFIG['MIN_HEIGHT']}+{x}+{y}")
        except Exception as e:
            print(f"Window positioning failed: {e}")
            # Fallback position: screen center
            self.root.geometry(f"{WINDOW_CONFIG['WIDTH']}x{WINDOW_CONFIG['MIN_HEIGHT']}+200+200")

    def _setup_window_close(self):
        """Set window close callback"""
        if not self.root:
            return

        def close():
            if self.on_close_command:
                self.on_close_command()

        self.root.protocol("WM_DELETE_WINDOW", close)

    # ========== UI Widget Creation (Core Change: Button Layout Refactor) ==========
    def _setup_ui(self):
        if not self.root:
            return

        # Main container
        main_frame = ctk.CTkFrame(
            self.root,
            fg_color=WINDOW_CONFIG["BG_COLOR"],
            corner_radius=WINDOW_CONFIG["CORNER_RADIUS"]
        )
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Top bar (status + step)
        top_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_frame.pack(fill="x", padx=14, pady=(12, 0))

        # Status label (Running/Done/Stopped/Error)
        self.status_label = ctk.CTkLabel(
            top_frame,
            text=f"{TEXT_CONSTANTS['RUNNING_TEXT']}…",
            font=ctk.CTkFont(size=WINDOW_CONFIG["TITLE_FONT_SIZE"]),
            text_color=WINDOW_CONFIG["TEXT_COLOR"]
        )
        self.status_label.pack(side="left")

        # Step label
        self.step_label = ctk.CTkLabel(
            top_frame,
            text=f"{TEXT_CONSTANTS['STEP_PREFIX']}0",
            font=ctk.CTkFont(size=WINDOW_CONFIG["TITLE_FONT_SIZE"]),
            text_color=WINDOW_CONFIG["TEXT_COLOR"]
        )
        self.step_label.pack(side="right")

        # Task name label
        self.task_name_label = ctk.CTkLabel(
            main_frame,
            text=f"{TEXT_CONSTANTS['TASK_PREFIX']}",
            font=ctk.CTkFont(size=WINDOW_CONFIG["TITLE_FONT_SIZE"]),
            text_color=WINDOW_CONFIG["TEXT_COLOR"],
            wraplength=280,
            justify="left"
        )
        self.task_name_label.pack(fill="x", padx=14, pady=(8, 0), anchor="w")

        # Log text box
        self.log_text = ctk.CTkTextbox(
            main_frame,
            height=100,
            font=ctk.CTkFont(size=WINDOW_CONFIG["LOG_FONT_SIZE"]),
            fg_color=WINDOW_CONFIG["LOG_BG_COLOR"],
            text_color=WINDOW_CONFIG["TEXT_COLOR"],
            corner_radius=WINDOW_CONFIG["BUTTON_RADIUS"],
            wrap="word"
        )
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(8, 0))
        self.log_text.configure(state="disabled")

        # ========== Core Change: Refactor Button Layout ==========
        # Create button container (for implementing two buttons with equal width)
        self.button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.button_frame.pack(fill="x", padx=14, pady=(8, 12))
        # Set button container weights for equal width distribution
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=1)

        # Stop button (default display, occupies first column)
        self.stop_button = ctk.CTkButton(
            self.button_frame,
            text=TEXT_CONSTANTS["STOP_BUTTON_TEXT"],
            font=ctk.CTkFont(size=WINDOW_CONFIG["TITLE_FONT_SIZE"]),
            fg_color=WINDOW_CONFIG["STOP_BTN_COLOR"],
            hover_color=WINDOW_CONFIG["STOP_BTN_HOVER"],
            corner_radius=WINDOW_CONFIG["BUTTON_RADIUS"],
            height=WINDOW_CONFIG["BUTTON_HEIGHT"],
            command=self._on_stop_clicked
        )
        # By default, stop button occupies entire button container
        self.stop_button.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

        # Agree and continue button (initially hidden, occupies second column)
        self.continue_button = ctk.CTkButton(
            self.button_frame,
            text="Proceed",
            font=ctk.CTkFont(size=WINDOW_CONFIG["TITLE_FONT_SIZE"]),
            fg_color="#2ecc71",  # Green theme
            hover_color="#27ae60",
            corner_radius=WINDOW_CONFIG["BUTTON_RADIUS"],
            height=WINDOW_CONFIG["BUTTON_HEIGHT"],
            command=self._on_continue_clicked,
            state="hidden"  # Initially hidden
        )

        # Safely execute adaptive height (with delay + exception handling)
        self.root.after(ANIMATION_CONFIG["HEIGHT_ADJUST_DELAY"], self._safe_adjust_window_height)

    # ========== New: Agree and Continue Button Click Event ==========
    def _on_continue_clicked(self):
        """Agree and continue button click: forward command to ViewModel"""
        if self.on_continue_command:
            try:
                self.on_continue_command()
            except Exception as e:
                print(f"Failed to execute continue command: {e}")

    def _setup_dragging(self):
        """Window dragging functionality"""
        if not self.root:
            return

        def start_drag(event):
            self._drag_start_x = event.x
            self._drag_start_y = event.y

        def do_drag(event):
            try:
                x = self.root.winfo_x() + event.x - self._drag_start_x
                y = self.root.winfo_y() + event.y - self._drag_start_y
                # Boundary check: prevent dragging off screen
                screen_width = self.root.winfo_screenwidth()
                screen_height = self.root.winfo_screenheight()
                x = max(0, min(x, screen_width - WINDOW_CONFIG["WIDTH"]))
                y = max(0, min(y, screen_height - WINDOW_CONFIG["MIN_HEIGHT"]))
                self.root.geometry(f"+{x}+{y}")
            except Exception:
                pass

        # Bind dragging events to title area
        for widget in (self.status_label, self.step_label):
            widget.bind("<Button-1>", start_drag)
            widget.bind("<B1-Motion>", do_drag)

    # ========== UI Events (Forward Commands Only) ==========
    def _on_stop_clicked(self):
        """Stop button click: only forward command to ViewModel"""
        if self.on_stop_command:
            try:
                self.on_stop_command()
            except Exception as e:
                print(f"Failed to execute stop command: {e}")

    # ========== UI Update Methods (Called by ViewModel) ==========
    def update_task_state(self, task_state):
        """Update entire task state (core binding method)"""
        if not self._ui_initialized or not self.root:
            return

        try:
            # Update task name
            self.task_name_label.configure(text=f"{TEXT_CONSTANTS['TASK_PREFIX']}{task_state.task_name}")

            # Update step
            self.step_label.configure(text=f"{TEXT_CONSTANTS['STEP_PREFIX']}{task_state.progress.step_idx}")

            # Update log
            self._update_log_text(task_state.progress.action, task_state.progress.reasoning)

            # Update status and button
            self._update_status_ui(task_state.status, task_state.error_msg)

            # Adaptive height
            self.root.after(ANIMATION_CONFIG["HEIGHT_ADJUST_DELAY"], self._safe_adjust_window_height)
        except Exception as e:
            print(f"Failed to update task state: {e}")

    def _update_log_text(self, action: str, reasoning: str = ""):
        """Update log text"""
        if not self._ui_initialized:
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        if action:
            log_text = f"{TEXT_CONSTANTS['ACTION_PREFIX']}{action}"
            if reasoning.strip():
                log_text += f"\n{TEXT_CONSTANTS['REASONING_PREFIX']}{reasoning}"
            self.log_text.insert("1.0", log_text)
        self.log_text.configure(state="disabled")

    # ========== Core Change: Update Status UI (New call_user handling) ==========
    def _update_status_ui(self, status: str, error_msg: Optional[str] = None):
        """Update status UI (title + button + animation)"""
        if not self._ui_initialized:
            return

        # Stop blinking animation
        self._stop_blink()

        # Update status text
        if status == TASK_STATUS["RUNNING"]:
            self.status_label.configure(text=f"{TEXT_CONSTANTS['RUNNING_TEXT']}…")
            self._start_blink()
            # Restore to single Stop button
            self._switch_to_single_button()
            self.stop_button.configure(
                text=TEXT_CONSTANTS["STOP_BUTTON_TEXT"],
                state="normal"
            )
        elif status == TASK_STATUS["COMPLETED"]:
            self.status_label.configure(text=TEXT_CONSTANTS["DONE_TEXT"])
            # Restore to single button (close button)
            self._switch_to_single_button()
            self.stop_button.configure(
                text=TEXT_CONSTANTS["CLOSE_BUTTON_TEXT"],
                command=self.on_close_command,
                state="normal"
            )
            # Auto close after 5 seconds
            self.root.after(5000, self._auto_close)
        elif status == TASK_STATUS["STOPPED"]:
            self.status_label.configure(text=TEXT_CONSTANTS["STOPPED_TEXT"])
            # Restore to single button (close button)
            self._switch_to_single_button()
            self.stop_button.configure(
                text=TEXT_CONSTANTS["CLOSE_BUTTON_TEXT"],
                command=self.on_close_command,
                state="normal"
            )
        elif status == TASK_STATUS["ERROR"]:
            self.status_label.configure(text=TEXT_CONSTANTS["ERROR_TEXT"])
            if error_msg:
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.insert("1.0", error_msg)
                self.log_text.configure(state="disabled")
            # Restore to single button (close button)
            self._switch_to_single_button()
            self.stop_button.configure(
                text=TEXT_CONSTANTS["CLOSE_BUTTON_TEXT"],
                command=self.on_close_command,
                state="normal"
            )
        elif status == TASK_STATUS["CALL_USER"]:
            # Core change: show two buttons in call_user state
            self.status_label.configure(text="Pending Confirmation")
            self._switch_to_double_buttons()

    # ========== New: Button Layout Switching Methods ==========
    def _switch_to_single_button(self):
        """Switch to single button layout (default Stop/Close button)"""
        # Hide continue button
        self.continue_button.grid_forget()
        # Stop button occupies entire button container
        self.stop_button.grid_configure(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

    def _switch_to_double_buttons(self):
        """Switch to two button layout (agree and continue + stop)"""
        # Stop button only occupies first column
        self.stop_button.grid_configure(row=0, column=1, columnspan=1, sticky="ew", padx=(2, 0), pady=0)
        # Show continue button (occupies second column)
        self.continue_button.grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=0)
        # Ensure button state is normal
        self.stop_button.configure(state="normal", text=TEXT_CONSTANTS["STOP_BUTTON_TEXT"])
        self.continue_button.configure(state="normal")

    # ========== Animation Control ==========
    def _start_blink(self):
        """Start title blinking"""
        if not self._ui_initialized:
            return

        self._blink = True
        self._blink_job = self.root.after(ANIMATION_CONFIG["BLINK_INTERVAL"], self._blink_title)

    def _stop_blink(self):
        """Stop title blinking"""
        if not self.root or not self._blink_job:
            return

        try:
            self.root.after_cancel(self._blink_job)
            self._blink_job = None
        except Exception:
            pass

    def _blink_title(self):
        """Title blinking animation"""
        if not self._ui_initialized:
            return

        try:
            dots = "…" if self._blink else ""
            self.status_label.configure(text=f"{TEXT_CONSTANTS['RUNNING_TEXT']}{dots}")
            self._blink = not self._blink
            self._blink_job = self.root.after(ANIMATION_CONFIG["BLINK_INTERVAL"], self._blink_title)
        except Exception:
            self._stop_blink()

    # ========== Window Adjustment (Safe Version) ==========
    def _safe_adjust_window_height(self):
        """Safe adaptive window height (core fix)"""
        if not self._ui_initialized or not self.root:
            return

        try:
            self.root.update_idletasks()
            task_label_height = self.task_name_label.winfo_reqheight()

            base_height = 60
            button_height = 52
            log_min_height = 80
            single_line_height = 25
            extra_height = max(0, task_label_height - single_line_height)

            new_height = base_height + task_label_height + log_min_height + button_height + extra_height
            new_height = max(WINDOW_CONFIG["MIN_HEIGHT"], min(new_height, WINDOW_CONFIG["MAX_HEIGHT"]))

            current_height = self.root.winfo_height()
            # Only update when height change exceeds 5px (avoid frequent refresh)
            if abs(new_height - current_height) > 5:
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                self.root.geometry(f"{WINDOW_CONFIG['WIDTH']}x{new_height}+{x}+{y}")
        except Exception as e:
            print(f"Failed to adjust window height: {e}")

    # ========== Window Control (Core Fix) ==========
    def show(self):
        """Show window (ensure correct UI rendering)"""
        if not self._ui_initialized or not self.root:
            print("UI not initialized, cannot show")
            return

        try:
            self.root.deiconify()  # Show window
            self.root.lift()  # Bring to front
            self.root.focus_force()  # Get focus
            self.root.attributes("-topmost", True)
            # Force refresh
            self.root.update()
            # Periodically re-assert topmost
            self._keep_on_top()
            print("UI window displayed")
        except Exception as e:
            print(f"Failed to show window: {e}")
            traceback.print_exc()

    def close(self):
        """Close window"""
        if not self._ui_initialized or not self.root:
            return

        self._ui_initialized = False
        self._stop_blink()

        try:
            self.root.quit()
            self.root.after(100, self.root.destroy)
        except Exception:
            pass
        print("UI window closed")

    def _keep_on_top(self):
        """Periodically re-assert topmost to prevent being covered"""
        if not self._ui_initialized or not self.root:
            return
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(2000, self._keep_on_top)
        except Exception:
            pass

    def _auto_close(self):
        """Auto close window after task completion"""
        if self._ui_initialized and self.on_close_command:
            self.on_close_command()

    def run_mainloop(self):
        """Run UI main loop"""
        if not self._ui_initialized or not self.root:
            raise RuntimeError("UI not initialized, cannot run main loop")

        try:
            self.root.mainloop()
        except Exception as e:
            raise RuntimeError(f"UI main loop exception: {e}") from e