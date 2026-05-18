# Mano skill

Desktop GUI automation driven by natural language. Captures screenshots, analyzes them with a hybrid vision model, and executes the returned actions on the local machine — click, type, scroll, drag, and more. Supports fully on-device local mode and cloud mode.

> **Skill:** Also available as a Claude Code / OpenClaw skill at [clawhub.ai/hanningwang/mano-cua](https://clawhub.ai/hanningwang/mano-cua) and in the [`skill/`](skill/) directory of this repo.

## How It Works

```
User ──► Local client ──► Cloud Server ──► Local client executes action
              │                         │
         screenshot               model selection
                                       │
                            ┌──────────┴──────────┐
                            │                     │
                       Mano Model           Claude CUA Model
                    (fast, lightweight)    (complex reasoning)
```

At each step, mano-cua captures the current screenshot and sends it along with the task description to the cloud server. The server analyzes the task and **automatically selects the most suitable model**:

- **Mano Model** — optimized for straightforward, repetitive GUI tasks. Low latency, high throughput. Ideal for simple clicks, form filling, and navigation.
- **Claude CUA (Computer Use Agent)** — handles tasks that require deeper visual understanding and multi-step reasoning. Used when the task involves complex layouts, ambiguous UI elements, or decision-making.

The server evaluates task complexity in real time and routes accordingly, balancing speed and accuracy.

## Installation

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

> **Note:** Only one task can run at a time per device. If you need to start a new task, first stop the current one with `mano-cua stop`.

## Configuration

Persistent settings are stored in `~/.mano/config.json`.

```bash
# List all keys and current values
mano-cua config --list

# Read or set a value
mano-cua config --get save-trajectory
mano-cua config --set save-trajectory true
```

| Key               | Default | Description                                                              |
| ----------------- | ------- | ------------------------------------------------------------------------ |
| `max-steps`       | `100`   | Maximum steps per task                                                   |
| `minimize`        | `false` | Start with the status panel minimized (`true` / `false`)                 |
| `save-trajectory` | `false` | Save a per-run trajectory under `~/.mano/trajectory/` (`true` / `false`) |

When `save-trajectory` is `true`, each run writes a session folder (for example `~/.mano/trajectory/sess-<timestamp>-<id>/`) containing:

- `session.json` — task metadata and final status
- `history.jsonl` — step-by-step actions, reasoning, and screenshot paths
- `screenshots/` — PNG captures per step
- `whole.log` — full terminal output (stdout/stderr) for the run
- `report.html` — offline HTML timeline with collapsible screenshots (open in a browser)

Other keys (for example `default-model-path`, `python-path`, `w8a8`) apply to local mode; run `mano-cua config --list` for the full list.

## Local Mode

Runs [Mano-P](https://huggingface.co/Mininglamp-2718/Mano-P) entirely on-device via MLX. No data leaves the machine. Requires macOS with Apple Silicon (M1+).

```bash
# Setup
mano-cua check
mano-cua install-sdk
mano-cua install-model

# Run
mano-cua run "click the search box, type openai, click search" --local --url "https://www.google.com"
```

## Examples

```bash
# Local mode (all inference on-device, no data leaves the machine)
mano-cua run "click the search box, type openai, click search, click the first result" --local --url "https://www.google.com" --minimize
mano-cua run "create a new note and type hello world" --local --app "Notes"

# Cloud mode
mano-cua run "Open Notes and create a new note titled Meeting Summary"
mano-cua run "Search for AI news in the browser and show the first result" --minimize --max-steps 20

# Cloud mode with --app or --url
mano-cua run "Create a calendar event for Friday 20:00 named Team Meeting" --app "Microsoft Outlook"
mano-cua run "Compare available plans for the AeroAPI" --url "https://www.flightaware.com/"

# Stop the current task
mano-cua stop
```

## Supported Actions

click · type · hotkey · scroll · drag · mouse move · screenshot · wait · app launch

## Permissions

Screen Recording and Accessibility (Keyboard/Mouse control) permissions are required. Grant these in **System Preferences > Privacy & Security** before running.

## Status Panel

A small UI panel is displayed on the top-right corner of the screen to track and manage the current session status.

## Safety & Consent

- Sensitive or irreversible actions trigger a confirmation prompt — the agent pauses and waits for explicit user approval before proceeding.
- Screenshots are captured and applications may be started or closed during the session. **Avoid exposing apps with sensitive or critical data** while a task is running.
- For privacy-sensitive tasks, **local mode (`--local`)** runs inference entirely on-device with zero network calls.

## Important Notes

- **Do not use the mouse or keyboard during the task.** Manual input while mano-cua is running may cause unexpected behavior.
- **Multiple displays:** only the primary display is used. All mouse movements, clicks, and screenshots are restricted to that display.

## Platform Support

macOS is the preferred and most tested platform. Adaptations for Windows and Linux are not yet fully completed — minor issues are expected.

## License

MIT-0
