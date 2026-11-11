"""簡易腳本：宣告式 JSON 步驟，嚴格 schema 驗證，受限直譯器。

絕不執行任意程式碼：無 eval / exec / subprocess / pickle / 動態 import。
解析時檢查型別、範圍、字串長度、巢狀深度、總步驟數與展開後動作數上限。
"""
from __future__ import annotations

import json
import os
import re
import string
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from . import win32
from .engine import EngineStatus, Sleeper, make_corner_check, move_with_mode

MAX_STEPS = 1_000
MAX_EXPANDED_ACTIONS = 1_000_000
MAX_DEPTH = 5
MAX_WAIT_MS = 600_000
MIN_WAIT_MS = 10
MAX_STR_LEN = 256
MAX_HOLD_MS = 1_000
MAX_LOOP = 10_000
MAX_FILE_BYTES = 1_000_000

STEP_KEYS = {
    "click": {"type", "x", "y", "button", "double", "hold_ms"},
    "move": {"type", "x", "y", "mode"},
    "wait": {"type", "ms"},
    "press_key": {"type", "key", "hold_ms"},
    "loop": {"type", "count", "steps"},
    "if_pixel_color": {"type", "x", "y", "color", "tolerance", "steps", "else"},
}
BUTTONS = ("left", "right", "middle")
MOVE_MODES = ("teleport", "curve")
_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


def parse_key(name: object) -> int | None:
    """腳本按鍵名稱 → 虛擬鍵碼（含英數與 F 鍵等白名單）。"""
    if not isinstance(name, str):
        return None
    k = name.strip().upper()
    if k in win32.HOTKEY_NAMES:
        return win32.HOTKEY_NAMES[k]
    if len(k) == 1 and k in (string.ascii_uppercase + string.digits):
        return ord(k)
    return None


def _err(ctx: "_Ctx", index: int, message: str) -> None:
    ctx.errors.append(f"步驟 {index + 1}：{message}")


class _Ctx:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.count = 0


def _req_int(ctx: _Ctx, step: dict, index: int, key: str,
             lo: int, hi: int) -> int | None:
    value = step.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        _err(ctx, index, f"「{key}」需為整數")
        return None
    if value < lo or value > hi:
        _err(ctx, index, f"「{key}」超出範圍 [{lo}, {hi}]")
        return None
    return value


def _opt_int(ctx: _Ctx, step: dict, index: int, key: str,
             lo: int, hi: int, default: int) -> int:
    value = step.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        _err(ctx, index, f"「{key}」需為整數")
        return default
    if value < lo or value > hi:
        _err(ctx, index, f"「{key}」超出範圍 [{lo}, {hi}]")
        return default
    return value


def _opt_enum(ctx: _Ctx, step: dict, index: int, key: str,
              allowed: tuple[str, ...], default: str) -> str:
    value = step.get(key)
    if value is None:
        return default
    if not isinstance(value, str) or value not in allowed:
        _err(ctx, index, f"「{key}」需為 {'/'.join(allowed)}")
        return default
    return value


def _opt_bool(ctx: _Ctx, step: dict, index: int, key: str, default: bool) -> bool:
    value = step.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        _err(ctx, index, f"「{key}」需為 true/false")
        return default
    return value


def _opt_str(ctx: _Ctx, step: dict, index: int, key: str) -> str | None:
    value = step.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_STR_LEN:
        _err(ctx, index, f"「{key}」需為 1–{MAX_STR_LEN} 字字串")
        return None
    return value.strip()


