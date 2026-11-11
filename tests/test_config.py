# -*- coding: utf-8 -*-
"""設定層測試：夾限、惡意輸入、原子存取、往返一致性。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from autoclicker import config
from autoclicker.config import (GlobalConfig, PointConfig, Settings,
                                normalize_settings, sanitize_point,
                                default_settings, load_settings,
                                save_settings, settings_to_dict,
                                point_to_dict, button_label)


class TestSanitizePoint(unittest.TestCase):
    def test_defaults_on_none(self):
        p = sanitize_point(None, 0)
        self.assertEqual(p.name, "點位 1")
        self.assertEqual(p.x, 0)

    def test_clamp(self):
        w: list[str] = []
        p = sanitize_point({"name": "a" * 300, "x": 10 ** 9, "y": -10 ** 9,
                            "radius": 9999, "repeat": 9999,
                            "jitter_pct": 999, "weight": -5}, 0, w)
        self.assertLessEqual(len(p.name), 64)
        self.assertTrue(w)
        self.assertGreaterEqual(p.repeat, 1)
        self.assertGreaterEqual(p.weight, 1)

    def test_hostile_types(self):
        w: list[str] = []
        p = sanitize_point({"name": 123, "x": "abc", "y": [1],
                            "enabled": "yes", "button": "<script>",
                            "jitter_mode": "drop table", "double": 1,
                            "screen_dpi": -50}, 0, w)
        self.assertIsInstance(p, PointConfig)
        self.assertTrue(w)
        self.assertIsInstance(p.enabled, bool)
        self.assertIsInstance(p.double, bool)
        self.assertIn(p.button, ("left", "right", "middle"))
        self.assertIn(p.jitter_mode, ("uniform", "normal"))

    def test_bool_not_int(self):
        w: list[str] = []
        p = sanitize_point({"x": True}, 0, w)
        self.assertEqual(p.x, 0)
        self.assertTrue(w)


class TestNormalizeSettings(unittest.TestCase):
    def test_point_cap(self):
        raw = {"points": [{"x": i, "y": i} for i in range(500)]}
        w: list[str] = []
        s = normalize_settings(raw, w)
        self.assertLessEqual(len(s.points), config.MAX_POINTS)
        self.assertTrue(w)

    def test_malicious_top_level(self):
        raw = {"points": "all your base", "config": 42,
               "monitor_layout": [{"evil": "\x00" * 100}]}
        w: list[str] = []
        s = normalize_settings(raw, w)
        self.assertIsInstance(s, Settings)
        self.assertEqual(len(s.points), 0)
        self.assertIsInstance(s.config, GlobalConfig)

    def test_global_order_pair_swap(self):
        raw = {"config": {"long_pause_min_ms": 2000,
                          "long_pause_max_ms": 100}}
        w: list[str] = []
        s = normalize_settings(raw, w)
        self.assertLessEqual(s.config.long_pause_min_ms,
                             s.config.long_pause_max_ms)
        self.assertTrue(w)

    def test_hotkey_fallback(self):
        raw = {"config": {"hotkey_start": "BOMB", "hotkey_stop": None}}
        w: list[str] = []
        s = normalize_settings(raw, w)
        self.assertEqual(s.config.hotkey_start, "F8")
        self.assertEqual(s.config.hotkey_stop, "F9")

    def test_roundtrip(self):
        s = default_settings()
        s.points = [sanitize_point({"name": "測試", "x": 100, "y": 200,
                                    "screen_index": 1}, 0)]
        d = settings_to_dict(s)
        self.assertIsInstance(d, dict)
        w: list[str] = []
        s2 = normalize_settings(json.loads(json.dumps(d)), w)
        self.assertEqual(s2.points[0].x, 100)
        self.assertEqual(s2.points[0].name, "測試")


class TestSaveLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_file(self):
        s = default_settings()
        s.points = [sanitize_point({"name": "存檔", "x": 5, "y": 6}, 0)]
        save_settings(s, self.path)
        self.assertTrue(self.path.exists())
        loaded, w = load_settings(self.path)
        self.assertEqual(loaded.points[0].name, "存檔")
        self.assertEqual(loaded.points[0].x, 5)

    def test_no_tmp_leftover(self):
        s = default_settings()
        save_settings(s, self.path)
        leftovers = [f for f in os.listdir(self.tmp.name)
                     if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_corrupted_returns_default(self):
        self.path.write_bytes(b"\xff\xfe not json \x00\x01")
        loaded, w = load_settings(self.path)
        self.assertEqual(loaded.points, [])
        self.assertTrue(w)

    def test_oversized_rejected(self):
        self.path.write_bytes(b'{"points":[]}' + b" " * (config.MAX_SETTING_FILE_BYTES + 10))
        loaded, w = load_settings(self.path)
        self.assertEqual(loaded.points, [])
        self.assertTrue(w)

    def test_missing_file(self):
        loaded, w = load_settings(Path(self.tmp.name) / "nope.json")
        self.assertIsInstance(loaded, Settings)


class TestHelpers(unittest.TestCase):
    def test_button_label(self):
        self.assertEqual(button_label("left"), "左鍵")
        self.assertEqual(button_label("right"), "右鍵")
        self.assertEqual(button_label("middle"), "中鍵")
        self.assertIsInstance(button_label("bogus"), str)

    def test_point_to_dict_keys(self):
        d = point_to_dict(PointConfig())
        self.assertIn("x", d)
        self.assertIn("screen_dpi", d)


if __name__ == "__main__":
    unittest.main()
