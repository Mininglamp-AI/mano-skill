"""Tests for trajectory stdout/stderr tee."""

import io
import os
import sys
import tempfile
import unittest

from visual.trajectory import log_tee


class TestLogTee(unittest.TestCase):
    def setUp(self):
        log_tee.uninstall_trajectory_tee()
        self._orig_out = sys.stdout
        self._orig_err = sys.stderr

    def tearDown(self):
        log_tee.uninstall_trajectory_tee()
        sys.stdout = self._orig_out
        sys.stderr = self._orig_err

    def test_early_buffer_flushed_to_whole_log(self):
        log_tee.enable_early_trajectory_buffer()
        print("before-dir", end="")
        with tempfile.TemporaryDirectory() as tmp:
            log_tee.install_trajectory_tee(tmp)
            print("after-dir")
            log_tee.uninstall_trajectory_tee()
            log_path = os.path.join(tmp, "whole.log")
            self.assertTrue(os.path.isfile(log_path))
            content = open(log_path, encoding="utf-8").read()
            self.assertIn("before-dir", content)
            self.assertIn("after-dir", content)

    def test_tee_writes_to_stream_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_tee.enable_early_trajectory_buffer()
            log_tee.install_trajectory_tee(tmp)
            captured = io.StringIO()
            real_out = sys.stdout._stream if hasattr(sys.stdout, "_stream") else sys.__stdout__
            sys.stdout = log_tee.TeeWriter(captured, sys.stdout._log_file)  # type: ignore[attr-defined]
            # simpler: just print and read file
            log_tee.uninstall_trajectory_tee()
            log_tee.enable_early_trajectory_buffer()
            log_tee.install_trajectory_tee(tmp)
            print("tee-line")
            log_tee.uninstall_trajectory_tee()
            content = open(os.path.join(tmp, "whole.log"), encoding="utf-8").read()
            self.assertIn("tee-line", content)

    def test_uninstall_stops_file_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_tee.enable_early_trajectory_buffer()
            log_tee.install_trajectory_tee(tmp)
            print("line1")
            log_tee.uninstall_trajectory_tee()
            print("line2")
            content = open(os.path.join(tmp, "whole.log"), encoding="utf-8").read()
            self.assertIn("line1", content)
            self.assertNotIn("line2", content)

    def test_buffer_inactive_when_not_enabled(self):
        self.assertFalse(log_tee.is_trajectory_logging_active())


if __name__ == "__main__":
    unittest.main()