def _parse_steps(steps: object, depth: int, ctx: _Ctx) -> list[dict]:
    if not isinstance(steps, list):
        ctx.errors.append("steps 需為陣列")
        return []
    if depth > MAX_DEPTH:
        ctx.errors.append(f"巢狀深度超過上限 {MAX_DEPTH}")
        return []
    out: list[dict] = []
    for i, raw in enumerate(steps):
        if ctx.count >= MAX_STEPS:
            ctx.errors.append(f"步驟總數超過上限 {MAX_STEPS}")
            return out
        ctx.count += 1
        if not isinstance(raw, dict):
            _err(ctx, i, "需為物件")
            continue
        stype = raw.get("type")
        if not isinstance(stype, str) or stype not in STEP_KEYS:
            _err(ctx, i, "type 需為 click/move/wait/press_key/loop/if_pixel_color")
            continue
        unknown = set(raw) - STEP_KEYS[stype]
        if unknown:
            _err(ctx, i, f"不支援的欄位：{', '.join(sorted(unknown))}")
            continue
        parsed = _parse_step(stype, raw, i, depth, ctx)
        if parsed is not None:
            out.append(parsed)
    return out


def _parse_step(stype: str, raw: dict, index: int, depth: int,
                ctx: _Ctx) -> dict | None:
    if stype == "click":
        x = _req_int(ctx, raw, index, "x", -1_000_000, 1_000_000)
        y = _req_int(ctx, raw, index, "y", -1_000_000, 1_000_000)
        button = _opt_enum(ctx, raw, index, "button", BUTTONS, "left")
        hold = _opt_int(ctx, raw, index, "hold_ms", 1, MAX_HOLD_MS, 50)
        if x is None or y is None:
            return None
        return {"type": "click", "x": x, "y": y, "button": button,
                "double": _opt_bool(ctx, raw, index, "double", False),
                "hold_ms": hold}

    if stype == "move":
        x = _req_int(ctx, raw, index, "x", -1_000_000, 1_000_000)
        y = _req_int(ctx, raw, index, "y", -1_000_000, 1_000_000)
        if x is None or y is None:
            return None
        return {"type": "move", "x": x, "y": y,
                "mode": _opt_enum(ctx, raw, index, "mode", MOVE_MODES, "teleport")}

    if stype == "wait":
        ms = _req_int(ctx, raw, index, "ms", MIN_WAIT_MS, MAX_WAIT_MS)
        return None if ms is None else {"type": "wait", "ms": ms}

    if stype == "press_key":
        key = _opt_str(ctx, raw, index, "key")
        vk = parse_key(key) if key is not None else None
        if vk is None:
            _err(ctx, index, "key 需為白名單內的按鍵（英數、F1–F24、SPACE…）")
            return None
        return {"type": "press_key", "key": key, "vk": vk,
                "hold_ms": _opt_int(ctx, raw, index, "hold_ms", 1, MAX_HOLD_MS, 50)}

    if stype == "loop":
        count = _req_int(ctx, raw, index, "count", 1, MAX_LOOP)
        if count is None:
            return None
        child = _parse_steps(raw.get("steps", []), depth + 1, ctx)
        if not child:
            ctx.warnings.append(f"步驟 {index + 1}：loop 內沒有步驟")
        return {"type": "loop", "count": count, "steps": child}

    if stype == "if_pixel_color":
        x = _req_int(ctx, raw, index, "x", -1_000_000, 1_000_000)
        y = _req_int(ctx, raw, index, "y", -1_000_000, 1_000_000)
        color_raw = _opt_str(ctx, raw, index, "color")
        rgb: tuple[int, int, int] | None = None
        if color_raw is not None:
            m = _COLOR_RE.match(color_raw)
            if m:
                rgb = (int(m.group(1)[0:2], 16), int(m.group(1)[2:4], 16),
                       int(m.group(1)[4:6], 16))
            else:
                _err(ctx, index, "color 需為 #RRGGBB 格式")
        if x is None or y is None or rgb is None:
            return None
        return {"type": "if_pixel_color", "x": x, "y": y, "color": rgb,
                "tolerance": _opt_int(ctx, raw, index, "tolerance", 0, 255, 10),
                "steps": _parse_steps(raw.get("steps", []), depth + 1, ctx),
                "else": _parse_steps(raw.get("else", []), depth + 1, ctx)}
    return None


