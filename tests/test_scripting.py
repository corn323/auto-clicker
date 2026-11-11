# -*- coding: utf-8 -*-
"""腳本模組測試：schema 白名單、限制上限、惡意輸入拒絕、存取往返。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autoclicker import scripting
from autoclicker.scripting import (parse_script, load_script, save_script,
                                   parse_key, MAX_STEPS, MAX_DEPTH,
                                   MAX_EXPANDED_ACTIONS)


def ok(raw):
    script, errors, warnings = parse_script(raw)
    return script, errors, warnings


def valid(raw):
    script, errors, warnings = parse_script(raw)
    assert errors == [], errors
    return script, warnings


class TestValidScripts(unittest.TestCase):
    def test_minimal(self):
        script, errors, _ = ok({"version": 1, "name": "t",
                                "steps": [{"type": "wait", "ms": 50}]})
        self.assertEqual(errors, [])
        self.assertIsNotNone(script)
        self.assertEqual(script["steps"][0]["ms"], 50)

    def test_all_step_types(self):
        raw = {"version": 1, "name": "all", "steps": [
            {"type": "click", "x": 100, "y": 200, "button": "right",
             "double": True, "hold_ms": 30},
            {"type": "move", "x": 300, "y": 400, "mode": "curve"},
            {"type": "wait", "ms": 100},
            {"type": "press_key", "key": "F5", "hold_ms": 20},
            {"type": "loop", "count": 2, "steps": [{"type": "wait", "ms": 10}]},
            {"type": "if_pixel_color", "x": 0, "y": 0, "color": "#FF00AA",
             "tolerance": 20, "steps": [{"type": "wait", "ms": 10}],
             "else": [{"type": "wait", "ms": 10}]},
        ]}
        script, errors, _ = ok(raw)
        self.assertEqual(errors, [])
        self.assertIsNotNone(script)
        self.assertEqual(len(script["steps"]), 6)
        self.assertEqual(script["steps"][5]["color"], (0xFF, 0x00, 0xAA))

    def test_defaults_filled(self):
        script, errors, _ = ok({"steps": [{"type": "click", "x": 5, "y": 5}]})
        self.assertEqual(errors, [])
        step = script["steps"][0]
        self.assertEqual(step["button"], "left")
        self.assertFalse(step["double"])
        self.assertEqual(step["hold_ms"], 50)


class TestRejections(unittest.TestCase):
    def assert_rejected(self, raw):
        script, errors, _ = parse_script(raw)
        self.assertIsNone(script)
        self.assertTrue(errors)

    def test_not_object(self):
        self.assert_rejected([1, 2, 3])
        self.assert_rejected("hello")
        self.assert_rejected(None)

    def test_wrong_version(self):
        self.assert_rejected({"version": 2, "steps": [{"type": "wait", "ms": 10}]})

    def test_unknown_top_field(self):
        self.assert_rejected({"steps": [{"type": "wait", "ms": 10}],
                              "admin": True})

    def test_unknown_step_type(self):
        self.assert_rejected({"steps": [{"type": "format_disk"}]})

    def test_unknown_step_field(self):
        self.assert_rejected({"steps": [{"type": "wait", "ms": 10,
                                         "cmd": "rm -rf /"}]})

    def test_wait_out_of_range(self):
        self.assert_rejected({"steps": [{"type": "wait", "ms": 5}]})
        self.assert_rejected({"steps": [{"type": "wait", "ms": 999999999}]})
        self.assert_rejected({"steps": [{"type": "wait", "ms": "100"}]})

    def test_click_out_of_range(self):
        self.assert_rejected({"steps": [{"type": "click",
                                         "x": 10 ** 9, "y": 0}]})
        self.assert_rejected({"steps": [{"type": "click",
                                         "x": 0.5, "y": 0}]})
        self.assert_rejected({"steps": [{"type": "click", "x": 0, "y": 0,
                                         "button": "laser"}]})

    def test_bad_key(self):
        self.assert_rejected({"steps": [{"type": "press_key",
                                         "key": "WIN"}]})
        self.assert_rejected({"steps": [{"type": "press_key",
                                         "key": "A" * 200}]})

    def test_bad_color(self):
        self.assert_rejected({"steps": [{"type": "if_pixel_color", "x": 0,
                                         "y": 0, "color": "#GGGGGG"}]})
        self.assert_rejected({"steps": [{"type": "if_pixel_color", "x": 0,
                                         "y": 0, "color": "red"}]})

    def test_empty_steps(self):
        self.assert_rejected({"steps": []})

    def test_step_not_object(self):
        self.assert_rejected({"steps": ["wait"]})

    def test_depth_exceeded(self):
        steps = [{"type": "wait", "ms": 10}]
        for _ in range(MAX_DEPTH + 2):
            steps = [{"type": "loop", "count": 1, "steps": steps}]
        self.assert_rejected({"steps": steps})

    def test_step_cap(self):
        self.assert_rejected({"steps": [{"type": "wait", "ms": 10}] * (MAX_STEPS + 1)})

    def test_expansion_cap(self):
        # 1 個 loop × 10,000 × 內層 100 wait = 1,000,100 > 上限
        inner = [{"type": "wait", "ms": 10}] * 100
        steps = [{"type": "loop", "count": scripting.MAX_LOOP, "steps": inner}]
        script, errors, _ = parse_script({"steps": steps})
        self.assertIsNone(script)

    def test_non_string_name(self):
        self.assert_rejected({"name": 123,
                              "steps": [{"type": "wait", "ms": 10}]})


class TestKeyWhitelist(unittest.TestCase):
    def test_alnum(self):
        self.assertEqual(parse_key("a"), ord("A"))
        self.assertEqual(parse_key("5"), ord("5"))

    def test_fkey(self):
        self.assertIsNotNone(parse_key("F12"))

    def test_rejects(self):
        self.assertIsNone(parse_key("ctrl"))
        self.assertIsNone(parse_key(None))
        self.assertIsNone(parse_key("AB"))
        self.assertIsNone(parse_key(""))


class TestFileIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "script.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        raw = {"version": 1, "name": "存取",
               "steps": [{"type": "wait", "ms": 20}]}
        script, errors, _ = parse_script(raw)
        self.assertEqual(errors, [])
        save_script(script, self.path)
        loaded, errors2, _ = load_script(self.path)
        self.assertEqual(errors2, [])
        self.assertEqual(loaded["steps"][0]["ms"], 20)
        self.assertEqual(loaded["name"], "存取")

    def test_bad_json(self):
        self.path.write_bytes(b"{broken")
        script, errors, _ = load_script(self.path)
        self.assertIsNone(script)
        self.assertTrue(errors)

    def test_oversized(self):
        self.path.write_bytes(b" " * (scripting.MAX_FILE_BYTES + 1))
        script, errors, _ = load_script(self.path)
        self.assertIsNone(script)

    def test_utf8_bom(self):
        data = json.dumps({"version": 1, "name": "b",
                           "steps": [{"type": "wait", "ms": 10}]},
                          ensure_ascii=False).encode("utf-8-sig")
        self.path.write_bytes(data)
        script, errors, _ = load_script(self.path)
        self.assertEqual(errors, [])
        self.assertIsNotNone(script)

    def test_missing_file(self):
        script, errors, _ = load_script(Path(self.tmp.name) / "nope.json")
        self.assertIsNone(script)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
