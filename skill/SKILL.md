---
name: mano-cua
description: Computer use for GUI automation tasks via VLA models. Use when the user describes a task in natural language that requires visual screen interaction and no API or CLI exists for the target app.
homepage: https://github.com/Mininglamp-AI/mano-skill
metadata: {"openclaw": {"emoji": "🖥️", "install": [{"id": "brew", "kind": "brew", "formula":"Mininglamp-AI/tap/mano-cua", "bins":["mano-cua"],"label": "Install mano-cua (brew)"}]}}
---

# mano-cua

Desktop GUI automation for tasks via VLA models. Use when the user describes a task in natural language that requires visual screen interaction and no API or CLI exists for the target app. Supports fully on-device local mode and cloud mode.

## Requirements

- A system with a **graphical desktop** (macOS / Windows / Linux)
- `mano-cua` binary installed (v1.1.0+ recommended for full feature support)

### Installation

**macOS / Linux (Homebrew):**

```bash
brew install Mininglamp-AI/tap/mano-cua

# Update to latest version
brew upgrade Mininglamp-AI/tap/mano-cua
```

**Windows:**

Download the latest `mano-cua-windows.zip` from [GitHub Releases](https://github.com/Mininglamp-AI/mano-skill/releases), extract it, and add the folder to your `PATH`.

## Usage

```bash
# Run a task
mano-cua run "your task description"

# Run with options (minimize UI panel and set max steps)
mano-cua run "task" --minimize --max-steps 10

# Open a URL in the browser before starting the task
mano-cua run "task" --url "https://example.com"

# Open an app before starting the task
mano-cua run "task" --app "Notes"

# Run in local mode (on-device inference, macOS Apple Silicon only)
mano-cua run "task" --local

# Stop the current running task
mano-cua stop
```

Run `mano-cua --help` or `mano-cua <command> --help` for full flags and options.

> **Note:** Only one task can run at a time per device. If you need to start a new task, first stop the current one with `mano-cua stop`.

> **--app vs --url:** Use one or the other, not both. `--app` launches a desktop application by name. `--url` opens a URL in the default browser. Both bring the target to the foreground before the agent starts.

> **Troubleshooting:** If tasks fail unexpectedly or features described below are unavailable, ensure your CLI is up to date: `brew upgrade Mininglamp-AI/tap/mano-cua`.

## Configuration

```bash
mano-cua config --list                        # Show all settings
mano-cua config --set max-steps 50            # Set default max steps
mano-cua config --set minimize true           # Always start with UI panel minimized
mano-cua config --set disable-bash true       # Disable shell tool in cloud mode
```

## Local Mode

Runs [Mano-P](https://huggingface.co/Mininglamp-2718/Mano-P) entirely on-device via MLX. No data leaves the machine. **Requires macOS with Apple Silicon (M1+).** The local model is lightweight (4B) — clarify the user's instruction and add context that the model may not infer on its own. Use `--app` or `--url` to set the starting context.

> **Tips for local mode:**
> - Vague instructions need specifics: "look up AI news" → `"Search for artificial intelligence news and open the first result"` with `--url "https://www.google.com"`
> - Tasks requiring domain knowledge need context: "adjust screen brightness" → `"Adjust screen brightness to 50% in System Settings > Display"` with `--app "System Settings"`

**Setup:**

```bash
mano-cua check
mano-cua install-sdk
mano-cua install-model

# Optional: use a custom Python environment or model path if dependencies or weights are already in local
mano-cua config --set python-path /path/to/.venv/bin/python
mano-cua config --set default-model-path /path/to/model-weights
```

> **Model format:** Local mode expects MLX w8a16 quantized weights for optimal performance. If your model is in fp16, convert it first:
> ```bash
> python -m mlx_vlm.convert --hf-path /path/to/fp16-model --mlx-path /path/to/output-w8a16 -q --q-bits 8 --dtype float16
> ```

**Run:**

```bash
mano-cua run "Search for openai on Google and open the first result" --local --url "https://www.google.com"
mano-cua run "Search for iphone on Xiaohongshu and open the first post" --local --url "https://www.xiaohongshu.com" --minimize --max-steps 15
mano-cua run "Create a new note titled hello world" --local --app "Notes"
```

## Examples

```bash
# Local mode (recommended for privacy — all inference on-device, no data leaves the machine)
mano-cua run "Search for openai on Google and open the first result" --local --url "https://www.google.com" --minimize
mano-cua run "Create a new note titled hello world" --local --app "Notes"

# Cloud mode
mano-cua run "Open Notes and create a new note titled Meeting Summary"
mano-cua run "Search for AI news in the browser and show the first result" --minimize --max-steps 20

# Cloud mode with --app or --url
mano-cua run "Create a calendar event for Friday 20:00 named Team Meeting" --app "Microsoft Outlook"
mano-cua run "Compare available plans for the AeroAPI" --url "https://www.flightaware.com/"

# Cloud mode — shell tool used for applicable steps to reduce time and improve accuracy (v1.1.0+)
mano-cua run "Create a file called report.txt on the Desktop with the content 'Q2 revenue summary', then mark it with a red tag in Finder"

# Stop the current task (use before starting a new one)
mano-cua stop
```

## How It Works

At each step, the current screen state is analyzed by a hybrid vision model to decide the next action. The agent performs bounded GUI actions (click, type, scroll, drag) only within the user-specified task scope, visible foreground target, and configured step/session limits. In cloud mode, when certain steps can be accomplished via shell, a shell tool will be invoked to perform the action rather than GUI operations to reduce steps and improve accuracy (requires v1.1.0+). For sensitive or irreversible actions, the agent pauses and prompts the user for explicit confirmation before proceeding.

Hybrid vision model:
- **Mano-P model** — handles straightforward, lightweight tasks with rapid output.
- **Claude (vision analysis)** — handles complex tasks requiring deeper reasoning. In cloud mode, only the primary-display screenshot is sent transiently via HTTPS for the current inference step; no background monitoring occurs.

The system automatically selects the appropriate model based on task complexity.

In **local mode (`--local`)**, a local Mano-P model runs on-device via MLX. No network calls for inference. Local mode is only supported on macOS with Apple Silicon.

**Structural capability boundaries (what the tool cannot do):**

- Cannot run in the background or persist between sessions — each invocation is a single, short-lived task.
- Cannot interact with secondary monitors — only the primary display is used.
- Cannot bypass OS-level permission dialogs or security prompts.
- Cannot access stored passwords, tokens, cookies, or credential managers — it can only see and interact with what is visually rendered on screen.
- In local mode, cannot execute shell commands or access the filesystem beyond what is visible on screen.
- In cloud mode, the shell tool may be used when it can accomplish a step more efficiently. This capability can be disabled via `mano-cua config --set disable-bash true`.

## Status Panel

A small UI panel is displayed on the top-right corner of the screen to track and manage the current session status.

## Data, Privacy & Safety

- The user must explicitly describe the task before any action is taken. There is no background operation, no scheduled scanning, and no persistent connection.
- Sensitive or irreversible actions (making purchases, entering credentials, deleting data) trigger a confirmation prompt — the agent pauses and waits for explicit user approval before proceeding.
- Step count is capped via `--max-steps`, preventing runaway execution.
- The on-screen status panel displays every action in real-time; the user can stop immediately via the panel or `mano-cua stop`.
- The agent stops the moment the user intervenes with mouse/keyboard input or the session ends.
- Most actions performed are inherently reversible (clicking, scrolling, typing can be undone). For non-reversible actions, the confirmation mechanism described above applies.
- In cloud mode, primary-display screenshots are sent transiently for inference only during an active user-initiated session; no continuous recording, background monitoring, or credential-store access occurs.
- For privacy-sensitive tasks, **local mode (`--local`)** runs inference entirely on-device with zero network calls — no data ever leaves the machine.
- The agent has no programmatic access to application data, APIs, or internal state — it can only see what is visually rendered on screen and interact via standard mouse/keyboard input.
- It does not access stored passwords, tokens, cookies, session stores, keychains, or credential managers. No API keys or secrets are required or embedded.
- The scope is limited to what the user explicitly describes in the task — the agent does not navigate to unrelated apps or accounts on its own.
- When `--app` or `--url` is specified, the agent's interaction is focused on that specific application or webpage.
- The full source code is [open source on GitHub](https://github.com/Mininglamp-AI/mano-skill) under MIT-0 license. The Homebrew formula builds directly from tagged GitHub releases with verifiable checksums.
- All network calls are isolated in a single module ([`task_model.py`](https://github.com/Mininglamp-AI/mano-skill/blob/main/visual/model/task_model.py)) for easy auditing.
- The client identifies itself only with a locally generated device ID (`~/.myapp_device_id`) — no secrets are transmitted or stored remotely.

## Important Notes

- **Do not use the mouse or keyboard during the task.** Manual input while mano-cua is running may cause unexpected behavior.
- **Multiple displays:** only the primary display is used. All mouse movements, clicks, and screenshots are restricted to that display.

## Platform Support

macOS is the primary and most tested platform. Windows adaptation has been completed with full support for GUI automation in cloud mode. Local mode (on-device inference) is only available on macOS with Apple Silicon. Linux support is functional but less tested — minor issues are expected.