def _estimate(steps: list[dict]) -> int:
    total = 0
    for s in steps:
        total += 1
        if s["type"] == "loop":
            total += s["count"] * _estimate(s["steps"])
        elif s["type"] == "if_pixel_color":
            total += _estimate(s["steps"]) + _estimate(s["else"])
    return total


def parse_script(raw: object) -> tuple[dict | None, list[str], list[str]]:
    """回傳（已驗證腳本或 None, 錯誤, 警告）。錯誤不為空時不可執行。"""
    ctx = _Ctx()
    if not isinstance(raw, dict):
        ctx.errors.append("腳本需為 JSON 物件")
        return None, ctx.errors, ctx.warnings
    unknown = set(raw) - {"version", "name", "steps"}
    if unknown:
        ctx.errors.append(f"不支援的頂層欄位：{', '.join(sorted(unknown))}")
    version = raw.get("version", 1)
    if version != 1:
        ctx.errors.append("僅支援 version 1")
    name = raw.get("name", "腳本")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_STR_LEN:
        ctx.errors.append("name 需為 1–256 字字串")
        name = None
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list):
        ctx.errors.append("steps 需為陣列")
        steps_raw = []
    steps = _parse_steps(steps_raw, 1, ctx)
    if not steps and not ctx.errors:
        ctx.errors.append("steps 不可為空")
    if ctx.count > MAX_STEPS:
        ctx.errors.append(f"步驟總數超過上限 {MAX_STEPS}")
    if ctx.errors:
        return None, ctx.errors, ctx.warnings
    script = {"version": 1, "name": name or "腳本", "steps": steps}
    if _estimate(steps) > MAX_EXPANDED_ACTIONS:
        ctx.errors.append("展開後的動作數超過上限 1,000,000，請降低迴圈次數")
        return None, ctx.errors, ctx.warnings
    return script, ctx.errors, ctx.warnings


def load_script(path: Path) -> tuple[dict | None, list[str], list[str]]:
    errors: list[str] = []
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"腳本檔超過 {MAX_FILE_BYTES // 1000} KB")
            return None, errors, []
    except OSError as exc:
        return None, [f"無法讀取腳本（{exc.strerror}）"], []
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, ["腳本內容不是有效的 JSON"], []
    return parse_script(raw)


