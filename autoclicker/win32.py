"""Win32 層：DPI 感知、SendInput 注入、螢幕列舉、全域熱鍵、UIPI 探測。

僅使用 ctypes 標準函式庫，無任何第三方依賴。全程使用實體像素座標。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import queue
import threading
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:
    shcore = None

ULONG_PTR = ctypes.c_size_t

# ---- SendInput / 滑鼠旗標 ----
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002

BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# ---- 虛擬桌面 metrics ----
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# ---- 熱鍵 ----
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

HOTKEY_NAMES = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F, "F17": 0x80,
    "F18": 0x81, "F19": 0x82, "F20": 0x83, "F21": 0x84, "F22": 0x85,
    "F23": 0x86, "F24": 0x87,
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "INSERT": 0x2D, "DELETE": 0x2E,
    "HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PGDN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "PAUSE": 0x13, "SCROLL": 0x91,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class MSG(ctypes.Structure):
    _fields_ = [("hWnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    left: int
    top: int
    right: int
    bottom: int
    dpi: int
    primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC, ctypes.POINTER(wintypes.RECT), MonitorEnumProc,
    wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetDoubleClickTime.restype = wintypes.UINT
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wintypes.DWORD
advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD)]
advapi32.GetTokenInformation.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TokenElevation = 20
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1


def _virtual_rect() -> tuple[int, int, int, int]:
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return vx, vy, max(1, vw), max(1, vh)


def virtual_rect() -> tuple[int, int, int, int]:
    """虛擬桌面範圍（left, top, width, height），支援負座標。"""
    return _virtual_rect()


def _normalize_coord(value: int, origin: int, span: int) -> int:
    """實體像素 → 0–65535（VIRTUALDESK 正規化，支援負座標）。"""
    value = max(origin, min(value, origin + span - 1))
    return round((value - origin) * 65535 / (span - 1)) if span > 1 else 0


def enable_dpi_awareness() -> None:
    """設定 Per-Monitor DPI Awareness V2（依序 fallback 到較舊 API）。"""
    ctx = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if ctx is not None:
        ctx.argtypes = [ctypes.c_void_p]
        ctx.restype = wintypes.BOOL
        if ctx(ctypes.c_void_p(-4)):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            return
    if shcore is not None and hasattr(shcore, "SetProcessDpiAwareness"):
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        if shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
            return
    user32.SetProcessDPIAware()


def _check_sent(sent: int, api: str) -> None:
    if sent != 1:
        err = ctypes.get_last_error()
        raise OSError(
            err,
            f"{api} 注入失敗（Win32 錯誤 {err}）。"
            "若目標程式以系統管理員執行而本工具不是，輸入會被 UIPI 封鎖。")


def move_to(x: int, y: int) -> None:
    """用 SendInput 將游標移到實體像素座標（虛擬桌面正規化）。"""
    vx, vy, vw, vh = _virtual_rect()
    nx = _normalize_coord(x, vx, vw)
    ny = _normalize_coord(y, vy, vh)
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(nx, ny, 0,
                        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE |
                        MOUSEEVENTF_VIRTUALDESK, 0, 0)
    _check_sent(user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)), "move_to")


def _mouse_event(flags: int, data: int = 0) -> None:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, data, flags, 0, 0)
    _check_sent(user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)), "mouse_event")


def mouse_down(button: str) -> None:
    _mouse_event(BUTTON_FLAGS[button][0])


def mouse_up(button: str) -> None:
    _mouse_event(BUTTON_FLAGS[button][1])


def release_all_buttons() -> None:
    """無論發生什麼錯誤，都送出三個按鍵的放開事件。"""
    for flags in (MOUSEEVENTF_LEFTUP, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_MIDDLEUP):
        try:
            _mouse_event(flags)
        except OSError:
            pass


def key_down(vk: int) -> None:
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(vk, 0, 0, 0, 0)
    _check_sent(user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)), "key_down")


def key_up(vk: int) -> None:
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
    _check_sent(user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)), "key_up")


def click_once(x: int, y: int, button: str, hold_ms: float) -> None:
    """測試用：移到座標並完整點擊一次。"""
    import time
    move_to(x, y)
    mouse_down(button)
    try:
        time.sleep(max(0.001, hold_ms / 1000.0))
    finally:
        mouse_up(button)


def get_cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return 0, 0
    return pt.x, pt.y


def get_double_click_time() -> int:
    return int(user32.GetDoubleClickTime())


def get_pixel(x: int, y: int) -> tuple[int, int, int] | None:
    hdc = user32.GetDC(None)
    if not hdc:
        return None
    try:
        c = gdi32.GetPixel(hdc, x, y)
        if c == 0xFFFFFFFF:  # CLR_INVALID
            return None
        return c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF
    finally:
        user32.ReleaseDC(None, hdc)


def set_window_pos(hwnd: int, x: int, y: int, w: int, h: int) -> bool:
    """以實體像素設定視窗位置與大小（支援負座標）；成功回 True。"""
    return bool(user32.SetWindowPos(
        wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST), x, y, w, h,
        SWP_NOACTIVATE | SWP_SHOWWINDOW))


def _monitor_dpi(hmon: wintypes.HMONITOR) -> int:
    if shcore is not None and hasattr(shcore, "GetDpiForMonitor"):
        try:
            dpi_x = wintypes.UINT()
            dpi_y = wintypes.UINT()
            fn = shcore.GetDpiForMonitor
            fn.argtypes = [wintypes.HMONITOR, ctypes.c_int,
                           ctypes.POINTER(wintypes.UINT),
                           ctypes.POINTER(wintypes.UINT)]
            if fn(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                return int(dpi_x.value)
        except (OSError, AttributeError):
            pass
    return 96


def list_monitors() -> list[MonitorInfo]:
    """列舉所有螢幕（依左上角排序，index 從 0 起）。"""
    monitors: list[MonitorInfo] = []

    def _cb(hmon, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            monitors.append(MonitorInfo(
                index=0,
                left=info.rcMonitor.left, top=info.rcMonitor.top,
                right=info.rcMonitor.right, bottom=info.rcMonitor.bottom,
                dpi=_monitor_dpi(hmon),
                primary=bool(info.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
    monitors.sort(key=lambda m: (m.left, m.top))
    return [
        MonitorInfo(i, m.left, m.top, m.right, m.bottom, m.dpi, m.primary)
        for i, m in enumerate(monitors)]


def monitor_signature(monitors: list[MonitorInfo]) -> list[dict]:
    return [
        {"index": m.index, "left": m.left, "top": m.top,
         "width": m.width, "height": m.height, "dpi": m.dpi}
        for m in monitors
    ]


def monitor_for_point(x: int, y: int,
                      monitors: list[MonitorInfo] | None = None) -> MonitorInfo | None:
    """找出包含座標的螢幕；都不包含時取中心最近者。"""
    ms = monitors if monitors is not None else list_monitors()
    if not ms:
        return None
    for m in ms:
        if m.left <= x < m.right and m.top <= y < m.bottom:
            return m
    cx, cy = x, y
    return min(ms, key=lambda m:
               abs((m.left + m.right) // 2 - cx) +
               abs((m.top + m.bottom) // 2 - cy))


def parse_hotkey(name: str) -> int | None:
    """熱鍵名稱 → 虛擬鍵碼；無效回 None。"""
    if not isinstance(name, str):
        return None
    return HOTKEY_NAMES.get(name.strip().upper())


def is_valid_hotkey(name: str) -> bool:
    return parse_hotkey(name) is not None


def _process_elevated(pid: int) -> bool | None:
    """查詢行程是否以管理員權限執行；無法判斷時回 None。"""
    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hproc:
        return None
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(hproc, TOKEN_QUERY, ctypes.byref(token)):
            return None
        elev = wintypes.DWORD(0)
        ret_len = wintypes.DWORD(0)
        ok = advapi32.GetTokenInformation(
            token, TokenElevation, ctypes.byref(elev),
            ctypes.sizeof(elev), ctypes.byref(ret_len))
        if not ok:
            return None
        return bool(elev.value)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(hproc)


def self_is_elevated() -> bool | None:
    return _process_elevated(kernel32.GetCurrentProcessId())


def foreground_elevation() -> tuple[bool | None, int]:
    """回傳（前景視窗行程是否提升權限, 行程 PID）。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _process_elevated(int(pid.value)), int(pid.value)


