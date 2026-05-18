"""Trajectory logging, history, and HTML report generation."""

from visual.trajectory.log_tee import (
    enable_early_trajectory_buffer,
    install_trajectory_tee,
    is_trajectory_logging_active,
    uninstall_trajectory_tee,
)
from visual.trajectory.report_generator import generate_report

__all__ = [
    "enable_early_trajectory_buffer",
    "install_trajectory_tee",
    "uninstall_trajectory_tee",
    "is_trajectory_logging_active",
    "generate_report",
]
