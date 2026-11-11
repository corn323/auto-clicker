"""設定層：預設值、逐欄位 schema 驗證、%APPDATA% 原子讀寫。

設定檔一律視為不可信輸入：任何欄位型別錯誤、超出範圍或未知值，
都以預設值或夾限處理並回報警告，絕不崩潰。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import win32

APP_NAME = "AutoClicker"
FILE_NAME = "settings.json"
MAX_SETTING_FILE_BYTES = 1_000_000
MAX_POINTS = 100
NAME_MAX = 64

COORD_LIMIT = 1_000_000
RADIUS_MAX = 1_000
HOLD_MAX_MS = 5_000
INTERVAL_MIN_MS = 10
INTERVAL_MAX_MS = 3_600_000
REPEAT_MAX = 100_000
WEIGHT_MAX = 100
TOTAL_REPEATS_MAX = 10_000_000
TOTAL_TIME_MAX_SEC = 86_400
LONG_PAUSE_MAX_MS = 600_000
MIN_INTERVAL_MAX_MS = 5_000

BUTTONS = ("left", "right", "middle")
JITTER_MODES = ("uniform", "normal")
ORDER_MODES = ("sequential", "random", "weighted")
MOVE_MODES = ("teleport", "curve")
STOP_MODES = ("repeats", "time", "manual")
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

_BUTTON_LABELS = {"left": "左鍵", "right": "右鍵", "middle": "中鍵"}


@dataclass
class PointConfig:
    name: str = "點位"
    x: int = 0
    y: int = 0
    enabled: bool = True
    radius: int = 0
    hold_min_ms: int = 30
    hold_max_ms: int = 120
    interval_ms: int = 200
    jitter_pct: int = 20
    jitter_mode: str = "uniform"
    button: str = "left"
    double: bool = False
    repeat: int = 1
    weight: int = 1
    screen_index: int = 0
    screen_x: int = 0
    screen_y: int = 0
    screen_width: int = 0
    screen_height: int = 0
    screen_dpi: int = 96


@dataclass
class GlobalConfig:
    order: str = "sequential"
    move_mode: str = "curve"
    min_interval_ms: int = 10
    long_pause_chance: int = 3
    long_pause_min_ms: int = 300
    long_pause_max_ms: int = 1500
    stop_mode: str = "manual"
    total_repeats: int = 100
    total_time_sec: int = 60
    hotkey_start: str = "F8"
    hotkey_stop: str = "F9"
    hotkey_record: str = "F6"
    emergency_corner: str = "top-left"
    corner_size: int = 3
    corner_enabled: bool = True
    press_delay_ms: int = 8


@dataclass
class Settings:
    points: list[PointConfig] = field(default_factory=list)
    config: GlobalConfig = field(default_factory=GlobalConfig)
    monitor_layout: list[dict] = field(default_factory=list)


def _as_int(raw: object, default: int, lo: int, hi: int,
            label: str, warnings: list[str]) -> int:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        warnings.append(f"{label} 型別無效，已使用預設值 {default}")
        return default
    if isinstance(raw, float) and not float(raw).is_integer():
        warnings.append(f"{label} 需為整數，已取整")
    value = int(raw)
    if value < lo or value > hi:
        warnings.append(f"{label} 超出範圍 [{lo}, {hi}]，已調整")
    return max(lo, min(hi, value))


def _as_bool(raw: object, default: bool, label: str, warnings: list[str]) -> bool:
    if raw is None:
        return default
    if not isinstance(raw, bool):
        warnings.append(f"{label} 需為 true/false，已使用預設值 {default}")
        return default
    return raw


_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _as_str(raw: object, default: str, max_len: int,
            label: str, warnings: list[str]) -> str:
    if raw is None:
        return default
    if not isinstance(raw, str):
        warnings.append(f"{label} 需為字串，已使用預設值")
        return default
    value = _CTRL_RE.sub("", raw.strip())
    if len(value) > max_len:
        value = value[:max_len]
        warnings.append(f"{label} 過長，已截斷為 {max_len} 字")
    if not value:
        value = default
    return value


def _as_enum(raw: object, allowed: tuple[str, ...], default: str,
             label: str, warnings: list[str]) -> str:
    if raw is None:
        return default
    if not isinstance(raw, str) or raw.strip().lower() not in allowed:
        warnings.append(f"{label} 無效，已使用預設值「{default}」")
        return default
    return raw.strip().lower()


def _apply_ordered_pair(lo_value: int, hi_value: int,
                        lo_label: str, hi_label: str,
                        warnings: list[str]) -> tuple[int, int]:
    if lo_value > hi_value:
        warnings.append(f"{lo_label} 大於 {hi_label}，已互換")
        lo_value, hi_value = hi_value, lo_value
    return lo_value, hi_value


def sanitize_point(raw: object, index: int,
                   warnings: list[str] | None = None) -> PointConfig:
    """驗證單一點位，任何問題都夾限或回預設值。"""
    warnings = warnings if warnings is not None else []
    prefix = f"點位 {index + 1}"
    if not isinstance(raw, dict):
        if raw is not None:
            warnings.append(f"{prefix} 資料格式無效，已使用預設值")
        raw = {}
    p = PointConfig(
        name=_as_str(raw.get("name"), f"點位 {index + 1}", NAME_MAX,
                     f"{prefix} 名稱", warnings),
        x=_as_int(raw.get("x"), 0, -COORD_LIMIT, COORD_LIMIT,
                  f"{prefix} X", warnings),
        y=_as_int(raw.get("y"), 0, -COORD_LIMIT, COORD_LIMIT,
                  f"{prefix} Y", warnings),
        enabled=_as_bool(raw.get("enabled"), True, f"{prefix} 啟用", warnings),
        radius=_as_int(raw.get("radius"), 0, 0, RADIUS_MAX,
                       f"{prefix} 偏移半徑", warnings),
        hold_min_ms=_as_int(raw.get("hold_min_ms"), 30, 1, HOLD_MAX_MS,
                            f"{prefix} 按住下限", warnings),
        hold_max_ms=_as_int(raw.get("hold_max_ms"), 120, 1, HOLD_MAX_MS,
                            f"{prefix} 按住上限", warnings),
        interval_ms=_as_int(raw.get("interval_ms"), 200, INTERVAL_MIN_MS,
                            INTERVAL_MAX_MS, f"{prefix} 間隔", warnings),
        jitter_pct=_as_int(raw.get("jitter_pct"), 20, 0, 100,
                           f"{prefix} 隨機幅度", warnings),
        jitter_mode=_as_enum(raw.get("jitter_mode"), JITTER_MODES, "uniform",
                             f"{prefix} 分佈模式", warnings),
        button=_as_enum(raw.get("button"), BUTTONS, "left",
                        f"{prefix} 按鍵", warnings),
        double=_as_bool(raw.get("double"), False, f"{prefix} 雙擊", warnings),
        repeat=_as_int(raw.get("repeat"), 1, 1, REPEAT_MAX,
                       f"{prefix} 重複次數", warnings),
        weight=_as_int(raw.get("weight"), 1, 1, WEIGHT_MAX,
                       f"{prefix} 權重", warnings),
        screen_index=_as_int(raw.get("screen_index"), 0, 0, 15,
                             f"{prefix} 螢幕編號", warnings),
        screen_x=_as_int(raw.get("screen_x"), 0, -COORD_LIMIT, COORD_LIMIT,
                         f"{prefix} 螢幕 X", warnings),
        screen_y=_as_int(raw.get("screen_y"), 0, -COORD_LIMIT, COORD_LIMIT,
                         f"{prefix} 螢幕 Y", warnings),
        screen_width=_as_int(raw.get("screen_width"), 0, 0, 30000,
                             f"{prefix} 螢幕寬", warnings),
        screen_height=_as_int(raw.get("screen_height"), 0, 0, 30000,
                              f"{prefix} 螢幕高", warnings),
        screen_dpi=_as_int(raw.get("screen_dpi"), 96, 48, 1000,
                           f"{prefix} 螢幕 DPI", warnings),
    )
    p.hold_min_ms, p.hold_max_ms = _apply_ordered_pair(
        p.hold_min_ms, p.hold_max_ms,
        f"{prefix} 按住下限", f"{prefix} 按住上限", warnings)
    return p


def sanitize_global(raw: object, warnings: list[str]) -> GlobalConfig:
    if not isinstance(raw, dict):
        if raw is not None:
            warnings.append("全域設定格式無效，已使用預設值")
        raw = {}

    def hk(key: str, default: str) -> str:
        value = _as_str(raw.get(key), default, 8, f"熱鍵 {key}", warnings)
        if not win32.is_valid_hotkey(value):
            warnings.append(f"熱鍵 {key}「{value}」無效，已使用預設值 {default}")
            return default
        return value

    g = GlobalConfig(
        order=_as_enum(raw.get("order"), ORDER_MODES, "sequential", "執行順序", warnings),
        move_mode=_as_enum(raw.get("move_mode"), MOVE_MODES, "curve", "游標移動", warnings),
        min_interval_ms=_as_int(raw.get("min_interval_ms"), 10, INTERVAL_MIN_MS,
                                MIN_INTERVAL_MAX_MS, "最低間隔", warnings),
        long_pause_chance=_as_int(raw.get("long_pause_chance"), 3, 0, 100,
                                  "長停頓機率", warnings),
        long_pause_min_ms=_as_int(raw.get("long_pause_min_ms"), 300, 100,
                                  LONG_PAUSE_MAX_MS, "長停頓下限", warnings),
        long_pause_max_ms=_as_int(raw.get("long_pause_max_ms"), 1500, 100,
                                  LONG_PAUSE_MAX_MS, "長停頓上限", warnings),
        stop_mode=_as_enum(raw.get("stop_mode"), STOP_MODES, "manual", "停止條件", warnings),
        total_repeats=_as_int(raw.get("total_repeats"), 100, 1, TOTAL_REPEATS_MAX,
                              "總點擊次數", warnings),
        total_time_sec=_as_int(raw.get("total_time_sec"), 60, 1, TOTAL_TIME_MAX_SEC,
                               "總時間", warnings),
        hotkey_start=hk("hotkey_start", "F8"),
        hotkey_stop=hk("hotkey_stop", "F9"),
        hotkey_record=hk("hotkey_record", "F6"),
        emergency_corner=_as_enum(raw.get("emergency_corner"), CORNERS,
                                  "top-left", "急停角落", warnings),
        corner_size=_as_int(raw.get("corner_size"), 3, 2, 100, "急停角落大小", warnings),
        corner_enabled=_as_bool(raw.get("corner_enabled"), True,
                                "角落急停開關", warnings),
        press_delay_ms=_as_int(raw.get("press_delay_ms"), 8, 0, 50,
                               "按下前延遲", warnings),
    )
    g.long_pause_min_ms, g.long_pause_max_ms = _apply_ordered_pair(
        g.long_pause_min_ms, g.long_pause_max_ms,
        "長停頓下限", "長停頓上限", warnings)
    return g


def _sanitize_layout(raw: object, warnings: list[str]) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        warnings.append("螢幕配置資料無效，已忽略")
        return []
    layout: list[dict] = []
    for i, item in enumerate(raw[:16]):
        if not isinstance(item, dict):
            continue
        w: list[str] = []  # 配置項目再壞掉時整項丟棄
        entry = {
            "index": _as_int(item.get("index"), i, 0, 15, f"螢幕 {i}", w),
            "left": _as_int(item.get("left"), 0, -COORD_LIMIT, COORD_LIMIT, f"螢幕 {i} left", w),
            "top": _as_int(item.get("top"), 0, -COORD_LIMIT, COORD_LIMIT, f"螢幕 {i} top", w),
            "width": _as_int(item.get("width"), 0, 1, 30000, f"螢幕 {i} 寬", w),
            "height": _as_int(item.get("height"), 0, 1, 30000, f"螢幕 {i} 高", w),
            "dpi": _as_int(item.get("dpi"), 96, 48, 1000, f"螢幕 {i} DPI", w),
        }
        if not w:
            layout.append(entry)
    if len(raw) > 16:
        warnings.append("螢幕配置項目過多，僅保留前 16 個")
    return layout


def normalize_settings(raw: object, warnings: list[str] | None = None) -> Settings:
    warnings = warnings if warnings is not None else []
    if not isinstance(raw, dict):
        if raw is not None:
            warnings.append("設定檔結構無效，已回復預設值")
        raw = {}
    points_raw = raw.get("points")
    if not isinstance(points_raw, list):
        if points_raw is not None:
            warnings.append("點位列表格式無效，已回復為空")
        points_raw = []
    if len(points_raw) > MAX_POINTS:
        points_raw = points_raw[:MAX_POINTS]
        warnings.append(f"點位數量超過上限 {MAX_POINTS}，已截斷")
    points = [sanitize_point(item, i, warnings) for i, item in enumerate(points_raw)]
    return Settings(
        points=points,
        config=sanitize_global(raw.get("config"), warnings),
        monitor_layout=_sanitize_layout(raw.get("monitor_layout"), warnings),
    )


def point_to_dict(p: PointConfig) -> dict:
    return {
        "name": p.name, "x": p.x, "y": p.y, "enabled": p.enabled,
        "radius": p.radius, "hold_min_ms": p.hold_min_ms,
        "hold_max_ms": p.hold_max_ms, "interval_ms": p.interval_ms,
        "jitter_pct": p.jitter_pct, "jitter_mode": p.jitter_mode,
        "button": p.button, "double": p.double, "repeat": p.repeat,
        "weight": p.weight, "screen_index": p.screen_index,
        "screen_x": p.screen_x, "screen_y": p.screen_y,
        "screen_width": p.screen_width, "screen_height": p.screen_height,
        "screen_dpi": p.screen_dpi,
    }


def settings_to_dict(settings: Settings) -> dict:
    return {
        "version": 1,
        "points": [point_to_dict(p) for p in settings.points],
        "config": vars(settings.config).copy(),
        "monitor_layout": settings.monitor_layout,
    }


def default_settings() -> Settings:
    return Settings()


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME / FILE_NAME
    return Path.home() / ".autoclicker" / FILE_NAME


def load_settings(path: Path | None = None) -> tuple[Settings, list[str]]:
    path = path or settings_path()
    warnings: list[str] = []
    if not path.is_file():
        return default_settings(), warnings
    try:
        if path.stat().st_size > MAX_SETTING_FILE_BYTES:
            warnings.append(f"設定檔超過 {MAX_SETTING_FILE_BYTES // 1000} KB，已回復預設值")
            return default_settings(), warnings
    except OSError as exc:
        warnings.append(f"無法讀取設定檔（{exc.strerror}），已回復預設值")
        return default_settings(), warnings
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError):
        warnings.append("設定檔內容損壞，已回復預設值")
        return default_settings(), warnings
    except OSError as exc:
        warnings.append(f"無法讀取設定檔（{exc.strerror}），已回復預設值")
        return default_settings(), warnings
    return normalize_settings(raw, warnings), warnings


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    """原子寫入：先寫同目錄暫存檔，再 os.replace 覆蓋。"""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(settings_to_dict(settings), ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp",
                                    dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def button_label(button: str) -> str:
    return _BUTTON_LABELS.get(button, button)