def error_text(code: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    n = kernel32.FormatMessageW(
        0x1000 | 0x0200, None, code, 0, buf, len(buf), None) \
        if hasattr(kernel32, "FormatMessageW") else 0
    return buf.value.strip() if n else f"Win32 錯誤 {code}"


class HotkeyManager:
    """全域熱鍵（RegisterHotKey + 執行緒訊息迴圈），事件送入 queue。"""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._tid = 0

    @property
    def queue(self) -> queue.Queue[str]:
        return self._queue

    def start(self, bindings: dict[str, str]) -> dict[str, str]:
        """註冊 {動作: 鍵名}；回傳 {動作: 失敗訊息}，空 dict 代表全部成功。"""
        self.stop()
        errors: dict[str, str] = {}
        ready = threading.Event()
        thread = threading.Thread(
            target=self._run, args=(dict(bindings), errors, ready), daemon=True)
        thread.start()
        self._thread = thread
        if not ready.wait(3.0):
            errors["*"] = "熱鍵執行緒啟動逾時"
        return errors

    def stop(self) -> None:
        if self._thread is not None and self._thread.is_alive() and self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(1.0)
        self._thread = None
        self._tid = 0

    def _run(self, bindings: dict[str, str], errors: dict[str, str],
             ready: threading.Event) -> None:
        self._tid = kernel32.GetCurrentThreadId()
        ids: dict[int, str] = {}
        for i, (action, name) in enumerate(bindings.items(), start=1):
            vk = parse_hotkey(name)
            if vk is None:
                errors[action] = f"無效熱鍵名稱「{name}」"
            elif not user32.RegisterHotKey(None, i, MOD_NOREPEAT, vk):
                err = ctypes.get_last_error()
                errors[action] = (
                    f"{name} 註冊失敗（{error_text(err)}），可能已被其他程式占用")
            else:
                ids[i] = action
        ready.set()
        if errors:
            for i in ids:
                user32.UnregisterHotKey(None, i)
            return
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                action = ids.get(int(msg.wParam))
                if action:
                    self._queue.put(action)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for i in ids:
            user32.UnregisterHotKey(None, i)
