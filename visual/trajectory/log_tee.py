"""Stdout/stderr tee to trajectory whole.log with early buffer support."""

import os
import sys
import threading
from typing import List, Optional, TextIO

_lock = threading.Lock()
_original_stdout: Optional[TextIO] = None
_original_stderr: Optional[TextIO] = None
_early_buffer: List[str] = []
_buffer_active = False
_tee_installed = False
_log_file: Optional[TextIO] = None


class TeeWriter:
    """Write to terminal stream and trajectory log file."""

    def __init__(self, stream: TextIO, log_file: Optional[TextIO]):
        self._stream = stream
        self._log_file = log_file
        self._write_lock = threading.Lock()

    def write(self, data: str) -> int:
        if not data:
            return 0
        with self._write_lock:
            self._stream.write(data)
            if self._log_file is not None:
                self._log_file.write(data)
                self._log_file.flush()
            if hasattr(self._stream, "flush"):
                self._stream.flush()
        return len(data)

    def flush(self) -> None:
        with self._write_lock:
            self._stream.flush()
            if self._log_file is not None:
                self._log_file.flush()

    def isatty(self) -> bool:
        return getattr(self._stream, "isatty", lambda: False)()

    def fileno(self) -> int:
        return self._stream.fileno()

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


class _EarlyBufferWriter:
    """Tee terminal output into an in-memory buffer before trajectory dir exists."""

    def __init__(self, stream: TextIO, buffer: List[str]):
        self._stream = stream
        self._buffer = buffer
        self._write_lock = threading.Lock()

    def write(self, data: str) -> int:
        if not data:
            return 0
        with self._write_lock:
            self._stream.write(data)
            self._buffer.append(data)
            if hasattr(self._stream, "flush"):
                self._stream.flush()
        return len(data)

    def flush(self) -> None:
        with self._write_lock:
            self._stream.flush()

    def isatty(self) -> bool:
        return getattr(self._stream, "isatty", lambda: False)()

    def fileno(self) -> int:
        return self._stream.fileno()

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def is_trajectory_logging_active() -> bool:
    """Return True if early buffer or file tee is active."""
    return _buffer_active or _tee_installed


def enable_early_trajectory_buffer() -> None:
    """Start teeing stdout/stderr to an in-memory buffer (before trajectory dir exists)."""
    global _buffer_active, _original_stdout, _original_stderr, _early_buffer

    with _lock:
        if _tee_installed or _buffer_active:
            return
        _original_stdout = sys.stdout
        _original_stderr = sys.stderr
        _early_buffer = []
        _buffer_active = True
        sys.stdout = _EarlyBufferWriter(_original_stdout, _early_buffer)  # type: ignore[assignment]
        sys.stderr = _EarlyBufferWriter(_original_stderr, _early_buffer)  # type: ignore[assignment]


def install_trajectory_tee(trajectory_dir: str) -> None:
    """Flush early buffer to whole.log and tee further output to that file."""
    global _buffer_active, _tee_installed, _log_file, _early_buffer

    with _lock:
        log_path = os.path.join(trajectory_dir, "whole.log")
        os.makedirs(trajectory_dir, exist_ok=True)

        with open(log_path, "w", encoding="utf-8", errors="replace") as f:
            for chunk in _early_buffer:
                f.write(chunk)
        _early_buffer = []
        _buffer_active = False

        if _log_file is not None and not _log_file.closed:
            _log_file.close()

        _log_file = open(log_path, "a", encoding="utf-8", errors="replace")

        base_out = _original_stdout or sys.__stdout__
        base_err = _original_stderr or sys.__stderr__
        sys.stdout = TeeWriter(base_out, _log_file)  # type: ignore[assignment]
        sys.stderr = TeeWriter(base_err, _log_file)  # type: ignore[assignment]
        _tee_installed = True


def uninstall_trajectory_tee() -> None:
    """Restore original stdout/stderr and close the log file."""
    global _tee_installed, _log_file, _buffer_active, _early_buffer

    with _lock:
        if not _tee_installed and not _buffer_active:
            return

        if _tee_installed:
            base_out = _original_stdout or sys.__stdout__
            base_err = _original_stderr or sys.__stderr__
            if isinstance(sys.stdout, TeeWriter):
                sys.stdout.flush()
            if isinstance(sys.stderr, TeeWriter):
                sys.stderr.flush()
            sys.stdout = base_out
            sys.stderr = base_err
            _tee_installed = False

        if _log_file is not None and not _log_file.closed:
            _log_file.flush()
            _log_file.close()
        _log_file = None

        _buffer_active = False
        _early_buffer = []
