"""點擊引擎：擬人化偏移/間隔、貝茲曲線移動、可中斷等待、停止條件。

所有計時使用 time.perf_counter；所有等待都可被 stop_event 中斷（F9 ≤ 100ms），
並在角落急停時立即中止。隨機數來源為 secrets（作業系統亂數，無固定種子）。
"""
from __future__ import annotations

import copy
import math
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

from . import win32
from .config import GlobalConfig, PointConfig, Settings


@dataclass(frozen=True)
class EngineStatus:
    state: str      # running / paused / stopping / idle
    point: str
    clicks: int
    elapsed: float  # 秒


def _rand01() -> float:
    """(0, 1] 均勻亂數，來源為 secrets（OS 亂數）。"""
    return (secrets.randbits(53) + 1) / (1 << 53)


def normal_offset(radius: int) -> tuple[int, int]:
    """以常態分佈（sigma = radius/3，截斷於 radius）在圓形範圍內取偏移。"""
    if radius <= 0:
        return 0, 0
    u1, u2 = _rand01(), _rand01()
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    r = min(float(radius), abs(z) * radius / 3.0)
    theta = 2.0 * math.pi * _rand01()
    return int(round(r * math.cos(theta))), int(round(r * math.sin(theta)))


def jittered_interval(base_ms: int, pct: int, mode: str) -> int:
    """基礎間隔 ± 隨機百分比；均勻或常態（截斷 ±2σ）。"""
    if pct <= 0:
        return max(1, int(base_ms))
    amp = base_ms * pct / 100.0
    if mode == "normal":
        u1, u2 = _rand01(), _rand01()
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        z = max(-2.0, min(2.0, z))
        delta = z * amp / 2.5
    else:
        delta = (_rand01() * 2.0 - 1.0) * amp
    return max(1, int(round(base_ms + delta)))


def uniform_range(lo: int, hi: int) -> int:
    if hi <= lo:
        return lo
    return lo + int(_rand01() * (hi - lo + 1)) % (hi - lo + 1)


def _shuffle(items: list) -> list:
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def clamp_to_virtual(x: int, y: int) -> tuple[int, int]:
    vx, vy, vw, vh = win32._virtual_rect()
    return max(vx, min(x, vx + vw - 1)), max(vy, min(y, vy + vh - 1))


def curve_path(x0: int, y0: int, x1: int, y1: int,
               steps: int = 24) -> list[tuple[int, int]]:
    """三次貝茲路徑：隨機垂直偏移的控制點 + 每點 ±1px 抖動。"""
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < 1 or steps < 2:
        return [(x1, y1)]
    sign = 1.0 if secrets.randbelow(2) else -1.0
    nx, ny = -(y1 - y0) / dist, (x1 - x0) / dist
    off1 = sign * dist * (0.05 + _rand01() * 0.15)
    off2 = -sign * dist * (0.05 + _rand01() * 0.15)
    c1x, c1y = x0 + (x1 - x0) / 3 + nx * off1, y0 + (y1 - y0) / 3 + ny * off1
    c2x, c2y = x0 + 2 * (x1 - x0) / 3 + nx * off2, y0 + 2 * (y1 - y0) / 3 + ny * off2
    pts: list[tuple[int, int]] = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        bx = mt ** 3 * x0 + 3 * mt ** 2 * t * c1x + 3 * mt * t ** 2 * c2x + t ** 3 * x1
        by = mt ** 3 * y0 + 3 * mt ** 2 * t * c1y + 3 * mt * t ** 2 * c2y + t ** 3 * y1
        jx = jy = 0
        if i < steps:
            jx = secrets.randbelow(3) - 1
            jy = secrets.randbelow(3) - 1
        pts.append((int(round(bx)) + jx, int(round(by)) + jy))
    pts[-1] = (x1, y1)
    return pts


def press_delay_ms(base_ms: int) -> int:
    """按下前短延遲：設定值（0–50ms）加上 0–3ms 小幅隨機，避免節奏工整。"""
    base = max(0, min(50, int(base_ms)))
    if base <= 0:
        return 0
    return base + secrets.randbelow(4)


_corner_suppressed = threading.Event()


def set_corner_suppressed(on: bool) -> None:
    """暫停/恢復角落急停偵測（選取位置遮罩、錄製期間使用）。"""
    if on:
        _corner_suppressed.set()
    else:
        _corner_suppressed.clear()


