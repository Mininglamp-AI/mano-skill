"""Smoke tests for Windows fixes.

Run: python tests/windows_smoke.py
Exits non-zero on any assertion failure.
"""
import os
import sys
import platform
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TestKeyNormalizer(unittest.TestCase):
    """Both Windows and macOS behaviour must hold simultaneously \u2014 the
    function takes is_macos as a parameter, so we drive both branches.
    """

    def setUp(self):
        from visual.agents.key_normalizer import _normalize_key_token
        self.norm = _normalize_key_token

    # ---- Modifier semantics ----
    def test_cmd_on_mac_stays_cmd(self):
        self.assertEqual(self.norm("cmd", True), "cmd")
        self.assertEqual(self.norm("command", True), "cmd")

    def test_cmd_on_windows_becomes_ctrl(self):
        # Cmd / Command in model output \u2192 Ctrl on Windows (the "primary
        # shortcut modifier" semantic mapping, not the physical key).
        self.assertEqual(self.norm("cmd", False), "ctrl")
        self.assertEqual(self.norm("command", False), "ctrl")

    def test_super_meta_win_on_windows_becomes_cmd(self):
        # pynput's Key.cmd IS the Windows key on Windows. Previously these
        # collapsed to ctrl which broke Win+E / Win+R. Regression guard.
        for token in ("win", "meta", "super"):
            self.assertEqual(self.norm(token, False), "cmd",
                             f"{token!r} on Windows must \u2192 cmd (Win key)")

    def test_super_meta_win_on_mac_becomes_cmd(self):
        for token in ("win", "meta", "super"):
            self.assertEqual(self.norm(token, True), "cmd")

    def test_option_becomes_alt(self):
        self.assertEqual(self.norm("option", True), "alt")
        self.assertEqual(self.norm("opt", False), "alt")

    def test_control_preserves_legacy_mac_semantics(self):
        # ON MAC: ctrl in model output \u2192 cmd (legacy behaviour, do not break).
        self.assertEqual(self.norm("ctrl", True), "cmd")
        self.assertEqual(self.norm("control", True), "cmd")
        # On Windows: ctrl stays ctrl.
        self.assertEqual(self.norm("ctrl", False), "ctrl")
        self.assertEqual(self.norm("control", False), "ctrl")

    # ---- New aliases (Windows-leaning) ----
    def test_function_keys(self):
        for i in range(1, 13):
            self.assertEqual(self.norm(f"F{i}", False), f"f{i}")

    def test_arrow_aliases(self):
        self.assertEqual(self.norm("ArrowUp", False), "up")
        self.assertEqual(self.norm("arrow-down", False), "down")

    def test_print_screen_aliases(self):
        self.assertEqual(self.norm("PrintScreen", False), "print_screen")
        self.assertEqual(self.norm("PrtSc", False), "print_screen")

    def test_home_end_insert(self):
        self.assertEqual(self.norm("Home", False), "home")
        self.assertEqual(self.norm("End", False), "end")
        self.assertEqual(self.norm("Insert", False), "insert")

    # ---- Combined normalize_actions roundtrip ----
    def test_normalize_actions_win_e_on_windows(self):
        from visual.agents.key_normalizer import normalize_actions
        actions = [{
            "name": "computer",
            "input": {"action": "key", "text": "win+e"},
        }]
        # Force Windows behaviour through the public API.
        with mock.patch("visual.agents.key_normalizer.platform") as p:
            p.system.return_value = "Windows"
            out = normalize_actions(actions)
        ti = out[0]["input"]
        self.assertEqual(ti["modifiers"], ["cmd"])
        self.assertEqual(ti["mains"], ["e"])

    def test_normalize_actions_cmd_c_on_mac_unchanged(self):
        from visual.agents.key_normalizer import normalize_actions
        actions = [{
            "name": "computer",
            "input": {"action": "key", "text": "cmd+c"},
        }]
        with mock.patch("visual.agents.key_normalizer.platform") as p:
            p.system.return_value = "Darwin"
            out = normalize_actions(actions)
        ti = out[0]["input"]
        self.assertEqual(ti["modifiers"], ["cmd"])
        self.assertEqual(ti["mains"], ["c"])

    def test_normalize_actions_cmd_c_on_windows_becomes_ctrl_c(self):
        from visual.agents.key_normalizer import normalize_actions
        actions = [{
            "name": "computer",
            "input": {"action": "key", "text": "cmd+c"},
        }]
        with mock.patch("visual.agents.key_normalizer.platform") as p:
            p.system.return_value = "Windows"
            out = normalize_actions(actions)
        ti = out[0]["input"]
        self.assertEqual(ti["modifiers"], ["ctrl"])
        self.assertEqual(ti["mains"], ["c"])


