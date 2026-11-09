import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'panel_layout', Path(__file__).resolve().parents[1] / 'blender_codex/panel_layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class PanelLayoutTests(unittest.TestCase):
    def test_uses_available_editor_beyond_original_sidebar(self):
        self.assertEqual(layout.horizontal_bounds(10, 900, 1200, 800), (400, 800))

    def test_resize_remains_inside_editor_and_anchors_right(self):
        self.assertEqual(layout.horizontal_bounds(100, 900, 1200, 5000), (100, 1100))
        self.assertEqual(layout.horizontal_bounds(100, 900, 1200, 1), (960, 240))

    def test_small_window_and_scaled_minimum(self):
        self.assertEqual(layout.horizontal_bounds(100, 200, 280, 900, 360), (100, 180))
        self.assertEqual(layout.horizontal_bounds(100, 900, 1200, 100, 360), (840, 360))

    def test_reset_follows_native_sidebar(self):
        self.assertEqual(layout.horizontal_bounds(10, 840, 1200), (840, 360))


if __name__ == '__main__':
    unittest.main()
