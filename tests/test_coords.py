# -*- coding: utf-8 -*-
"""絕對座標正規化：實體像素 ↔ 0–65535 往返誤差 ≤ 1px（含負座標副螢幕）。"""
from __future__ import annotations

import unittest

from autoclicker.win32 import _normalize_coord

TOL = 1


def denormalize(n: int, origin: int, span: int) -> int:
    """測試端反算：0–65535 還原為實體像素（SendInput 的對應關係）。"""
    if span <= 1:
        return origin
    return origin + round(n * (span - 1) / 65535)


class TestRoundtrip(unittest.TestCase):
    def assert_roundtrip(self, origin: int, span: int) -> None:
        step = max(1, span // 97)
        samples = list(range(origin, origin + span, step))
        samples += [origin, origin + span // 2, origin + span - 1]
        for value in samples:
            n = _normalize_coord(value, origin, span)
            self.assertGreaterEqual(n, 0)
            self.assertLessEqual(n, 65535)
            restored = denormalize(n, origin, span)
            self.assertLessEqual(
                abs(restored - value), TOL,
                f"origin={origin} span={span} value={value} "
                f"n={n} restored={restored}")

    def test_1920(self):
        self.assert_roundtrip(0, 1920)

    def test_1080(self):
        self.assert_roundtrip(0, 1080)

    def test_2560(self):
        self.assert_roundtrip(0, 2560)

    def test_1440(self):
        self.assert_roundtrip(0, 1440)

    def test_negative_secondary_horizontal(self):
        self.assert_roundtrip(-1920, 1920)
        self.assert_roundtrip(-2560, 2560)

    def test_negative_secondary_vertical(self):
        self.assert_roundtrip(-1080, 1080)
        self.assert_roundtrip(-1440, 1440)

    def test_large_primary_4k(self):
        self.assert_roundtrip(0, 3840)
        self.assert_roundtrip(0, 2160)


class TestNormalizeEdges(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(_normalize_coord(0, 0, 1920), 0)
        self.assertEqual(_normalize_coord(1919, 0, 1920), 65535)

    def test_clamped_below_and_above(self):
        self.assertEqual(_normalize_coord(-100, 0, 1920), 0)
        self.assertEqual(_normalize_coord(99999, 0, 1920), 65535)

    def test_negative_origin_zero(self):
        self.assertEqual(_normalize_coord(-1920, -1920, 1920), 0)
        self.assertEqual(_normalize_coord(-1, -1920, 1920), 65535)

    def test_monotonic(self):
        values = [_normalize_coord(v, -1920, 1920) for v in range(-1920, -1)]
        self.assertEqual(values, sorted(values))

    def test_span_one(self):
        self.assertEqual(_normalize_coord(5, 5, 1), 0)


if __name__ == "__main__":
    unittest.main()
