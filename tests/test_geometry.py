# -*- coding: utf-8 -*-
"""引擎純函式測試：分佈、截斷、曲線路徑、可中斷等待。"""
from __future__ import annotations

import math
import threading
import unittest

from autoclicker import engine


class TestNormalOffset(unittest.TestCase):
    def test_within_radius(self):
        for radius in (0, 1, 5, 30, 120):
            for _ in range(2000):
                dx, dy = engine.normal_offset(radius)
                self.assertGreaterEqual(dx, -radius)
                self.assertLessEqual(dx, radius)
                self.assertGreaterEqual(dy, -radius)
                self.assertLessEqual(dy, radius)
                self.assertLessEqual(math.hypot(dx, dy), radius + 1)

    def test_zero_radius(self):
        self.assertEqual(engine.normal_offset(0), (0, 0))
        self.assertEqual(engine.normal_offset(-3), (0, 0))

    def test_mean_near_center(self):
        n = 20000
        sx = sy = 0.0
        for _ in range(n):
            dx, dy = engine.normal_offset(60)
            sx += dx
            sy += dy
        self.assertLess(abs(sx / n), 3.0)
        self.assertLess(abs(sy / n), 3.0)

    def test_not_all_zero(self):
        moved = sum(
            1 for _ in range(500) if engine.normal_offset(20) != (0, 0))
        self.assertGreater(moved, 300)


class TestJitteredInterval(unittest.TestCase):
    def test_uniform_bounds(self):
        for _ in range(3000):
            v = engine.jittered_interval(100, 20, "uniform")
            self.assertGreaterEqual(v, 80)
            self.assertLessEqual(v, 120)

    def test_normal_bounds(self):
        for _ in range(3000):
            v = engine.jittered_interval(100, 20, "normal")
            self.assertGreaterEqual(v, 80)
            self.assertLessEqual(v, 120)

    def test_zero_pct(self):
        self.assertEqual(engine.jittered_interval(100, 0, "uniform"), 100)

    def test_min_one(self):
        for _ in range(500):
            self.assertGreaterEqual(engine.jittered_interval(1, 50, "uniform"), 1)


class TestUniformRange(unittest.TestCase):
    def test_bounds_and_endpoints(self):
        seen = set()
        for _ in range(5000):
            v = engine.uniform_range(3, 7)
            self.assertTrue(3 <= v <= 7)
            seen.add(v)
        self.assertEqual(seen, {3, 4, 5, 6, 7})

    def test_reversed_returns_lo(self):
        self.assertEqual(engine.uniform_range(7, 3), 7)


class TestCurvePath(unittest.TestCase):
    def test_endpoints_and_length(self):
        pts = engine.curve_path(100, 100, 900, 500, steps=24)
        self.assertEqual(len(pts), 24)
        self.assertEqual(pts[-1], (900, 500))
        self.assertNotEqual(pts[0], (100, 100))

    def test_short_distance(self):
        self.assertEqual(engine.curve_path(5, 5, 5, 5, steps=24), [(5, 5)])

    def test_smoothness(self):
        pts = engine.curve_path(0, 0, 1000, 0, steps=24)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            self.assertLessEqual(math.hypot(x1 - x0, y1 - y0), 1000 / 8)


class TestSleeper(unittest.TestCase):
    def test_stop_before_wait(self):
        stop = threading.Event()
        stop.set()
        s = engine.Sleeper(stop)
        start = _now()
        self.assertFalse(s.wait(5000))
        self.assertLess(_now() - start, 1.0)

    def test_normal_wait(self):
        s = engine.Sleeper(threading.Event())
        start = _now()
        self.assertTrue(s.wait(120))
        self.assertGreaterEqual(_now() - start, 0.1)

    def test_pause_then_stop(self):
        stop = threading.Event()
        pause = threading.Event()
        pause.set()
        s = engine.Sleeper(stop, pause)
        result = []

        def run():
            result.append(s.wait(10000))

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(1.0)
        self.assertTrue(t.is_alive())  # 暫停中不可自行結束
        stop.set()
        t.join(1.0)
        self.assertFalse(t.is_alive())
        self.assertEqual(result, [False])

    def test_corner_trigger(self):
        stop = threading.Event()
        s = engine.Sleeper(stop, corner_check=lambda: True)
        self.assertFalse(s.wait(5000))
        self.assertTrue(stop.is_set())


def _now() -> float:
    import time
    return time.perf_counter()


if __name__ == "__main__":
    unittest.main()