class TestPrimaryMonitorRealMss(unittest.TestCase):
    """End-to-end test against the actually-installed mss — not a mock.

    Run on a real machine with mss installed; asserts the helper picks a
    monitor whose recorded ``(left, top)`` contains the screen origin
    (which is what every supported OS guarantees for the primary display).
    Skipped if mss isn't available or the test machine has zero displays.
    """

    def test_real_mss_primary_contains_origin(self):
        try:
            import mss as _mss
        except ImportError:
            self.skipTest("mss not installed")
        from visual.computer.computer_use_util import get_primary_monitor
        with _mss.mss() as sct:
            if len(sct.monitors) <= 1:
                self.skipTest("no real displays exposed by mss")
            mon_keys = list(sct.monitors[1].keys())
            print(f"  [real mss {_mss.__version__}] monitors[1] keys = {mon_keys}")
            primary = get_primary_monitor(sct)
            # Origin (0, 0) must lie within the chosen monitor's rect.
            self.assertLessEqual(primary["left"], 0)
            self.assertGreater(primary["left"] + primary["width"], 0)
            self.assertLessEqual(primary["top"], 0)
            self.assertGreater(primary["top"] + primary["height"], 0)


class TestPrimaryMonitor(unittest.TestCase):
    def test_picks_monitor_containing_origin_when_primary_is_secondary_index(self):
        """Mano-P #16 reproducer: user remarked their right-side display as
        primary; mss enumerates them in physical order so monitors[1] is the
        left/secondary display. Origin (0, 0) is inside the *real* primary,
        which is monitors[2] in this fake setup.
        """
        from visual.computer.computer_use_util import get_primary_monitor

        class FakeSct:
            monitors = [
                # virtual screen merged: spans -1920..1920
                {"left": -1920, "top": 0, "width": 3840, "height": 1080},
                # secondary on the left, negative offset — does NOT contain origin
                {"left": -1920, "top": 0, "width": 1920, "height": 1080},
                # primary, anchored at (0, 0) on Windows / macOS
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
        m = get_primary_monitor(FakeSct())
        self.assertEqual((m["left"], m["top"]), (0, 0))
        self.assertEqual(m["width"], 1920)

    def test_origin_strategy_works_without_is_primary_field(self):
        """mss <= 10.1 doesn't expose is_primary at all. The origin-containment
        rule must still pick the right monitor.
        """
        from visual.computer.computer_use_util import get_primary_monitor

        class FakeSct:
            monitors = [
                {"left": 0, "top": -1080, "width": 1920, "height": 2160},
                # display stacked above primary (negative top), no is_primary
                {"left": 0, "top": -1080, "width": 1920, "height": 1080},
                # the actual primary at (0, 0)
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
        m = get_primary_monitor(FakeSct())
        self.assertEqual(m["top"], 0)

    def test_falls_back_to_is_primary_when_no_origin_match(self):
        """Pathological setup where no monitor contains (0, 0) (e.g. all
        physical displays positioned with positive offsets in a tiled wall).
        Modern is_primary flag wins over the legacy monitors[1] fallback.
        """
        from visual.computer.computer_use_util import get_primary_monitor

        class FakeSct:
            monitors = [
                {"left": 100, "top": 100, "width": 4000, "height": 2000},
                {"left": 100, "top": 100, "width": 1920, "height": 1080},
                {"left": 2020, "top": 100, "width": 1920, "height": 1080,
                 "is_primary": True},
            ]
        m = get_primary_monitor(FakeSct())
        self.assertEqual(m["left"], 2020)

    def test_falls_back_to_index_1_on_single_display(self):
        from visual.computer.computer_use_util import get_primary_monitor

        class FakeSct:
            monitors = [
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
            ]
        m = get_primary_monitor(FakeSct())
        self.assertEqual(m["width"], 1920)

    def test_handles_mss_legacy_4key_schema(self):
        """mss 10.1.0 monitors only expose left/top/width/height. Helper must
        work without ever touching is_primary/name/unique_id keys.
        """
        from visual.computer.computer_use_util import get_primary_monitor

        class FakeSct:
            monitors = [
                {"left": 0, "top": 0, "width": 2256, "height": 1504},
                {"left": 0, "top": 0, "width": 2256, "height": 1504},
            ]
        m = get_primary_monitor(FakeSct())
        # Equal to original sct.monitors[1] behaviour on single-display setups.
        self.assertEqual(set(m.keys()), {"left", "top", "width", "height"})


class TestVisualConfigChip(unittest.TestCase):
    def test_chip_model_short_circuits_off_mac(self):
        from visual.config import visual_config

        # Even if sysctl somehow exists (e.g. WSL), platform guard returns "".
        with mock.patch.object(visual_config, "_platform") as p:
            p.system.return_value = "Windows"
            self.assertEqual(visual_config._get_chip_model(), "")

    def test_user_agent_on_windows_has_no_chip_tag(self):
        from visual.config import visual_config
        with mock.patch.object(visual_config, "_platform") as p:
            p.system.return_value = "Windows"
            p.machine.return_value = "AMD64"
            p.python_version.return_value = "3.13.5"
            p.release.return_value = "11"
            p.mac_ver.return_value = ("", ("", "", ""), "")
            ua = visual_config.build_user_agent()
            self.assertIn("Windows NT", ua)
            self.assertNotIn("Apple", ua)


class TestWindowsAppLauncher(unittest.TestCase):
    """Verify alias dispatch without actually launching anything."""

    def test_alias_table_covers_high_freq(self):
        from visual.computer.computer_action_executor import ComputerActionExecutor
        aliases = ComputerActionExecutor._WIN_APP_ALIASES
        for key in ("settings", "calculator", "notepad", "task manager",
                    "file explorer", "calc", "chrome", "edge",
                    "sticky notes", "control panel"):
            self.assertIn(key, aliases, f"alias {key!r} missing")

    def test_alias_table_is_english_only(self):
        """Per review feedback: don't carry CJK aliases in the executor; the
        model receives an English platform hint upstream.
        """
        from visual.computer.computer_action_executor import ComputerActionExecutor
        for k in ComputerActionExecutor._WIN_APP_ALIASES:
            self.assertTrue(k.isascii(),
                            f"alias key must be ASCII / English, got {k!r}")

    def test_open_app_windows_uses_startfile_first(self):
        # Build an executor instance without running __init__ (which touches mss).
        from visual.computer import computer_action_executor as cae
        inst = cae.ComputerActionExecutor.__new__(cae.ComputerActionExecutor)
        with mock.patch("visual.computer.computer_action_executor.os.startfile",
                        create=True) as sf, \
                mock.patch("visual.computer.computer_action_executor.subprocess.Popen") as sp, \
                mock.patch("visual.computer.computer_action_executor.subprocess.run") as sr:
            inst._open_app_windows("settings")
            sf.assert_called_once_with("ms-settings:")
            sp.assert_not_called()
            sr.assert_not_called()

    def test_open_app_windows_uwp_uses_explorer_shell(self):
        from visual.computer import computer_action_executor as cae
        inst = cae.ComputerActionExecutor.__new__(cae.ComputerActionExecutor)
        with mock.patch("visual.computer.computer_action_executor.os.startfile",
                        create=True) as sf, \
                mock.patch("visual.computer.computer_action_executor.subprocess.Popen") as sp:
            inst._open_app_windows("Sticky Notes")
            sp.assert_called_once()
            args, kwargs = sp.call_args
            self.assertTrue(args[0].lower().startswith("explorer.exe shell:appsfolder"))
            self.assertTrue(kwargs.get("shell"))
            sf.assert_not_called()

    def test_open_app_windows_falls_back_to_powershell(self):
        from visual.computer import computer_action_executor as cae
        inst = cae.ComputerActionExecutor.__new__(cae.ComputerActionExecutor)
        with mock.patch("visual.computer.computer_action_executor.os.startfile",
                        create=True, side_effect=OSError("not found")), \
                mock.patch("visual.computer.computer_action_executor.subprocess.run") as sr:
            sr.return_value = mock.Mock(returncode=0, stderr="")
            inst._open_app_windows("FantasyApp.exe")
            sr.assert_called_once()
            cmd = sr.call_args[0][0]
            self.assertEqual(cmd[0], "powershell")


if __name__ == "__main__":
    unittest.main(verbosity=2)
