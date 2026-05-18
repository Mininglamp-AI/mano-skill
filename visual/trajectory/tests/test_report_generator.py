"""Tests for report.html generation."""

import json
import os
import tempfile
import unittest

from visual.trajectory.history import append_history_line
from visual.trajectory.report_generator import generate_report


class TestReportGenerator(unittest.TestCase):
    def _fixture_dir(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "screenshots"), exist_ok=True)
        session = {
            "task": "打开企业微信",
            "status": "completed",
            "total_steps": 3,
            "session_id": "sess-test",
            "started_at": "2026-05-18T09:43:59",
            "finished_at": "2026-05-18T09:44:21",
            "agent_type": "cloud",
            "platform": "Windows",
        }
        with open(os.path.join(tmp, "session.json"), "w", encoding="utf-8") as f:
            json.dump(session, f)
        append_history_line(
            tmp, step=0, action_desc="Initializing", reasoning="init", phase="init"
        )
        append_history_line(
            tmp,
            step=1,
            action_desc="key: super",
            reasoning="search",
            phase="action",
            screenshot="screenshots/1.png",
        )
        png = os.path.join(tmp, "screenshots", "1.png")
        with open(png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        append_history_line(
            tmp, step=3, action_desc="DONE", reasoning="done", phase="terminal"
        )
        return tmp

    def test_header_contains_task_and_status(self):
        tmp = self._fixture_dir()
        path = generate_report(tmp)
        html = open(path, encoding="utf-8").read()
        self.assertIn("打开企业微信", html)
        self.assertIn("completed", html)

    def test_collapsible_screenshot_and_placeholder(self):
        tmp = self._fixture_dir()
        html = open(generate_report(tmp), encoding="utf-8").read()
        self.assertIn("screenshot-details", html)
        self.assertIn('screenshots/1.png', html)
        append_history_line(
            tmp, step=2, action_desc="key: Escape", reasoning="x", phase="action"
        )
        html2 = open(generate_report(tmp), encoding="utf-8").read()
        self.assertIn("(No screenshot)", html2)

    def test_action_kind_css_classes(self):
        tmp = self._fixture_dir()
        html = open(generate_report(tmp), encoding="utf-8").read()
        self.assertIn("action-key", html)
        self.assertIn("action-done", html)

    def test_does_not_read_whole_log(self):
        tmp = self._fixture_dir()
        whole = os.path.join(tmp, "whole.log")
        with open(whole, "w", encoding="utf-8") as f:
            f.write("SECRET_TERMINAL_ONLY")
        html = open(generate_report(tmp), encoding="utf-8").read()
        self.assertNotIn("SECRET_TERMINAL_ONLY", html)


if __name__ == "__main__":
    unittest.main()