def corner_suppressed() -> bool:
    return _corner_suppressed.is_set()


def make_corner_check(corner: str, size: int,
                      suppressed: Callable[[], bool] | None = None
                      ) -> Callable[[], bool]:
    """角落急停：游標進入角落 size×size 區域即回 True。

    suppressed 回 True 時（例如選取位置遮罩開啟）暫停偵測；
    容差強制至少 2px，避免誤觸。
    """
    size = max(2, int(size))

    def check() -> bool:
        if _corner_suppressed.is_set():
            return False
        if suppressed is not None and suppressed():
            return False
        try:
            x, y = win32.get_cursor_pos()
        except OSError:
            return False
        vx, vy, vw, vh = win32._virtual_rect()
        left = corner in ("top-left", "bottom-left")
        top = corner in ("top-left", "top-right")
        cx = x - vx if left else vx + vw - 1 - x
        cy = y - vy if top else vy + vh - 1 - y
        return cx < size and cy < size
    return check


class Sleeper:
    """可中斷等待：stop_event、pause_event（暫停時凍結）與角落急停。"""

    def __init__(self, stop_event: threading.Event,
                 pause_event: threading.Event | None = None,
                 corner_check: Callable[[], bool] | None = None,
                 poll: float = 0.05) -> None:
        self._stop = stop_event
        self._pause = pause_event
        self._corner = corner_check
        self._poll = poll

    def wait(self, ms: float) -> bool:
        """等待 ms 毫秒；被停止或角落急停時回 False（急停會設 stop_event）。"""
        deadline = time.perf_counter() + ms / 1000.0
        while True:
            if self._stop.is_set():
                return False
            if self._corner is not None and self._corner():
                self._stop.set()
                return False
            while (self._pause is not None and self._pause.is_set()
                   and not self._stop.is_set()):
                if self._corner is not None and self._corner():
                    self._stop.set()
                    return False
                self._stop.wait(self._poll)
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            self._stop.wait(min(self._poll, remaining))


