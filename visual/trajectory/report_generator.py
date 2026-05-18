"""Generate report.html from session.json and history.jsonl."""

import html
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from visual.trajectory.action_styles import css_class_for_kind, infer_action_kind

_WHOLE_LOG_NAME = "whole.log"

_STYLES = """
:root {
  --bg: #0f1419;
  --card: #1a2332;
  --text: #e7ecf3;
  --muted: #8b9cb3;
  --initializing: #6b7280;
  --open-app: #22c55e;
  --key: #3b82f6;
  --click: #f97316;
  --type: #a855f7;
  --done: #10b981;
  --fail: #ef4444;
  --other: #64748b;
}
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
  padding: 1.5rem;
  line-height: 1.5;
}
header.report-header {
  background: var(--card);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}
header.report-header h1 { margin: 0 0 0.75rem; font-size: 1.35rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.75rem;
}
.stat-label { color: var(--muted); font-size: 0.8rem; }
.stat-value { font-weight: 600; }
.toolbar { margin-bottom: 1rem; }
.toolbar button {
  background: #2563eb;
  color: #fff;
  border: none;
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  cursor: pointer;
  margin-right: 0.5rem;
}
.toolbar button:hover { background: #1d4ed8; }
.step-group {
  background: var(--card);
  border-radius: 10px;
  margin-bottom: 1rem;
  overflow: hidden;
}
.step-group > h2 {
  margin: 0;
  padding: 0.75rem 1rem;
  font-size: 1rem;
  background: rgba(255,255,255,0.04);
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.history-entry {
  padding: 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.history-entry header {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
.action-badge {
  font-weight: 600;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.9rem;
}
.timestamp, .phase-tag { color: var(--muted); font-size: 0.8rem; }
.reasoning { white-space: pre-wrap; margin: 0.5rem 0; }
.actions-json {
  font-size: 0.75rem;
  background: rgba(0,0,0,0.25);
  padding: 0.5rem;
  border-radius: 6px;
  overflow-x: auto;
}
.screenshot-details { margin-top: 0.5rem; }
.screenshot-details img {
  max-width: 100%;
  border-radius: 6px;
  margin-top: 0.5rem;
  border: 1px solid rgba(255,255,255,0.1);
}
.no-screenshot { color: var(--muted); font-size: 0.85rem; margin: 0.5rem 0 0; }
footer { margin-top: 2rem; color: var(--muted); font-size: 0.85rem; }
.action-initializing .action-badge { background: var(--initializing); color: #fff; }
.action-open-app .action-badge { background: var(--open-app); color: #fff; }
.action-key .action-badge { background: var(--key); color: #fff; }
.action-click .action-badge { background: var(--click); color: #fff; }
.action-type .action-badge { background: var(--type); color: #fff; }
.action-done .action-badge { background: var(--done); color: #fff; }
.action-fail .action-badge { background: var(--fail); color: #fff; }
.action-other .action-badge { background: var(--other); color: #fff; }
"""

_SCRIPT = """
function setAllScreenshots(open) {
  document.querySelectorAll('.screenshot-details').forEach(function(el) {
    el.open = open;
  });
}
document.getElementById('expand-all').addEventListener('click', function() { setAllScreenshots(true); });
document.getElementById('collapse-all').addEventListener('click', function() { setAllScreenshots(false); });
"""


def _escape(text: str) -> str:
    return html.escape(text or "", quote=True)


