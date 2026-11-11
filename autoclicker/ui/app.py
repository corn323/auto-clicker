"""主視窗：啟動、主題、視窗記憶、熱鍵、執行控制與點位操作。"""
from __future__ import annotations

import copy
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from .. import scripting, win32
from ..config import (MAX_POINTS, PointConfig, Settings, sanitize_global,
                      sanitize_point, save_settings)
from ..engine import ClickEngine, EngineStatus, set_corner_suppressed
from . import strings as S
from .pages import GlobalPageMixin, PointsPanelMixin, StatusBarMixin
from .script_page import ScriptPageMixin
from .theme import DARK, THEMES, apply_styles, load_fonts
from .widgets import ScrollArea, Tooltip


class ScreenOverlay:
    """覆蓋整個虛擬桌面的半透明遮罩；點一下新增座標，Esc/右鍵取消。

    位置與尺寸一律以 Win32 虛擬桌面「實體像素」計算（virtual_rect +
    SetWindowPos），不依賴 Tk 的 DPI 縮放換算，確保負座標副螢幕與
    混合 DPI 下遮罩仍精準貼合；點擊座標同樣用 GetCursorPos 實體像素。
    """

    def __init__(self, root: tk.Tk, on_pick, on_cancel, fonts) -> None:
        self.on_pick = on_pick
        self.on_cancel = on_cancel
        vx, vy, vw, vh = win32.virtual_rect()
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-alpha", 0.38)
        self.top.configure(bg="#07090c")
        self.canvas = tk.Canvas(self.top, bg="#07090c", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.top.update_idletasks()
        hwnd = int(self.top.wm_frame(), 16)
        if not win32.set_window_pos(hwnd, vx, vy, vw, vh):
            self.top.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.top.update_idletasks()
        try:
            self.top.grab_set()
            self.top.focus_force()
        except tk.TclError:
            pass
        self._draw_monitors(vx, vy, vw, fonts)
        self.canvas.bind("<Button-1>", self._pick)
        self.canvas.bind("<Button-3>", self._cancel)
        self.top.bind("<Escape>", self._cancel)
        self.top.protocol("WM_DELETE_WINDOW", self._cancel)

    def _draw_monitors(self, vx: int, vy: int, vw: int, fonts) -> None:
        for m in win32.list_monitors():
            x0, y0 = m.left - vx, m.top - vy
            x1, y1 = x0 + m.width, y0 + m.height
            self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2,
                                         outline=DARK.accent, width=2)
            self.canvas.create_text(
                x0 + 14, y0 + 12, anchor="nw", fill=DARK.text,
                text=(f"螢幕 {m.index + 1}  {m.width}×{m.height}  {m.dpi} DPI"
                      + ("（主）" if m.primary else "")),
                font=fonts.section)
        self.canvas.create_text(
            vw // 2, 44, fill="#ffffff", text=S.OVERLAY_HINT,
            font=fonts.head)

    def _pick(self, _event=None) -> None:
        self._close()
        x, y = win32.get_cursor_pos()
        self.on_pick(x, y)

    def _cancel(self, _event=None) -> None:
        self._close()
        self.on_cancel()

    def _close(self) -> None:
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()


