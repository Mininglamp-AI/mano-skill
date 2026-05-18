"""Smoke test for trajectory package import."""

import unittest


class TestPackageImport(unittest.TestCase):
    def test_import_without_side_effects(self):
        import visual.trajectory  # noqa: F401

        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
