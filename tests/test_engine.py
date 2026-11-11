# -*- coding: utf-8 -*-
"""引擎流程測試（不注入任何滑鼠輸入）：順序模式、停止條件、狀態。"""
from __future__ import annotations

import threading
import unittest
from unittest import mock

from autoclicker import engine
from autoclicker.config import GlobalConfig, PointConfig, Settings


def make_settings(**gkw) -> Settings:
    return Settings(
        points=[PointConfig(name=f"p{i}", x=10 * i, y=10 * i)
                for i in range(3)],
        config=GlobalConfig(**gkw),
    )


class TestOrder(unittest.TestCase):
    def setUp(self):
        self.eng = engine.ClickEngine()

    def test_sequential_keeps_order(self):
        s = make_settings(order="sequential")
        names = [p.name for p in self.eng._order_points(s.points, s.config)]
        self.assertEqual(names, ["p0", "p1", "p2"])

    def test_random_is_permutation(self):
        s = make_settings(order="random")
        names = [p.name for p in self.eng._order_points(s.points, s.config)]
        self.assertEqual(sorted(names), ["p0", "p1", "p2"])

    def test_weighted_covers_domain(self):
        s = make_settings(order="weighted")
        s.points[0].weight = 100
        names = [p.name for p in self.eng._order_points(s.points, s.config)]
        for name in names:
            self.assertIn(name, {"p0", "p1", "p2"})

    def test_weighted_bias(self):
        s = make_settings(order="weighted")
        s.points[0].weight = 1000
        s.points[1].weight = 1
        s.points[2].weight = 1
        counts = {"p0": 0, "p1": 0, "p2": 0}
        for _ in range(200):
            for p in self.eng._order_points(s.points, s.config):
                counts[p.name] += 1
        self.assertGreater(counts["p0"], counts["p1"] * 10)


class TestStopCondition(unittest.TestCase):
    def setUp(self):
        self.eng = engine.ClickEngine()

    def test_repeats(self):
        g = GlobalConfig(stop_mode="repeats", total_repeats=50)
        self.eng._clicks = 49
        self.assertFalse(self.eng._stop_reached(g))
        self.eng._clicks = 50
        self.assertTrue(self.eng._stop_reached(g))

    def test_time(self):
        g = GlobalConfig(stop_mode="time", total_time_sec=1)
        import time
        self.eng._start_time = time.perf_counter() - 2
        self.assertTrue(self.eng._stop_reached(g))
        self.eng._start_time = time.perf_counter()
        self.assertFalse(self.eng._stop_reached(g))

    def test_manual_never(self):
        g = GlobalConfig(stop_mode="manual")
        self.eng._clicks = 10 ** 9
        self.assertFalse(self.eng._stop_reached(g))


class TestLifecycle(unittest.TestCase):
    def test_idle_status(self):
        eng = engine.ClickEngine()
        st = eng.status()
        self.assertEqual(st.state, "idle")
        self.assertEqual(st.clicks, 0)

    def test_toggle_pause_not_running(self):
        self.assertFalse(engine.ClickEngine().toggle_pause())

    def test_stop_without_start(self):
        engine.ClickEngine().stop()

    def test_no_enabled_points_errors(self):
        errors = []
        done = threading.Event()
        s = make_settings()
        s.points[0].enabled = False
        s.points[1].enabled = False
        s.points[2].enabled = False

        eng = engine.ClickEngine(on_error=errors.append,
                                 on_finished=lambda st: done.set())
        self.assertTrue(eng.start(s))
        self.assertTrue(done.wait(5.0),
                        "無啟用點位時應立即結束並回報")
        self.assertTrue(any("沒有啟用的點位" in e for e in errors))
        self.assertFalse(eng.is_running())

    def test_double_start_rejected(self):
        eng = engine.ClickEngine()
        holder = threading.Event()
        eng._thread = threading.Thread(
            target=lambda: holder.wait(2.0), daemon=True,
            name="fake-engine")
        eng._thread.start()
        try:
            self.assertTrue(eng.is_running())
            self.assertFalse(eng.start(make_settings()))
        finally:
            holder.set()
            eng.stop()


