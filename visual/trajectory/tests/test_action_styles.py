"""Tests for action_kind inference."""

import unittest

from visual.trajectory.action_styles import (
    ACTION_KIND_DONE,
    ACTION_KIND_FAIL,
    ACTION_KIND_INITIALIZING,
    ACTION_KIND_KEY,
    ACTION_KIND_OPEN_APP,
    infer_action_kind,
)


class TestActionStyles(unittest.TestCase):
    def test_initializing(self):
        self.assertEqual(infer_action_kind("Initializing"), ACTION_KIND_INITIALIZING)

    def test_open_app(self):
        self.assertEqual(infer_action_kind("Open app: 企业微信"), ACTION_KIND_OPEN_APP)

    def test_key(self):
        self.assertEqual(infer_action_kind("key: super"), ACTION_KIND_KEY)

    def test_done_fail(self):
        self.assertEqual(infer_action_kind("DONE"), ACTION_KIND_DONE)
        self.assertEqual(infer_action_kind("FAIL"), ACTION_KIND_FAIL)


if __name__ == "__main__":
    unittest.main()