class App(PointsPanelMixin, GlobalPageMixin, ScriptPageMixin, StatusBarMixin):
    ORDER_LABELS = {"sequential": "依序", "random": "隨機",
                    "weighted": "加權隨機"}
    MOVE_LABELS = {"teleport": "瞬移", "curve": "曲線移動"}
    STOP_LABELS = {"manual": "手動熱鍵", "repeats": "總次數",
                   "time": "總時間"}
    JITTER_LABELS = {"uniform": "均勻", "normal": "常態"}
    CORNER_LABELS = {"top-left": "左上", "top-right": "右上",
                     "bottom-left": "左下", "bottom-right": "右下"}
    BUTTON_LABELS = {"left": "左鍵", "right": "右鍵", "middle": "中鍵"}
    APP_TITLE = S.APP_TITLE

    def __init__(self, root: tk.Tk, settings: Settings,
                 load_warnings: list[str]) -> None:
        self.root = root
        self.settings = settings
        self.q: queue.Queue = queue.Queue()
        self.hotkeys = win32.HotkeyManager()
        self.engine = ClickEngine(self._on_status, self._on_error,
                                  self._on_finished)
        self.script_runner = scripting.ScriptRunner(
            self._on_status, self._on_error, self._on_finished)
        self.overlay: ScreenOverlay | None = None
        self._sel_index: int | None = None
        self._drag_row: str | None = None
        self._save_job: str | None = None
        self._toast_job: str | None = None
        self._geom_job: str | None = None
        self._poll_job: str | None = None
        self._narrow = False
        self.monitors: list[win32.MonitorInfo] = []
        self._scroll_areas: list[ScrollArea] = []
        self._dpi = next((m.dpi for m in win32.list_monitors()
                          if m.primary), 96)
        self._px = lambda n: max(1, int(round(n * self._dpi / 96)))
        self.fonts = load_fonts(root)
        self.palette = THEMES.get(settings.theme, DARK)
        apply_styles(root, self.palette, self.fonts, self._px)
        self._make_vars()
        self._build()
        self._update_run_button()
        self.refresh_tree()
        self.refresh_monitor_info()
        self._update_hint()
        self._register_hotkeys()
        self._poll()
        if load_warnings:
            self.root.after(200, lambda: messagebox.showwarning(
                S.APP_TITLE,
                S.LOAD_WARNINGS.format(
                    warnings="\n".join(load_warnings[:10]))))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.root.after(60, self._sync_narrow)

    # ---- 標題列與版面 ----
    def _build(self) -> None:
        self.root.title(S.APP_TITLE)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._restore_window()

        header = ttk.Frame(self.root, style="Surface.TFrame",
                           padding=(self._px(16), self._px(10)))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=S.APP_TITLE,
                  style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.hint_label = ttk.Label(header, style="Hint.TLabel", text="")
        self.hint_label.grid(row=0, column=1, sticky="e",
                             padx=(self._px(12), self._px(12)))
        self.theme_btn = ttk.Button(
            header, text=(S.THEME_LIGHT if self.palette.name == "dark"
                          else S.THEME_DARK),
            style="Ghost.TButton", command=self._toggle_theme)
        self.theme_btn.grid(row=0, column=2, sticky="e")
        self._attach_tip(self.theme_btn, S.TIP_THEME)

        self.main = ttk.Frame(self.root, padding=(self._px(12), self._px(8)))
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.columnconfigure(0, weight=3, minsize=self._px(280))
        self.main.columnconfigure(1, weight=2, minsize=self._px(320))
        self.main.rowconfigure(0, weight=1)
        self._build_points_panel(self.main)
        self._build_notebook(self.main)
        self._build_status_bar()
        self._relayout()

    def _restore_window(self) -> None:
        width, height = S.WINDOW_DEFAULT
        min_w, min_h = S.WINDOW_MIN
        self.root.minsize(self._px(min_w), self._px(min_h))
        saved = self.settings.window
        if saved and self._window_reachable(saved):
            w = max(self._px(min_w), saved["width"])
            h = max(self._px(min_h), saved["height"])
            self.root.geometry(f"{w}x{h}+{saved['x']}+{saved['y']}")
            return
        w, h = self._px(width), self._px(height)
        monitors = win32.list_monitors()
        m = next((mon for mon in monitors if mon.primary),
                 monitors[0] if monitors else None)
        if m is None:
            self.root.geometry(f"{w}x{h}")
            return
        x = m.left + (m.width - w) // 2
        y = m.top + (m.height - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _window_reachable(self, saved: dict) -> bool:
        x, y = saved["x"], saved["y"]
        w, h = saved["width"], saved["height"]
        need_x, need_y = self._px(80), self._px(60)
        for m in win32.list_monitors():
            ix = min(x + w, m.left + m.width) - max(x, m.left)
            iy = min(y + h, m.top + m.height) - max(y, m.top)
            if ix >= need_x and iy >= need_y:
                return True
        return False

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        narrow = event.width < self._px(S.NARROW_WIDTH)
        if narrow != self._narrow:
            self._narrow = narrow
            self._relayout()
        self._schedule_geometry_save()

    def _sync_narrow(self) -> None:
        try:
            narrow = self.root.winfo_width() < self._px(S.NARROW_WIDTH)
        except tk.TclError:
            return
        if narrow != self._narrow:
            self._narrow = narrow
            self._relayout()

    def _relayout(self) -> None:
        m = self.main
        if self._narrow:
            m.columnconfigure(0, weight=1, minsize=0)
            m.columnconfigure(1, weight=0, minsize=0)
            m.rowconfigure(0, weight=2)
            m.rowconfigure(1, weight=3)
            self.points_panel.grid(row=0, column=0, columnspan=2,
                                   sticky="nsew",
                                   padx=0, pady=(0, self._px(8)))
            self.notebook.grid(row=1, column=0, columnspan=2,
                               sticky="nsew", padx=0, pady=0)
            self.tree.configure(displaycolumns=S.TREE_NARROW_COLUMNS)
        else:
            m.rowconfigure(1, weight=0)
            m.rowconfigure(0, weight=1)
            m.columnconfigure(0, weight=3, minsize=self._px(280))
            m.columnconfigure(1, weight=2, minsize=self._px(320))
            self.points_panel.grid(row=0, column=0, columnspan=1,
                                   sticky="nsew",
                                   padx=(0, self._px(8)), pady=0)
            self.notebook.grid(row=0, column=1, columnspan=1,
                               sticky="nsew", padx=0, pady=0)
            self.tree.configure(displaycolumns="#all")

    # ---- 主題 ----
    def _toggle_theme(self) -> None:
        self.settings.theme = ("light" if self.palette.name == "dark"
                               else "dark")
        self._apply_theme()
        self._schedule_save()

    def _apply_theme(self) -> None:
        self.palette = THEMES.get(self.settings.theme, DARK)
        t = self.palette
        apply_styles(self.root, t, self.fonts, self._px)
        for area in self._scroll_areas:
            area.apply_theme(t)
        self.script_text.configure(bg=t.surface, fg=t.text,
                                   insertbackground=t.text,
                                   highlightbackground=t.border,
                                   highlightcolor=t.accent)
        self.script_msg.configure(foreground=t.muted)
        self.theme_btn.configure(
            text=(S.THEME_LIGHT if t.name == "dark" else S.THEME_DARK))

    def _attach_tip(self, widget: tk.Misc, text: str) -> None:
        if text:
            Tooltip(widget, text, lambda: self.palette, self.fonts.small,
                    self._px)

    # ---- 元件狀態 ----
    def _make_vars(self) -> None:
        self.v_name = tk.StringVar()
        self.v_enabled = tk.BooleanVar(value=True)
        self.v_pos = tk.StringVar(value="—")
        self.v_screen = tk.StringVar(value="—")
        self.v_radius = tk.StringVar(value="0")
        self.v_hold_min = tk.StringVar(value="30")
        self.v_hold_max = tk.StringVar(value="120")
        self.v_interval = tk.StringVar(value="200")
        self.v_jitter = tk.StringVar(value="20")
        self.v_jitter_mode = tk.StringVar(
            value=self.JITTER_LABELS["uniform"])
        self.v_button = tk.StringVar(value=self.BUTTON_LABELS["left"])
        self.v_double = tk.BooleanVar(value=False)
        self.v_repeat = tk.StringVar(value="1")
        self.v_weight = tk.StringVar(value="1")
        self.v_order = tk.StringVar(value=self.ORDER_LABELS["sequential"])
        self.v_move = tk.StringVar(value=self.MOVE_LABELS["curve"])
        self.v_min_interval = tk.StringVar(value="10")
        self.v_pause_chance = tk.StringVar(value="3")
        self.v_pause_min = tk.StringVar(value="300")
        self.v_pause_max = tk.StringVar(value="1500")
        self.v_stop_mode = tk.StringVar(value=self.STOP_LABELS["manual"])
        self.v_total_repeats = tk.StringVar(value="100")
        self.v_total_time = tk.StringVar(value="60")
        self.v_hk_start = tk.StringVar(value="F8")
        self.v_hk_stop = tk.StringVar(value="F9")
        self.v_hk_record = tk.StringVar(value="F6")
        self.v_corner = tk.StringVar(value=self.CORNER_LABELS["top-left"])
        self.v_corner_size = tk.StringVar(value="3")
        self.v_corner_enabled = tk.BooleanVar(value=True)
        self.v_press_delay = tk.StringVar(value="8")

    def _build_notebook(self, parent: ttk.Frame) -> None:
        nb = ttk.Notebook(parent)
        self.notebook = nb
        nb.grid(row=0, column=1, sticky="nsew")
        point_area = ScrollArea(nb, self._px)
        point_area.inner.configure(padding=(self._px(14), self._px(10)))
        global_area = ScrollArea(nb, self._px)
        global_area.inner.configure(padding=(self._px(14), self._px(10)))
        script_tab = ttk.Frame(nb, padding=self._px(12))
        self._scroll_areas.extend((point_area, global_area))
        for area in (point_area, global_area):
            area.apply_theme(self.palette)
        nb.add(point_area, text=" " + S.TAB_POINTS + " ")
        nb.add(global_area, text=" " + S.TAB_GLOBAL + " ")
        nb.add(script_tab, text=" " + S.TAB_SCRIPT + " ")
        self._build_point_editor(point_area.inner)
        self._build_global_tab(global_area.inner)
        self._build_script_tab(script_tab)
        self._load_global_vars()

    @staticmethod
    def _key_of(labels: dict, display: str) -> str | None:
        for k, v in labels.items():
            if v == display:
                return k
        return None

    @staticmethod
    def _read_int_var(var: tk.StringVar, fallback: int) -> int:
        try:
            return int(str(var.get()).strip())
        except (ValueError, tk.TclError):
            return fallback

    def _update_hint(self) -> None:
        g = self.settings.config
        self.hint_label.configure(
            text=S.HINT.format(record=g.hotkey_record,
                               start=g.hotkey_start, stop=g.hotkey_stop),
            style="Hint.TLabel")
        self._refresh_empty()

    def _flash_status(self, text: str) -> None:
        """標題列短暫訊息（新增點位回饋），1.8 秒後恢復熱鍵提示。"""
        self.hint_label.configure(text=text, style="Toast.TLabel")
        if self._toast_job:
            try:
                self.root.after_cancel(self._toast_job)
            except tk.TclError:
                pass
        self._toast_job = self.root.after(1800, self._clear_toast)

    def _clear_toast(self) -> None:
        self._toast_job = None
        self._update_hint()

    # ---- 點位操作 ----
    def _next_name(self) -> str:
        names = {p.name for p in self.settings.points}
        n = len(self.settings.points) + 1
        while f"點位 {n}" in names:
            n += 1
        return f"點位 {n}"

    def _make_point(self, x: int, y: int) -> PointConfig | None:
        monitors = win32.list_monitors()
        m = win32.monitor_for_point(x, y, monitors)
        if m is None:
            messagebox.showwarning(S.APP_TITLE, S.DLG_NO_SCREEN)
            return None
        p = sanitize_point({
            "name": self._next_name(), "x": x, "y": y, "enabled": True,
            "screen_index": m.index, "screen_x": m.left, "screen_y": m.top,
            "screen_width": m.width, "screen_height": m.height,
            "screen_dpi": m.dpi,
        }, len(self.settings.points), [])
        self.settings.monitor_layout = win32.monitor_signature(monitors)
        return p

    def record_point(self, x: int | None = None, y: int | None = None) -> None:
        if self.overlay is not None:
            return
        set_corner_suppressed(True)
        try:
            if x is None or y is None:
                x, y = win32.get_cursor_pos()
            if len(self.settings.points) >= MAX_POINTS:
                messagebox.showwarning(
                    S.APP_TITLE, S.DLG_POINT_LIMIT.format(limit=MAX_POINTS))
                return
            p = self._make_point(x, y)
            if p is None:
                return
            self.settings.points.append(p)
            self._sel_index = len(self.settings.points) - 1
            self.refresh_tree()
            self._schedule_save()
            self.root.bell()
            self._flash_status(S.TOAST_ADDED.format(name=p.name, x=x, y=y))
        finally:
            set_corner_suppressed(False)

    def _pick_add(self) -> None:
        self._open_overlay("add")

    def _pick_edit(self) -> None:
        if self._sel_index is None:
            messagebox.showinfo(S.APP_TITLE, S.DLG_PICK_FIRST)
            return
        self._open_overlay("edit")

    def _open_overlay(self, mode: str) -> None:
        if self.overlay is not None:
            return

        def picked(x: int, y: int) -> None:
            self.overlay = None
            set_corner_suppressed(False)
            if mode == "add":
                self.record_point(x, y)
                return
            p = self._make_point(x, y)
            if p is not None and self._sel_index is not None:
                old = self.settings.points[self._sel_index]
                p.name, p.enabled = old.name, old.enabled
                p.radius = old.radius
                p.hold_min_ms, p.hold_max_ms = old.hold_min_ms, old.hold_max_ms
                p.interval_ms, p.jitter_pct = old.interval_ms, old.jitter_pct
                p.jitter_mode, p.button, p.double = (old.jitter_mode,
                                                     old.button, old.double)
                p.repeat, p.weight = old.repeat, old.weight
                self.settings.points[self._sel_index] = p
                self.refresh_tree()
                self._schedule_save()

        def cancelled() -> None:
            self.overlay = None
            set_corner_suppressed(False)

        set_corner_suppressed(True)
        try:
            self.overlay = ScreenOverlay(self.root, picked, cancelled,
                                         self.fonts)
        except tk.TclError:
            set_corner_suppressed(False)
            raise

    def _delete_point(self) -> None:
        if self._sel_index is None:
            return
        idx = self._sel_index
        del self.settings.points[idx]
        if self.settings.points:
            self._sel_index = min(idx, len(self.settings.points) - 1)
        else:
            self._sel_index = None
        self.refresh_tree()
        self._schedule_save()

    def _copy_point(self) -> None:
        if self._sel_index is None:
            return
        if len(self.settings.points) >= MAX_POINTS:
            messagebox.showwarning(
                S.APP_TITLE, S.DLG_POINT_LIMIT.format(limit=MAX_POINTS))
            return
        src = self.settings.points[self._sel_index]
        dup = copy.deepcopy(src)
        dup.name = self._next_name()
        dup.enabled = False
        self.settings.points.insert(self._sel_index + 1, dup)
        self._sel_index += 1
        self.refresh_tree()
        self._schedule_save()

    def _move_point(self, delta: int) -> None:
        if self._sel_index is None:
            return
        idx = self._sel_index
        new = idx + delta
        if new < 0 or new >= len(self.settings.points):
            return
        pts = self.settings.points
        pts[idx], pts[new] = pts[new], pts[idx]
        self._sel_index = new
        self.refresh_tree()
        self._schedule_save()

    def _tree_press(self, event) -> None:
        self._drag_row = self.tree.identify_row(event.y) or None

    def _tree_motion(self, event) -> None:
        if not self._drag_row:
            return
        target = self.tree.identify_row(event.y)
        if target and target != self._drag_row:
            self.tree.move(self._drag_row, "", self.tree.index(target))

    def _tree_release(self, _event) -> None:
        if not self._drag_row:
            return
        self._drag_row = None
        order = [int(iid[1:]) for iid in self.tree.get_children()]
        if order != list(range(len(order))):
            self.settings.points = [self.settings.points[i] for i in order]
            self._schedule_save()
        sel = self.tree.selection()
        self._sel_index = int(sel[0][1:]) if sel else None
        self.refresh_tree()

    def _tree_toggle_enabled(self, _event=None) -> str:
        if self._sel_index is None:
            return "break"
        p = self.settings.points[self._sel_index]
        p.enabled = not p.enabled
        self.refresh_tree()
        self._schedule_save()
        return "break"

    # ---- 螢幕 ----
    def _layout_matches(self) -> bool:
        if not self.settings.monitor_layout:
            return True
        return win32.monitor_signature(self.monitors) == self.settings.monitor_layout

    def _recalibrate(self) -> None:
        self.refresh_monitor_info()
        for p in self.settings.points:
            m = win32.monitor_for_point(p.x, p.y, self.monitors)
            if m is not None:
                p.screen_index, p.screen_x, p.screen_y = (
                    m.index, m.left, m.top)
                p.screen_width, p.screen_height = m.width, m.height
                p.screen_dpi = m.dpi
        self.settings.monitor_layout = win32.monitor_signature(self.monitors)
        self.refresh_tree()
        self._schedule_save()
        messagebox.showinfo(S.APP_TITLE, S.DLG_RECALIBRATED)

    # ---- 執行控制 ----
    def toggle_run(self) -> None:
        if self.engine.is_running():
            self.engine.toggle_pause()
            return
        if self.script_runner.is_running():
            self.script_runner.toggle_pause()
            return
        self.start_engine()

    def start_engine(self) -> None:
        if self.engine.is_running() or self.script_runner.is_running():
            return
        if not any(p.enabled for p in self.settings.points):
            messagebox.showinfo(
                S.APP_TITLE,
                S.DLG_NO_ENABLED.format(
                    record=self.settings.config.hotkey_record))
            return
        self._apply_global()
        if not self._layout_matches():
            if not messagebox.askyesno(S.APP_TITLE, S.DLG_LAYOUT_CHANGED):
                return
        elevated, pid = win32.foreground_elevation()
        if elevated and not win32.self_is_elevated():
            if not messagebox.askyesno(
                    S.APP_TITLE, S.DLG_ELEVATED.format(pid=pid)):
                return
        self.engine.start(self.settings)
        self._update_run_button()

    def stop_all(self) -> None:
        self.engine.stop()
        self.script_runner.stop()
        win32.release_all_buttons()
        self._update_run_button()

    def _update_run_button(self) -> None:
        engine_on = self.engine.is_running()
        script_on = self.script_runner.is_running()
        g = self.settings.config
        if engine_on or script_on:
            paused = (self.engine.paused if engine_on
                      else self.script_runner.paused)
            text = (S.BTN_RESUME if paused else S.BTN_PAUSE).format(
                hotkey=g.hotkey_start)
            self.stop_btn.configure(style="Danger.TButton")
        else:
            text = S.BTN_START.format(hotkey=g.hotkey_start)
            self.stop_btn.configure(style="TButton")
        self.start_btn.configure(text=text)
        self.stop_btn.configure(text=S.BTN_STOP.format(hotkey=g.hotkey_stop))

    # ---- 熱鍵 ----
    def _register_hotkeys(self, bindings: dict[str, str] | None = None) -> bool:
        if bindings is None:
            g = self.settings.config
            bindings = {"start": g.hotkey_start, "stop": g.hotkey_stop,
                        "record": g.hotkey_record}
        errors = self.hotkeys.start(bindings)
        if errors:
            detail = "\n".join(f"{k}：{v}" for k, v in errors.items())
            messagebox.showerror(
                S.APP_TITLE, S.DLG_HOTKEY_FAILED.format(detail=detail))
            return False
        return True

    def _apply_hotkeys(self) -> None:
        g = self.settings.config
        old = (g.hotkey_start, g.hotkey_stop, g.hotkey_record)
        g.hotkey_start = str(self.v_hk_start.get()).strip().upper()
        g.hotkey_stop = str(self.v_hk_stop.get()).strip().upper()
        g.hotkey_record = str(self.v_hk_record.get()).strip().upper()
        self.settings.config = sanitize_global(vars(g), [])
        self._load_global_vars()
        if not self._register_hotkeys():
            g.hotkey_start, g.hotkey_stop, g.hotkey_record = old
            self.settings.config = sanitize_global(vars(g), [])
            self._register_hotkeys()
        self._load_global_vars()
        self._update_run_button()
        self._update_hint()
        self._schedule_save()

    # ---- 狀態與訊息 ----
    def _on_status(self, st: EngineStatus) -> None:
        self.q.put(("status", st))

    def _on_error(self, msg: str) -> None:
        self.q.put(("error", msg))

    def _on_finished(self, st: EngineStatus) -> None:
        self.q.put(("finished", st))

    def _show_status(self, st: EngineStatus) -> None:
        state = st.state
        if state == "idle" and st.clicks:
            state = "stopped"
        self.state_label.configure(text=S.STATE_LABELS[state],
                                   style=S.STATE_STYLES[state])
        self.point_value.configure(
            text=st.point or "—",
            style=("Value.TLabel" if st.point else "ValueMuted.TLabel"))
        self.clicks_value.configure(text=str(st.clicks))
        total = int(st.elapsed)
        self.time_value.configure(text=f"{total // 60:02d}:{total % 60:02d}")
        self._update_run_button()

    def _show_error(self, message: str) -> None:
        self._update_run_button()
        messagebox.showerror(S.APP_TITLE, message)

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "status":
                    self._show_status(data)
                elif kind == "error":
                    self._show_error(data)
                elif kind == "finished":
                    self._show_status(data)
        except queue.Empty:
            pass
        try:
            while True:
                action = self.hotkeys.queue.get_nowait()
                if action == "record":
                    self.record_point()
                elif action == "start":
                    self.toggle_run()
                elif action == "stop":
                    self.stop_all()
        except queue.Empty:
            pass
        self._poll_job = self.root.after(50, self._poll)

    # ---- 存檔與關閉 ----
    def _schedule_save(self) -> None:
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._do_save)

    def _schedule_geometry_save(self) -> None:
        if self._geom_job:
            self.root.after_cancel(self._geom_job)
        self._geom_job = self.root.after(500, self._store_geometry)

    def _store_geometry(self) -> None:
        self._geom_job = None
        try:
            if self.root.state() != "normal":
                return
            width, height = self.root.winfo_width(), self.root.winfo_height()
            x, y = self.root.winfo_x(), self.root.winfo_y()
        except tk.TclError:
            return
        if width < self._px(200) or height < self._px(150):
            return
        self.settings.window = {"x": int(x), "y": int(y),
                                "width": int(width), "height": int(height)}
        self._schedule_save()

    def _do_save(self) -> None:
        self._save_job = None
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showerror(
                S.APP_TITLE,
                S.DLG_SAVE_ERROR.format(reason=exc.strerror or str(exc)))

    def _on_close(self) -> None:
        for job in (self._poll_job, self._save_job, self._geom_job,
                    self._toast_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self._poll_job = self._save_job = self._geom_job = None
        self._store_geometry()
        self.engine.stop()
        self.script_runner.stop()
        set_corner_suppressed(False)
        self.hotkeys.stop()
        win32.release_all_buttons()
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.root.destroy()