def _parse_timestamp(ts: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y%m%d-%H%M%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _elapsed_seconds(started: str, finished: str) -> Optional[int]:
    start_dt = _parse_timestamp(started)
    end_dt = _parse_timestamp(finished)
    if start_dt and end_dt:
        return int((end_dt - start_dt).total_seconds())
    return None


def _load_session(trajectory_dir: str) -> Dict[str, Any]:
    path = os.path.join(trajectory_dir, "session.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_history(trajectory_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(trajectory_dir, "history.jsonl")
    if not os.path.isfile(path):
        return []
    lines: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


def _resolve_screenshot(trajectory_dir: str, entry: Dict[str, Any]) -> Optional[str]:
    rel = entry.get("screenshot")
    if rel and os.path.isfile(os.path.join(trajectory_dir, rel)):
        return rel
    step = entry.get("step")
    if step is not None:
        candidate = f"screenshots/{step}.png"
        if os.path.isfile(os.path.join(trajectory_dir, candidate)):
            return candidate
    return None


def _render_entry(trajectory_dir: str, entry: Dict[str, Any]) -> str:
    action_desc = entry.get("action_desc", "")
    reasoning = entry.get("reasoning", "")
    timestamp = entry.get("timestamp", "")
    actions = entry.get("actions") or []
    kind = entry.get("action_kind") or infer_action_kind(action_desc, actions)
    css_class = css_class_for_kind(kind)
    screenshot_rel = _resolve_screenshot(trajectory_dir, entry)

    if screenshot_rel:
        screenshot_html = (
            '<details class="screenshot-details">'
            "<summary>Show screenshot</summary>"
            f'<img src="{_escape(screenshot_rel)}" alt="step screenshot" loading="lazy" />'
            "</details>"
        )
    else:
        screenshot_html = '<p class="no-screenshot">(No screenshot)</p>'

    actions_html = ""
    if actions:
        actions_json = _escape(json.dumps(actions, ensure_ascii=False, indent=2))
        actions_html = f'<pre class="actions-json">{actions_json}</pre>'

    return (
        f'<article class="history-entry {css_class}">'
        "<header>"
        f'<span class="action-badge">{_escape(action_desc)}</span>'
        f'<span class="timestamp">{_escape(timestamp)}</span>'
        f'<span class="phase-tag">{_escape(str(entry.get("phase", "")))}</span>'
        "</header>"
        f'<div class="reasoning">{_escape(reasoning)}</div>'
        f"{actions_html}"
        f"{screenshot_html}"
        "</article>"
    )


def generate_report(trajectory_dir: str) -> str:
    """Build report.html from session.json and history.jsonl only.

    Returns the path to the written report file.
    """
    session = _load_session(trajectory_dir)
    history = _load_history(trajectory_dir)

    started = session.get("started_at", "")
    finished = session.get("finished_at", "")
    elapsed = _elapsed_seconds(started, finished) if finished else None
    elapsed_str = f"{elapsed}s" if elapsed is not None else "n/a"

    stats_rows = [
        ("Task", session.get("task", "")),
        ("Status", session.get("status", "")),
        ("Total steps", str(session.get("total_steps", ""))),
        ("History events", str(len(history))),
        ("Session ID", session.get("session_id", "")),
        ("Agent", session.get("agent_type", "")),
        ("Platform", session.get("platform", "")),
        ("Started at", started),
        ("Finished at", finished or "n/a"),
        ("Duration", elapsed_str),
    ]
    if session.get("cloud_session_id"):
        stats_rows.append(("Cloud Session", session.get("cloud_session_id", "")))

    stats_html = "".join(
        f'<div><div class="stat-label">{_escape(label)}</div>'
        f'<div class="stat-value">{_escape(str(value))}</div></div>'
        for label, value in stats_rows
    )

    grouped = defaultdict(list)
    for entry in history:
        grouped[int(entry.get("step", 0))].append(entry)

    steps_html = "".join(
        f'<section class="step-group"><h2>Step {step}</h2>'
        + "".join(_render_entry(trajectory_dir, e) for e in grouped[step])
        + "</section>"
        for step in sorted(grouped.keys())
    )

    task_title = _escape(session.get("task", "Task Report"))
    whole_log_link = ""
    if os.path.isfile(os.path.join(trajectory_dir, _WHOLE_LOG_NAME)):
        whole_log_link = (
            f'<footer>Full terminal log: <a href="{_WHOLE_LOG_NAME}">whole.log</a></footer>'
        )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{task_title} — Mano Trajectory Report</title>
  <style>{_STYLES}</style>
</head>
<body>
  <header class="report-header">
    <h1>{task_title}</h1>
    <div class="stats-grid">{stats_html}</div>
  </header>
  <div class="toolbar">
    <button type="button" id="expand-all">Expand all screenshots</button>
    <button type="button" id="collapse-all">Collapse all screenshots</button>
  </div>
  <main>{steps_html or "<p>No history recorded</p>"}</main>
  {whole_log_link}
  <script>{_SCRIPT}</script>
</body>
</html>
"""
    out_path = os.path.join(trajectory_dir, "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
