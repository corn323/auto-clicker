# -*- coding: utf-8 -*-
"""引擎流程測試（不注入任何滑鼠輸入）：順序模式、停止條件、狀態。"""
from __future__ import annotations

import threading
import unittest

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


if __name__ == "__main__":
    unittest.main()
