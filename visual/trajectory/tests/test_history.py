"""Tests for history.jsonl append helper."""

import json
import os
import tempfile
import unittest

from visual.trajectory.history import append_history_line


class TestHistory(unittest.TestCase):
    def test_append_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            append_history_line(
                tmp,
                step=1,
                action_desc="key: Enter",
                reasoning="submit",
                phase="action",
            )
            path = os.path.join(tmp, "history.jsonl")
            line = json.loads(open(path, encoding="utf-8").read().strip())
            self.assertEqual(line["step"], 1)
            self.assertEqual(line["phase"], "action")
            self.assertEqual(line["action_kind"], "key")
            self.assertIn("timestamp", line)


if __name__ == "__main__":
    unittest.main()