def move_with_mode(x: int, y: int, mode: str, sleeper: Sleeper) -> bool:
    """移動游標：teleport 瞬移，或貝茲曲線（每步 5–14ms 隨機）。"""
    if not sleeper.wait(1):
        return False
    if mode == "teleport":
        win32.move_to(x, y)
        return True
    cx, cy = win32.get_cursor_pos()
    dist = math.hypot(x - cx, y - cy)
    if dist < 2:
        win32.move_to(x, y)
        return True
    steps = max(8, min(40, int(dist) // 15))
    for px, py in curve_path(cx, cy, x, y, steps):
        if not sleeper.wait(uniform_range(5, 14)):
            return False
        win32.move_to(px, py)
    return True


class ClickEngine:
    """在獨立執行緒執行點擊迴圈；UI 透過 callback 收狀態。"""

    def __init__(self,
                 on_status: Callable[[EngineStatus], None] | None = None,
                 on_error: Callable[[str], None] | None = None,
                 on_finished: Callable[[EngineStatus], None] | None = None) -> None:
        self._on_status = on_status
        self._on_error = on_error
        self._on_finished = on_finished
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._settings: Settings | None = None
        self._clicks = 0
        self._start_time = 0.0
        self._current = ""
        self._held: str | None = None
        self._last_emit = 0.0

    # ---- 生命週期 ----
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, settings: Settings) -> bool:
        if self.is_running():
            return False
        self._stop.clear()
        self._pause.clear()
        self._clicks = 0
        self._current = ""
        self._held = None
        self._start_time = time.perf_counter()
        self._settings = copy.deepcopy(settings)
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="autoclicker-engine")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()

    def toggle_pause(self) -> bool:
        """回 True 代表有切換；未執行中回 False。"""
        if not self.is_running():
            return False
        if self._pause.is_set():
            self._pause.clear()
        else:
            self._pause.set()
        self._emit(force=True)
        return True

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    # ---- 狀態 ----
    def status(self) -> EngineStatus:
        state = "idle"
        if self._thread is not None and self._thread.is_alive():
            state = "paused" if self._pause.is_set() else "running"
        elapsed = time.perf_counter() - self._start_time if self._start_time else 0.0
        return EngineStatus(state, self._current, self._clicks, elapsed)

    def _emit(self, force: bool = False, state: str | None = None) -> None:
        now = time.perf_counter()
        if not force and now - self._last_emit < 0.1:
            return
        self._last_emit = now
        st = self.status()
        if state:
            st = EngineStatus(state, st.point, st.clicks, st.elapsed)
        if self._on_status:
            try:
                self._on_status(st)
            except Exception:
                pass

    def _error(self, message: str) -> None:
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:
                pass

    # ---- 主迴圈 ----
    def _run(self) -> None:
        try:
            self._loop()
        except Exception as exc:  # 任何錯誤都回報且不靜默
            self._error(f"引擎錯誤：{exc}")
        finally:
            if self._held is not None:
                try:
                    win32.mouse_up(self._held)
                except OSError:
                    pass
                self._held = None
            if self._on_finished:
                try:
                    self._on_finished(EngineStatus(
                        "idle", self._current, self._clicks,
                        time.perf_counter() - self._start_time))
                except Exception:
                    pass

    def _stop_reached(self, g: GlobalConfig) -> bool:
        if g.stop_mode == "repeats":
            return self._clicks >= g.total_repeats
        if g.stop_mode == "time":
            return time.perf_counter() - self._start_time >= g.total_time_sec
        return False

    def _order_points(self, points: list[PointConfig],
                      g: GlobalConfig) -> list[PointConfig]:
        if g.order == "random":
            return _shuffle(points)
        if g.order == "weighted":
            picked: list[PointConfig] = []
            total = sum(max(1, p.weight) for p in points)
            for _ in range(len(points)):
                pick = secrets.randbelow(total)
                acc = 0
                for p in points:
                    acc += max(1, p.weight)
                    if pick < acc:
                        picked.append(p)
                        break
            return picked
        return list(points)

    def _loop(self) -> None:
        settings = self._settings
        assert settings is not None
        g = settings.config
        points = [p for p in settings.points if p.enabled]
        if not points:
            self._error("沒有啟用的點位，無法開始")
            return
        self._start_time = time.perf_counter()
        self._emit(force=True)
        corner = (make_corner_check(g.emergency_corner, g.corner_size)
                  if g.corner_enabled else None)
        sleeper = Sleeper(self._stop, self._pause, corner)
        while not self._stop.is_set():
            if self._stop_reached(g):
                break
            for point in self._order_points(points, g):
                if self._stop.is_set() or self._stop_reached(g):
                    break
                self._activate(point, g, sleeper)
        self._emit(force=True, state="stopping" if self._stop.is_set() else "idle")

    def _activate(self, point: PointConfig, g: GlobalConfig,
                  sleeper: Sleeper) -> None:
        self._current = point.name
        self._emit()
        for i in range(point.repeat):
            if self._stop.is_set() or self._stop_reached(g):
                return
            if not self._one_click(point, g, sleeper):
                return
            if i < point.repeat - 1:
                gap = max(g.min_interval_ms, jittered_interval(
                    point.interval_ms, point.jitter_pct, point.jitter_mode))
                if not sleeper.wait(gap):
                    return
        gap = max(g.min_interval_ms, jittered_interval(
            point.interval_ms, point.jitter_pct, point.jitter_mode))
        if not sleeper.wait(gap):
            return
        if _rand01() * 100.0 < g.long_pause_chance:
            sleeper.wait(uniform_range(g.long_pause_min_ms, g.long_pause_max_ms))

    def _one_click(self, point: PointConfig, g: GlobalConfig,
                   sleeper: Sleeper) -> bool:
        dx, dy = normal_offset(point.radius)
        tx, ty = clamp_to_virtual(point.x + dx, point.y + dy)
        if not move_with_mode(tx, ty, g.move_mode, sleeper):
            return False
        delay = press_delay_ms(g.press_delay_ms)
        if delay and not sleeper.wait(delay):
            return False
        clicks = 2 if point.double else 1
        for i in range(clicks):
            hold = uniform_range(point.hold_min_ms, point.hold_max_ms)
            win32.mouse_down(point.button)
            self._held = point.button
            try:
                if not sleeper.wait(hold):
                    return False
            finally:
                win32.mouse_up(point.button)
                self._held = None
            self._clicks += 1
            self._emit()
            if i < clicks - 1:
                dclick = win32.get_double_click_time()
                gap = min(120, max(30, dclick - 60))
                if not sleeper.wait(uniform_range(40, max(40, gap))):
                    return False
        interval = max(g.min_interval_ms, jittered_interval(
            point.interval_ms, point.jitter_pct, point.jitter_mode))
        return sleeper.wait(interval)
