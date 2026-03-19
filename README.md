# Mano skill

Desktop GUI automation driven by natural language. Captures screenshots, sends them to a cloud-based hybrid vision model, and executes the returned actions on the local machine — click, type, scroll, drag, and more.

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

At each step, fty-nb captures the current screenshot and sends it along with the task description to the cloud server. The server analyzes the task and **automatically selects the most suitable model**:

- **Mano Model** — optimized for straightforward, repetitive GUI tasks. Low latency, high throughput. Ideal for simple clicks, form filling, and navigation.
- **Claude CUA (Computer Use Agent)** — handles tasks that require deeper visual understanding and multi-step reasoning. Used when the task involves complex layouts, ambiguous UI elements, or decision-making.

The server evaluates task complexity in real time and routes accordingly, balancing speed and accuracy.

## Installation

```bash
brew tap HanningWang/tap
brew install fty-nb
```

## Usage

```bash
fty-nb run "your task description"
```

## Examples

```bash
fty-nb run "Open WeChat and tell FTY that the meeting is postponed"
fty-nb run "Search for AI news in Xiaohongshu and show the first post"
```

## Supported Actions

click · type · hotkey · scroll · drag · mouse move · screenshot · wait · app launch

## Permissions

Screen Recording and Accessibility (Keyboard/Mouse control) permissions are required. Grant these in **System Preferences > Privacy & Security** before running.

## Status Panel

A small UI panel is displayed on the top-right corner of the screen to track and manage the current session status.

## Safety & Consent

- User consent is required before proceeding with steps that may be sensitive or potentially dangerous.
- Screenshots are captured and applications may be started or closed during the session. **Avoid exposing apps with sensitive or critical data** while a task is running.

## Important Notes

- **Do not use the mouse or keyboard during the task.** Manual input while fty-nb is running may cause unexpected behavior.
- **Multiple displays:** only the primary display is used. All mouse movements, clicks, and screenshots are restricted to that display.

## Platform Support

This is a **Beta** release. macOS is the preferred and most tested platform. Adaptations for Windows and Linux are not yet fully completed — minor issues are expected.

## License

MIT