def save_script(script: dict, path: Path) -> None:
    data = json.dumps({"version": script.get("version", 1),
                       "name": script.get("name", "腳本"),
                       "steps": script["steps"]},
                      ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".script-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class ScriptRunner:
    """腳本執行緒；與 ClickEngine 相同的停止/暫停/急停機制。"""

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
        self._script: dict | None = None
        self._clicks = 0
        self._start_time = 0.0
        self._current = ""

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, script: dict, corner: str = "top-left",
              corner_size: int = 3) -> bool:
        if self.is_running():
            return False
        self._stop.clear()
        self._pause.clear()
        self._clicks = 0
        self._current = ""
        self._script = script
        self._start_time = time.perf_counter()
        self._thread = threading.Thread(
            target=self._run, args=(make_corner_check(corner, corner_size),),
            daemon=True, name="autoclicker-script")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    def toggle_pause(self) -> bool:
        if not self.is_running():
            return False
        if self._pause.is_set():
            self._pause.clear()
        else:
            self._pause.set()
        self._emit(force=True)
        return True

    def _status(self, state: str | None = None) -> EngineStatus:
        s = state or ("paused" if self._pause.is_set() else "running")
        elapsed = time.perf_counter() - self._start_time if self._start_time else 0.0
        return EngineStatus(s, self._current, self._clicks, elapsed)

    def _emit(self, force: bool = False) -> None:
        if not self._on_status:
            return
        now = time.perf_counter()
        if force or now - getattr(self, "_last_emit", 0.0) >= 0.1:
            self._last_emit = now
            try:
                self._on_status(self._status())
            except Exception:
                pass

    def _run(self, corner_check) -> None:
        try:
            sleeper = Sleeper(self._stop, self._pause, corner_check)
            assert self._script is not None
            self._exec_steps(self._script["steps"], sleeper)
        except Exception as exc:
            self._safe_error(f"腳本錯誤：{exc}")
        finally:
            if self._on_finished:
                try:
                    self._on_finished(self._status("idle"))
                except Exception:
                    pass

    def _safe_error(self, message: str) -> None:
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:
                pass

    def _exec_steps(self, steps: list[dict], sleeper: Sleeper) -> bool:
        for step in steps:
            if self._stop.is_set():
                return False
            if not self._exec_step(step, sleeper):
                return False
        return True

    def _exec_step(self, step: dict, sleeper: Sleeper) -> bool:
        stype = step["type"]
        if stype == "click":
            self._current = f"click ({step['x']}, {step['y']})"
        elif stype == "move":
            self._current = f"move ({step['x']}, {step['y']})"
        elif stype == "wait":
            self._current = f"wait {step['ms']}ms"
        elif stype == "press_key":
            self._current = f"key {step['key']}"
        elif stype == "loop":
            self._current = f"loop ×{step['count']}"
        else:
            self._current = f"if_pixel ({step['x']}, {step['y']})"
        self._emit()
        try:
            # 明確分派，不使用 getattr(self, f"_do_{stype}") 這類動態屬性取用。
            if stype == "click":
                return self._do_click(step, sleeper)
            if stype == "move":
                return self._do_move(step, sleeper)
            if stype == "wait":
                return self._do_wait(step, sleeper)
            if stype == "press_key":
                return self._do_press_key(step, sleeper)
            if stype == "loop":
                return self._do_loop(step, sleeper)
            if stype == "if_pixel_color":
                return self._do_if_pixel_color(step, sleeper)
            self._safe_error(f"不支援的步驟類型：{stype}")
            return False
        except OSError as exc:
            self._safe_error(f"{stype} 失敗：{exc}")
            return False

    def _press(self, button: str, hold: int, sleeper: Sleeper) -> bool:
        win32.mouse_down(button)
        try:
            if not sleeper.wait(hold):
                return False
        finally:
            win32.mouse_up(button)
        return True

    def _do_click(self, step: dict, sleeper: Sleeper) -> bool:
        win32.move_to(step["x"], step["y"])
        clicks = 2 if step["double"] else 1
        for i in range(clicks):
            if not self._press(step["button"], step["hold_ms"], sleeper):
                return False
            self._clicks += 1
            self._emit()
            if i < clicks - 1:
                if not sleeper.wait(60):
                    return False
        return sleeper.wait(max(10, step["hold_ms"]))

    def _do_move(self, step: dict, sleeper: Sleeper) -> bool:
        return move_with_mode(step["x"], step["y"], step["mode"], sleeper)

    def _do_wait(self, step: dict, sleeper: Sleeper) -> bool:
        return sleeper.wait(step["ms"])

    def _do_press_key(self, step: dict, sleeper: Sleeper) -> bool:
        vk = step["vk"]
        win32.key_down(vk)
        try:
            if not sleeper.wait(step["hold_ms"]):
                return False
        finally:
            win32.key_up(vk)
        return sleeper.wait(max(10, step["hold_ms"]))

    def _do_loop(self, step: dict, sleeper: Sleeper) -> bool:
        for _ in range(step["count"]):
            if self._stop.is_set():
                return False
            if not self._exec_steps(step["steps"], sleeper):
                return False
        return True

    def _do_if_pixel_color(self, step: dict, sleeper: Sleeper) -> bool:
        pixel = win32.get_pixel(step["x"], step["y"])
        tol = step["tolerance"]
        matched = pixel is not None and all(
            abs(a - b) <= tol for a, b in zip(pixel, step["color"]))
        branch = step["steps"] if matched else step["else"]
        if matched:
            self._current += "（符合）"
        return self._exec_steps(branch, sleeper)