class TestPressDelay(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(engine.press_delay_ms(0), 0)
        self.assertEqual(engine.press_delay_ms(-5), 0)

    def test_default_range(self):
        for _ in range(500):
            v = engine.press_delay_ms(8)
            self.assertGreaterEqual(v, 8)
            self.assertLessEqual(v, 11)

    def test_clamped_to_50(self):
        for _ in range(500):
            v = engine.press_delay_ms(999)
            self.assertGreaterEqual(v, 50)
            self.assertLessEqual(v, 53)


class TestCornerCheck(unittest.TestCase):
    def tearDown(self):
        engine.set_corner_suppressed(False)

    def _check_at(self, pos, corner="top-left", size=3):
        with mock.patch.object(engine.win32, "get_cursor_pos",
                               return_value=pos), \
             mock.patch.object(engine.win32, "_virtual_rect",
                               return_value=(0, 0, 1920, 1080)):
            return engine.make_corner_check(corner, size)()

    def test_triggers_in_corner(self):
        self.assertTrue(self._check_at((0, 0)))
        self.assertTrue(self._check_at((2, 2)))

    def test_not_in_corner(self):
        self.assertFalse(self._check_at((100, 100)))

    def test_tolerance_min_two_px(self):
        # size=1 應被提高到 2px：(1,1) 會觸發、(2,2) 不會
        self.assertTrue(self._check_at((1, 1), size=1))
        self.assertFalse(self._check_at((2, 2), size=1))

    def test_suppressed(self):
        engine.set_corner_suppressed(True)
        self.assertFalse(self._check_at((0, 0)))
        engine.set_corner_suppressed(False)
        self.assertTrue(self._check_at((0, 0)))

    def test_bottom_right(self):
        self.assertTrue(self._check_at((1919, 1079), corner="bottom-right"))
        self.assertFalse(self._check_at((1916, 1079), corner="bottom-right"))


class TestButtonRelease(unittest.TestCase):
    """任何例外/停止都必須送出對應的 button-up（不真的注入輸入）。"""

    def test_release_when_wait_raises_after_press(self):
        class BoomSleeper:
            def __init__(self):
                self.calls = 0

            def wait(self, ms):
                self.calls += 1
                if self.calls >= 3:
                    raise RuntimeError("boom")
                return True

        eng = engine.ClickEngine()
        point = PointConfig(name="x", x=10, y=10)
        g = GlobalConfig(move_mode="teleport", press_delay_ms=8)
        with mock.patch.object(engine.win32, "move_to"), \
             mock.patch.object(engine.win32, "mouse_down") as md, \
             mock.patch.object(engine.win32, "mouse_up") as mu, \
             mock.patch.object(engine.win32, "_virtual_rect",
                               return_value=(0, 0, 1920, 1080)):
            with self.assertRaises(RuntimeError):
                eng._one_click(point, g, BoomSleeper())
        md.assert_called_once_with("left")
        mu.assert_called_once_with("left")
        self.assertIsNone(eng._held)

    def test_run_finally_releases_held_button(self):
        eng = engine.ClickEngine()
        eng._held = "right"
        eng._start_time = 1.0
        with mock.patch.object(eng, "_loop", side_effect=RuntimeError("x")), \
             mock.patch.object(engine.win32, "mouse_up") as mu:
            eng._run()
        mu.assert_called_once_with("right")
        self.assertIsNone(eng._held)

    def test_script_press_releases_on_exception(self):
        from autoclicker import scripting

        class BoomSleeper:
            def wait(self, ms):
                raise RuntimeError("boom")

        runner = scripting.ScriptRunner()
        with mock.patch.object(scripting.win32, "mouse_down") as md, \
             mock.patch.object(scripting.win32, "mouse_up") as mu:
            with self.assertRaises(RuntimeError):
                runner._press("left", 50, BoomSleeper())
        md.assert_called_once_with("left")
        mu.assert_called_once_with("left")


if __name__ == "__main__":
    unittest.main()
