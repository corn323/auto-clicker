"""UI：ttk 自訂深色主題、點位列表與編輯、全域設定、腳本、狀態列、遮罩選點。"""
from __future__ import annotations

import copy
import json
import queue
import sys
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.font as tkfont
import tkinter.messagebox as messagebox
from pathlib import Path
from tkinter import ttk

from . import scripting, win32
from .config import (APP_NAME, MAX_POINTS, PointConfig, Settings,
                     button_label, sanitize_global, sanitize_point,
                     save_settings)
from .engine import (ClickEngine, EngineStatus, set_corner_suppressed,
                     uniform_range)

# ---- 色票（語意角色） ----
BG = "#14171c"
SURFACE = "#1b2027"
SURFACE2 = "#232a33"
BORDER = "#2e3742"
TEXT = "#e8edf5"
MUTED = "#98a2b3"
ACCENT = "#4f8cff"
ACCENT_DARK = "#3d6fd6"
SUCCESS = "#3ecf8e"
DANGER = "#ff5d5d"
WARNING = "#f2b544"
SELECTION = "#2b3d5f"

ORDER_LABELS = {"sequential": "依序", "random": "隨機", "weighted": "加權隨機"}
MOVE_LABELS = {"teleport": "瞬移", "curve": "曲線移動"}
STOP_LABELS = {"manual": "手動熱鍵", "repeats": "總次數", "time": "總時間"}
JITTER_LABELS = {"uniform": "均勻", "normal": "常態"}
CORNER_LABELS = {"top-left": "左上", "top-right": "右上",
                 "bottom-left": "左下", "bottom-right": "右下"}
BUTTON_LABELS_UI = {"left": "左鍵", "right": "右鍵", "middle": "中鍵"}
STATE_STYLE = {
    "idle": ("● 待機", MUTED),
    "running": ("● 執行中", SUCCESS),
    "paused": ("● 暫停", WARNING),
    "stopping": ("● 停止中", DANGER),
}


class ScreenOverlay:
    """覆蓋整個虛擬桌面的半透明遮罩；點一下記錄座標，Esc/右鍵取消。

    位置與尺寸一律以 Win32 虛擬桌面「實體像素」計算（virtual_rect +
    SetWindowPos），不依賴 Tk 的 DPI 縮放換算，確保負座標副螢幕與
    混合 DPI 下遮罩仍精準貼合；點擊座標同樣用 GetCursorPos 實體像素。
    """

    def __init__(self, root: tk.Tk, on_pick, on_cancel) -> None:
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
            # 極少數環境 SetWindowPos 失敗時退回 Tk geometry（仍為實體像素）
            self.top.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.top.update_idletasks()
        try:
            self.top.grab_set()
            self.top.focus_force()
        except tk.TclError:
            pass
        self._draw_monitors(vx, vy, vw, vh)
        self.canvas.bind("<Button-1>", self._pick)
        self.canvas.bind("<Button-3>", self._cancel)
        self.top.bind("<Escape>", self._cancel)
        self.top.protocol("WM_DELETE_WINDOW", self._cancel)

    def _draw_monitors(self, vx: int, vy: int, vw: int, _vh: int) -> None:
        for m in win32.list_monitors():
            x0, y0 = m.left - vx, m.top - vy
            x1, y1 = x0 + m.width, y0 + m.height
            self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2,
                                         outline=ACCENT, width=2)
            self.canvas.create_text(
                x0 + 14, y0 + 12, anchor="nw", fill=TEXT,
                text=(f"螢幕 {m.index + 1}  {m.width}×{m.height}  {m.dpi} DPI"
                      + ("（主）" if m.primary else "")),
                font=("Microsoft JhengHei UI", 11, "bold"))
        self.canvas.create_text(
            vw // 2, 44, fill="#ffffff",
            text="點一下要記錄的位置   ·   Esc 取消",
            font=("Microsoft JhengHei UI", 14, "bold"))

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


class App:
    def __init__(self, root: tk.Tk, settings: Settings,
                 load_warnings: list[str]) -> None:
        self.root = root
        self.settings = settings
        self.q: queue.Queue = queue.Queue()
        self.hotkeys = win32.HotkeyManager()
        self.engine = ClickEngine(self._on_status, self._on_error, self._on_finished)
        self.script_runner = scripting.ScriptRunner(
            self._on_status, self._on_error, self._on_finished)
        self.overlay: ScreenOverlay | None = None
        self._sel_index: int | None = None
        self._drag_row: str | None = None
        self._save_job: str | None = None
        self._toast_job: str | None = None
        self.monitors: list[win32.MonitorInfo] = []
        self._dpi = next((m.dpi for m in win32.list_monitors() if m.primary), 96)
        self._px = lambda n: max(1, int(round(n * self._dpi / 96)))
        self._font_setup()
        self._style_setup()
        self._make_vars()
        self._build()
        self.refresh_tree()
        self.refresh_monitor_info()
        self._register_hotkeys()
        self._poll()
        if load_warnings:
            self.root.after(200, lambda: messagebox.showwarning(
                APP_NAME, "載入設定時已自動修正：\n\n" + "\n".join(load_warnings[:10])))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 外觀 ----
    def _font_setup(self) -> None:
        families = set(tkfont.families(self.root))
        zh = ("Microsoft JhengHei UI" if "Microsoft JhengHei UI" in families
              else "Microsoft JhengHei" if "Microsoft JhengHei" in families
              else "Segoe UI")
        self.f_body = tkfont.Font(family=zh, size=10)
        self.f_small = tkfont.Font(family=zh, size=9)
        self.f_head = tkfont.Font(family=zh, size=16, weight="bold")
        self.f_mono = tkfont.Font(
            family="Consolas" if "Consolas" in families else zh, size=10)

    def _style_setup(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=self.f_body,
                    borderwidth=0, focuscolor=ACCENT)
        s.configure("TFrame", background=BG)
        s.configure("Surface.TFrame", background=SURFACE)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED,
                    font=self.f_small)
        s.configure("Head.TLabel", background=SURFACE, foreground=TEXT,
                    font=self.f_head)
        s.configure("Hint.TLabel", background=SURFACE, foreground=MUTED,
                    font=self.f_small)
        s.configure("TButton", background=SURFACE2, foreground=TEXT,
                    padding=(self._px(12), self._px(6)), borderwidth=0)
        s.map("TButton", background=[("active", BORDER), ("disabled", SURFACE)],
              foreground=[("disabled", MUTED)])
        s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        s.map("Accent.TButton",
              background=[("disabled", SURFACE2), ("active", ACCENT_DARK)],
              foreground=[("disabled", MUTED)])
        s.configure("Danger.TButton", background=DANGER, foreground="#ffffff")
        s.map("Danger.TButton",
              background=[("disabled", SURFACE2), ("active", "#e04848")],
              foreground=[("disabled", MUTED)])
        s.configure("TEntry", fieldbackground=SURFACE2, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, padding=self._px(5))
        s.configure("TSpinbox", fieldbackground=SURFACE2, foreground=TEXT,
                    insertcolor=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=self._px(3))
        s.configure("TCombobox", fieldbackground=SURFACE2, background=SURFACE2,
                    foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=self._px(4))
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE2)],
              selectbackground=[("readonly", SURFACE2)],
              selectforeground=[("readonly", TEXT)])
        s.configure("TCheckbutton", background=BG, foreground=TEXT,
                    focuscolor=ACCENT)
        s.map("TCheckbutton", background=[("active", BG)])
        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, rowheight=self._px(30), borderwidth=0,
                    bordercolor=BG)
        s.map("Treeview", background=[("selected", SELECTION)],
              foreground=[("selected", TEXT)],
              lightcolor=[("active", BG), ("!active", BG), ("disabled", BG)],
              darkcolor=[("active", BG), ("!active", BG), ("disabled", BG)])
        s.configure("Treeview.Heading", background=SURFACE2, foreground=MUTED,
                    relief="flat", padding=(self._px(6), self._px(7)),
                    font=self.f_small)
        s.map("Treeview.Heading", background=[("active", BORDER)],
              lightcolor=[("active", SURFACE2), ("!active", SURFACE2)],
              darkcolor=[("active", SURFACE2), ("!active", SURFACE2)])
        s.configure("TNotebook", background=BG, borderwidth=0,
                    bordercolor=BG, darkcolor=BG)
        s.map("TNotebook",
              lightcolor=[("active", BG), ("!active", BG), ("disabled", BG)],
              darkcolor=[("active", BG), ("!active", BG), ("disabled", BG)])
        s.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                    padding=(self._px(14), self._px(8)), bordercolor=BG,
                    darkcolor=BG)
        s.map("TNotebook.Tab",
              background=[("selected", SURFACE), ("active", SURFACE)],
              foreground=[("selected", TEXT), ("active", TEXT)],
              lightcolor=[("selected", BG), ("active", BG), ("!selected", BG)],
              darkcolor=[("selected", BG), ("active", BG), ("!selected", BG)])
        s.configure("TScrollbar", background=SURFACE2, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED)
        self.root.option_add("*TCombobox*Listbox.background", SURFACE2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", SELECTION)
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        self.root.configure(bg=BG)

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
        self.v_jitter_mode = tk.StringVar(value=JITTER_LABELS["uniform"])
        self.v_button = tk.StringVar(value=BUTTON_LABELS_UI["left"])
        self.v_double = tk.BooleanVar(value=False)
        self.v_repeat = tk.StringVar(value="1")
        self.v_weight = tk.StringVar(value="1")
        self.v_order = tk.StringVar(value=ORDER_LABELS["sequential"])
        self.v_move = tk.StringVar(value=MOVE_LABELS["curve"])
        self.v_min_interval = tk.StringVar(value="10")
        self.v_pause_chance = tk.StringVar(value="3")
        self.v_pause_min = tk.StringVar(value="300")
        self.v_pause_max = tk.StringVar(value="1500")
        self.v_stop_mode = tk.StringVar(value=STOP_LABELS["manual"])
        self.v_total_repeats = tk.StringVar(value="100")
        self.v_total_time = tk.StringVar(value="60")
        self.v_hk_start = tk.StringVar(value="F8")
        self.v_hk_stop = tk.StringVar(value="F9")
        self.v_hk_record = tk.StringVar(value="F6")
        self.v_corner = tk.StringVar(value=CORNER_LABELS["top-left"])
        self.v_corner_size = tk.StringVar(value="3")
        self.v_corner_enabled = tk.BooleanVar(value=True)
        self.v_press_delay = tk.StringVar(value="8")

    @staticmethod
    def _key_of(labels: dict, display: str) -> str | None:
        for k, v in labels.items():
            if v == display:
                return k
        return None

    @staticmethod
    def _lrow(tab: ttk.Frame, text: str) -> ttk.Frame:
        """在 tab 建立一列：左欄標籤、右欄回傳容器。"""
        row = len(tab.winfo_children())
        ttk.Label(tab, text=text).grid(row=row, column=0, sticky="w", pady=3)
        f = ttk.Frame(tab)
        f.grid(row=row, column=1, sticky="w", pady=3)
        return f

    # ---- 版面 ----
    def _build(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry(f"{self._px(1080)}x{self._px(720)}")
        self.root.minsize(self._px(980), self._px(620))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, style="Surface.TFrame",
                           padding=(self._px(20), self._px(12)))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=APP_NAME, style="Head.TLabel").pack(side="left")
        self.hint_label = ttk.Label(header, style="Hint.TLabel", text="")
        self.hint_label.pack(side="right")
        self._update_hint()

        main = ttk.Frame(self.root, padding=(self._px(12), self._px(8)))
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=3, minsize=self._px(620))
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)
        self._build_points_panel(main)
        self._build_notebook(main)
        self._build_status_bar()

    def _build_points_panel(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        bar = ttk.Frame(left)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text="錄製 F6", command=self.record_point).pack(side="left")
        ttk.Button(bar, text="選取位置",
                   command=self._pick_add).pack(side="left", padx=(5, 0))
        ttk.Button(bar, text="測試此點",
                   command=self._test_point).pack(side="left", padx=(5, 0))
        ttk.Button(bar, text="上移", width=4,
                   command=lambda: self._move_point(-1)).pack(side="left", padx=(5, 0))
        ttk.Button(bar, text="下移", width=4,
                   command=lambda: self._move_point(1)).pack(side="left", padx=(5, 0))
        ttk.Button(bar, text="複製", width=4,
                   command=self._copy_point).pack(side="left", padx=(5, 0))
        ttk.Button(bar, text="刪除", width=4,
                   command=self._delete_point).pack(side="left", padx=(5, 0))

        self.tree_frame = ttk.Frame(left)
        self.tree_frame.grid(row=1, column=0, sticky="nsew")
        cols = ("enabled", "name", "pos", "screen", "offset", "button", "count")
        self.tree = ttk.Treeview(self.tree_frame, columns=cols,
                                 show="headings", selectmode="browse")
        for cid, text, width, anchor in (
                ("enabled", "啟用", 44, "center"), ("name", "名稱", 120, "w"),
                ("pos", "座標", 100, "w"), ("screen", "螢幕", 190, "w"),
                ("offset", "偏移", 48, "e"), ("button", "按鍵", 66, "w"),
                ("count", "次數", 48, "e")):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=self._px(width), anchor=anchor,
                             stretch=False)
        scroll = ttk.Scrollbar(self.tree_frame, orient="vertical",
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<ButtonPress-1>", self._tree_press)
        self.tree.bind("<B1-Motion>", self._tree_motion)
        self.tree.bind("<ButtonRelease-1>", self._tree_release)
        self.tree.bind("<Delete>", lambda e: self._delete_point())
        self.tree.bind("<space>", self._tree_toggle_enabled)

        self.empty_label = ttk.Label(
            left, style="Muted.TLabel",
            text="尚無點位：把游標移到目標位置按 F6，或按「選取位置」點一下畫面。")

    def _build_notebook(self, parent: ttk.Frame) -> None:
        nb = ttk.Notebook(parent)
        self.notebook = nb
        nb.grid(row=0, column=1, sticky="nsew")
        point_tab = ttk.Frame(nb, padding=12)
        global_tab = ttk.Frame(nb, padding=12)
        script_tab = ttk.Frame(nb, padding=12)
        nb.add(point_tab, text=" 點位設定 ")
        nb.add(global_tab, text=" 全域設定 ")
        nb.add(script_tab, text=" 腳本 ")
        self._build_point_editor(point_tab)
        self._build_global_tab(global_tab)
        self._build_script_tab(script_tab)
        self._load_global_vars()

    def _build_point_editor(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, minsize=self._px(86))
        tab.columnconfigure(1, weight=1)

        def entry(var, width=14):
            e = ttk.Entry(tab, textvariable=var, width=width)
            e.bind("<FocusOut>", lambda e: self._apply_editor())
            e.bind("<Return>", lambda e: self._apply_editor())
            return e

        def spin(var, lo, hi, width=14):
            sp = ttk.Spinbox(tab, from_=lo, to=hi, textvariable=var, width=width)
            sp.bind("<FocusOut>", lambda e: self._apply_editor())
            sp.bind("<Return>", lambda e: self._apply_editor())
            return sp

        def grid(widget, row, sticky="we"):
            widget.grid(row=row, column=1, sticky=sticky, pady=3)

        def label(text, row):
            ttk.Label(tab, text=text).grid(row=row, column=0, sticky="w", pady=3)

        label("名稱", 0)
        self.e_name = entry(self.v_name, 20)
        grid(self.e_name, 0)
        label("啟用", 1)
        grid(ttk.Checkbutton(tab, text="啟用此點位", variable=self.v_enabled,
                             command=self._apply_editor), 1, "w")
        label("座標", 2)
        pos_row = ttk.Frame(tab)
        pos_row.grid(row=2, column=1, sticky="we", pady=3)
        ttk.Label(pos_row, textvariable=self.v_pos, font=self.f_mono).pack(side="left")
        ttk.Button(pos_row, text="重新選取", width=9,
                   command=self._pick_edit).pack(side="left", padx=(8, 0))
        label("所屬螢幕", 3)
        self.e_screen = ttk.Label(tab, textvariable=self.v_screen,
                                  style="Muted.TLabel")
        grid(self.e_screen, 3, "w")
        label("偏移半徑", 4)
        grid(spin(self.v_radius, 0, 1000), 4)
        label("按住時間", 5)
        hold_row = ttk.Frame(tab)
        hold_row.grid(row=5, column=1, sticky="w", pady=3)
        for var in (self.v_hold_min, self.v_hold_max):
            sp = ttk.Spinbox(hold_row, from_=1, to=5000, textvariable=var, width=6)
            sp.bind("<FocusOut>", lambda e: self._apply_editor())
            sp.bind("<Return>", lambda e: self._apply_editor())
            sp.pack(side="left")
        ttk.Label(hold_row, text="–", style="Muted.TLabel").pack(side="left", padx=3)
        ttk.Label(hold_row, text="ms", style="Muted.TLabel").pack(side="left")
        label("點擊間隔", 6)
        grid(spin(self.v_interval, 10, 3600000), 6)
        label("隨機幅度", 7)
        jitter_row = ttk.Frame(tab)
        jitter_row.grid(row=7, column=1, sticky="w", pady=3)
        sp = ttk.Spinbox(jitter_row, from_=0, to=100, textvariable=self.v_jitter,
                         width=6)
        sp.bind("<FocusOut>", lambda e: self._apply_editor())
        sp.pack(side="left")
        ttk.Label(jitter_row, text="%", style="Muted.TLabel").pack(side="left", padx=(3, 8))
        jc = ttk.Combobox(jitter_row, textvariable=self.v_jitter_mode,
                          values=list(JITTER_LABELS.values()), state="readonly",
                          width=7)
        jc.bind("<<ComboboxSelected>>", lambda e: self._apply_editor())
        jc.pack(side="left")
        label("按鍵", 8)
        btn_row = ttk.Frame(tab)
        btn_row.grid(row=8, column=1, sticky="w", pady=3)
        bc = ttk.Combobox(btn_row, textvariable=self.v_button,
                          values=list(BUTTON_LABELS_UI.values()),
                          state="readonly", width=7)
        bc.bind("<<ComboboxSelected>>", lambda e: self._apply_editor())
        bc.pack(side="left")
        ttk.Checkbutton(btn_row, text="雙擊", variable=self.v_double,
                        command=self._apply_editor).pack(side="left", padx=(10, 0))
        label("重複次數", 9)
        grid(spin(self.v_repeat, 1, 100000), 9)
        label("權重", 10)
        grid(spin(self.v_weight, 1, 100), 10)
        ttk.Label(tab, style="Muted.TLabel",
                  text="權重僅在「加權隨機」順序使用；偏移半徑 0 表示精準落點。").grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.editor_empty = ttk.Label(
            tab, style="Muted.TLabel", text="從左側選擇一個點位以編輯。")
        self.editor_body = tab

    def _build_global_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, minsize=self._px(100))
        tab.columnconfigure(1, weight=1)

        def spin(parent, var, lo, hi, width=7):
            sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=width)
            sp.bind("<FocusOut>", lambda e: self._apply_global())
            sp.bind("<Return>", lambda e: self._apply_global())
            return sp

        def combo(parent, var, values, width=10):
            c = ttk.Combobox(parent, textvariable=var, values=values,
                             state="readonly", width=width)
            c.bind("<<ComboboxSelected>>", lambda e: self._apply_global())
            return c

        def muted(parent, text):
            ttk.Label(parent, style="Muted.TLabel", text=text).pack(side="left")

        f = self._lrow(tab, "執行順序")
        combo(f, self.v_order, list(ORDER_LABELS.values()), 12).pack(side="left")
        f = self._lrow(tab, "游標移動")
        combo(f, self.v_move, list(MOVE_LABELS.values()), 12).pack(side="left")
        f = self._lrow(tab, "最低間隔")
        spin(f, self.v_min_interval, 10, 5000).pack(side="left")
        muted(f, "ms（兩次點擊之間至少）")
        f = self._lrow(tab, "按下前延遲")
        spin(f, self.v_press_delay, 0, 50).pack(side="left")
        muted(f, "ms（移動後、按下前，另加 0–3ms 隨機）")
        f = self._lrow(tab, "隨機長停頓")
        spin(f, self.v_pause_chance, 0, 100, 5).pack(side="left")
        muted(f, "%，")
        spin(f, self.v_pause_min, 100, 600000).pack(side="left")
        muted(f, "–")
        spin(f, self.v_pause_max, 100, 600000).pack(side="left")
        muted(f, "ms")
        f = self._lrow(tab, "停止條件")
        combo(f, self.v_stop_mode, list(STOP_LABELS.values()), 12).pack(side="left")
        self.spin_repeats = spin(f, self.v_total_repeats, 1, 10000000)
        self.spin_repeats.pack(side="left", padx=(10, 0))
        muted(f, "次")
        self.spin_time = spin(f, self.v_total_time, 1, 86400)
        muted(f, "秒")
        self.spin_time.pack(side="left", padx=(10, 0))
        self.v_stop_mode.trace_add("write", lambda *a: self._update_stop_extra())
        f = self._lrow(tab, "全域熱鍵")
        for caption, var in (("開始/暫停", self.v_hk_start),
                             ("緊急停止", self.v_hk_stop),
                             ("錄製", self.v_hk_record)):
            muted(f, caption + " ")
            e = ttk.Entry(f, textvariable=var, width=7)
            e.bind("<Return>", lambda ev: self._apply_hotkeys())
            e.pack(side="left", padx=(0, 6))
        f = self._lrow(tab, "")
        ttk.Button(f, text="套用熱鍵", command=self._apply_hotkeys).pack(side="left")
        muted(f, "熱鍵被其他程式占用時可改鍵")
        f = self._lrow(tab, "角落急停")
        ttk.Checkbutton(f, text="啟用", variable=self.v_corner_enabled,
                        command=self._apply_global).pack(side="left")
        combo(f, self.v_corner, list(CORNER_LABELS.values()), 8
              ).pack(side="left", padx=(8, 0))
        muted(f, "游標進入角落")
        spin(f, self.v_corner_size, 2, 100, 5).pack(side="left")
        muted(f, "px（最少 2px）")
        f = self._lrow(tab, "螢幕配置")
        self.monitor_label = ttk.Label(f, style="Muted.TLabel", text="…",
                                       justify="left")
        self.monitor_label.pack(side="left", anchor="n")
        f = self._lrow(tab, "")
        ttk.Button(f, text="重新校正", command=self._recalibrate).pack(side="left")
        muted(f, "螢幕或縮放變更後使用")

    def _build_script_tab(self, tab: ttk.Frame) -> None:
        tab.rowconfigure(3, weight=1)
        tab.columnconfigure(0, weight=1)
        bar = ttk.Frame(tab)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text="載入檔案", command=self._script_load).pack(side="left")
        ttk.Button(bar, text="匯出",
                   command=self._script_export).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="驗證",
                   command=self._script_validate).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="載入範例", command=self._script_load_example
                   ).pack(side="left", padx=(6, 0))
        bar2 = ttk.Frame(tab)
        bar2.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(bar2, text="執行", style="Accent.TButton",
                   command=self._script_run).pack(side="left")
        ttk.Button(bar2, text="停止",
                   command=self.stop_all).pack(side="left", padx=(6, 0))
        self.example_combo = ttk.Combobox(bar2, state="readonly", width=16)
        self.example_combo.pack(side="right")
        self._refresh_examples()
        self.script_path_label = ttk.Label(tab, style="Muted.TLabel",
                                           text="尚未載入腳本")
        self.script_path_label.grid(row=2, column=0, sticky="w")
        text_frame = ttk.Frame(tab)
        text_frame.grid(row=3, column=0, sticky="nsew", pady=(4, 4))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.script_text = tk.Text(text_frame, height=14, wrap="word", undo=True,
                                   bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                                   relief="flat", padx=10, pady=8,
                                   font=self.f_mono)
        sbar = ttk.Scrollbar(text_frame, orient="vertical",
                             command=self.script_text.yview)
        self.script_text.configure(yscrollcommand=sbar.set)
        self.script_text.grid(row=0, column=0, sticky="nsew")
        sbar.grid(row=0, column=1, sticky="ns")
        self.script_text.insert("1.0", json.dumps(
            {"version": 1, "name": "新腳本",
             "steps": [{"type": "wait", "ms": 500},
                       {"type": "click", "x": 500, "y": 500,
                        "button": "left", "double": False, "hold_ms": 50}]},
            ensure_ascii=False, indent=2))
        self.script_msg = ttk.Label(tab, style="Muted.TLabel", text="",
                                    wraplength=380, justify="left")
        self.script_msg.grid(row=4, column=0, sticky="w")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root, style="Surface.TFrame",
                        padding=(self._px(20), self._px(10)))
        bar.grid(row=2, column=0, sticky="ew")
        self.state_label = tk.Label(bar, text="● 待機", bg=SURFACE, fg=MUTED)
        self.state_label.pack(side="left")
        self.point_value = tk.Label(bar, text="—", bg=SURFACE, fg=MUTED)
        self.clicks_value = tk.Label(bar, text="0", bg=SURFACE, fg=TEXT)
        self.time_value = tk.Label(bar, text="00:00", bg=SURFACE, fg=TEXT)
        for caption, value in (("目前點位", self.point_value),
                               ("已點擊", self.clicks_value),
                               ("運行時間", self.time_value)):
            ttk.Label(bar, style="Hint.TLabel", text=caption
                      ).pack(side="left", padx=(24, 4))
            value.pack(side="left")
        self.toast_label = tk.Label(bar, text="", bg=SURFACE, fg=SUCCESS)
        self.toast_label.pack(side="left", padx=(24, 0))
        self.start_btn = ttk.Button(bar, text="開始 F8", style="Accent.TButton",
                                    command=self.toggle_run, width=11)
        self.start_btn.pack(side="right")
        self.stop_btn = ttk.Button(bar, text="停止 F9", style="Danger.TButton",
                                   command=self.stop_all, width=9)
        self.stop_btn.pack(side="right", padx=(0, 8))

    # ---- 資料 <-> UI ----
    def refresh_tree(self) -> None:
        selected = None
        if self._sel_index is not None and self._sel_index < len(self.settings.points):
            selected = self._sel_index
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.settings.points):
            self.tree.insert("", "end", iid=f"i{i}", values=(
                "是" if p.enabled else "否", p.name, f"{p.x}, {p.y}",
                f"#{p.screen_index + 1} {p.screen_width}×{p.screen_height} "
                f"{p.screen_dpi}dpi", p.radius,
                button_label(p.button) + ("＋雙擊" if p.double else ""),
                p.repeat))
        if self.settings.points:
            self.empty_label.grid_remove()
        else:
            self.empty_label.grid(row=2, column=0, sticky="w", pady=6)
        if selected is not None:
            self.tree.selection_set(f"i{selected}")
            self.tree.see(f"i{selected}")
        else:
            self._show_editor(None)

    def _on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self._sel_index = int(sel[0][1:])
        self._show_editor(self._sel_index)

    def _show_editor(self, index: int | None) -> None:
        if index is None or index >= len(self.settings.points):
            self._sel_index = None
            for child in self.editor_body.winfo_children():
                if child is not self.editor_empty:
                    child.grid_remove()
            self.editor_empty.grid(row=0, column=0, columnspan=2, pady=40)
            return
        self.editor_empty.grid_remove()
        for child in self.editor_body.winfo_children():
            if child is not self.editor_empty:
                child.grid()
        p = self.settings.points[index]
        self.v_name.set(p.name)
        self.v_enabled.set(p.enabled)
        self.v_pos.set(f"{p.x}, {p.y}")
        self.v_screen.set(
            f"#{p.screen_index + 1}  {p.screen_width}×{p.screen_height}  "
            f"{p.screen_dpi} DPI  ({p.screen_x}, {p.screen_y})")
        self.v_radius.set(str(p.radius))
        self.v_hold_min.set(str(p.hold_min_ms))
        self.v_hold_max.set(str(p.hold_max_ms))
        self.v_interval.set(str(p.interval_ms))
        self.v_jitter.set(str(p.jitter_pct))
        self.v_jitter_mode.set(JITTER_LABELS.get(p.jitter_mode, "均勻"))
        self.v_button.set(button_label(p.button))
        self.v_double.set(p.double)
        self.v_repeat.set(str(p.repeat))
        self.v_weight.set(str(p.weight))

    @staticmethod
    def _read_int_var(var: tk.StringVar, fallback: int) -> int:
        try:
            return int(str(var.get()).strip())
        except (ValueError, tk.TclError):
            return fallback

    def _apply_editor(self) -> None:
        if self._sel_index is None or self._sel_index >= len(self.settings.points):
            return
        p = self.settings.points[self._sel_index]
        raw = {**point_to_dict(p),
               "name": str(self.v_name.get()),
               "enabled": bool(self.v_enabled.get()),
               "radius": self._read_int_var(self.v_radius, p.radius),
               "hold_min_ms": self._read_int_var(self.v_hold_min, p.hold_min_ms),
               "hold_max_ms": self._read_int_var(self.v_hold_max, p.hold_max_ms),
               "interval_ms": self._read_int_var(self.v_interval, p.interval_ms),
               "jitter_pct": self._read_int_var(self.v_jitter, p.jitter_pct),
               "jitter_mode": self._key_of(JITTER_LABELS,
                   str(self.v_jitter_mode.get())) or p.jitter_mode,
               "button": self._key_of(BUTTON_LABELS_UI,
                   str(self.v_button.get())) or p.button,
               "double": bool(self.v_double.get()),
               "repeat": self._read_int_var(self.v_repeat, p.repeat),
               "weight": self._read_int_var(self.v_weight, p.weight)}
        self.settings.points[self._sel_index] = sanitize_point(
            raw, self._sel_index, [])
        self.refresh_tree()
        self._schedule_save()

    def _load_global_vars(self) -> None:
        g = self.settings.config
        self.v_order.set(ORDER_LABELS.get(g.order, "依序"))
        self.v_move.set(MOVE_LABELS.get(g.move_mode, "曲線移動"))
        self.v_min_interval.set(str(g.min_interval_ms))
        self.v_pause_chance.set(str(g.long_pause_chance))
        self.v_pause_min.set(str(g.long_pause_min_ms))
        self.v_pause_max.set(str(g.long_pause_max_ms))
        self.v_stop_mode.set(STOP_LABELS.get(g.stop_mode, "手動熱鍵"))
        self.v_total_repeats.set(str(g.total_repeats))
        self.v_total_time.set(str(g.total_time_sec))
        self.v_hk_start.set(g.hotkey_start)
        self.v_hk_stop.set(g.hotkey_stop)
        self.v_hk_record.set(g.hotkey_record)
        self.v_corner.set(CORNER_LABELS.get(g.emergency_corner, "左上"))
        self.v_corner_size.set(str(g.corner_size))
        self.v_corner_enabled.set(g.corner_enabled)
        self.v_press_delay.set(str(g.press_delay_ms))
        self._update_stop_extra()

    def _apply_global(self) -> None:
        g = self.settings.config
        raw = {**vars(g),
               "order": self._key_of(ORDER_LABELS, str(self.v_order.get())) or g.order,
               "move_mode": self._key_of(MOVE_LABELS,
                   str(self.v_move.get())) or g.move_mode,
               "min_interval_ms": self._read_int_var(self.v_min_interval,
                   g.min_interval_ms),
               "long_pause_chance": self._read_int_var(self.v_pause_chance,
                   g.long_pause_chance),
               "long_pause_min_ms": self._read_int_var(self.v_pause_min,
                   g.long_pause_min_ms),
               "long_pause_max_ms": self._read_int_var(self.v_pause_max,
                   g.long_pause_max_ms),
               "stop_mode": self._key_of(STOP_LABELS,
                   str(self.v_stop_mode.get())) or g.stop_mode,
               "total_repeats": self._read_int_var(self.v_total_repeats,
                   g.total_repeats),
               "total_time_sec": self._read_int_var(self.v_total_time,
                   g.total_time_sec),
               "emergency_corner": self._key_of(CORNER_LABELS,
                   str(self.v_corner.get())) or g.emergency_corner,
               "corner_size": self._read_int_var(self.v_corner_size,
                   g.corner_size),
               "corner_enabled": bool(self.v_corner_enabled.get()),
               "press_delay_ms": self._read_int_var(self.v_press_delay,
                   g.press_delay_ms)}
        self.settings.config = sanitize_global(raw, [])
        self._load_global_vars()
        self._schedule_save()

    def _update_stop_extra(self) -> None:
        mode = self._key_of(STOP_LABELS, str(self.v_stop_mode.get()))
        self.spin_repeats.config(state="normal" if mode == "repeats" else "disabled")
        self.spin_time.config(state="normal" if mode == "time" else "disabled")

    def _update_hint(self) -> None:
        g = self.settings.config
        self.hint_label.config(
            text=f"{g.hotkey_record} 錄製   ·   {g.hotkey_start} 開始/暫停   ·   "
                 f"{g.hotkey_stop} 停止")

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
            messagebox.showwarning(APP_NAME, "無法判斷座標所屬螢幕。")
            return None
        p = sanitize_point({
            "name": self._next_name(), "x": x, "y": y, "enabled": True,
            "screen_index": m.index, "screen_x": m.left, "screen_y": m.top,
            "screen_width": m.width, "screen_height": m.height,
            "screen_dpi": m.dpi,
        }, len(self.settings.points), [])
        self.settings.monitor_layout = win32.monitor_signature(monitors)
        return p

    def _flash_status(self, text: str) -> None:
        """狀態列短暫訊息（錄製回饋），1.8 秒後自動清除。"""
        self.toast_label.config(text=text)
        if self._toast_job:
            try:
                self.root.after_cancel(self._toast_job)
            except tk.TclError:
                pass
        self._toast_job = self.root.after(1800, self._clear_toast)

    def _clear_toast(self) -> None:
        self._toast_job = None
        self.toast_label.config(text="")

    def record_point(self, x: int | None = None, y: int | None = None) -> None:
        if self.overlay is not None:
            return
        set_corner_suppressed(True)
        try:
            if x is None or y is None:
                x, y = win32.get_cursor_pos()
            if len(self.settings.points) >= MAX_POINTS:
                messagebox.showwarning(APP_NAME, f"點位數量已達上限 {MAX_POINTS}。")
                return
            p = self._make_point(x, y)
            if p is None:
                return
            self.settings.points.append(p)
            self._sel_index = len(self.settings.points) - 1
            self.refresh_tree()
            self._schedule_save()
            self.root.bell()
            self._flash_status(f"已記錄：{p.name}（{x}, {y}）")
        finally:
            set_corner_suppressed(False)

    def _pick_add(self) -> None:
        self._open_overlay("add")

    def _pick_edit(self) -> None:
        if self._sel_index is None:
            messagebox.showinfo(APP_NAME, "先在左側選擇要修改的點位。")
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
                p.jitter_mode, p.button, p.double = (old.jitter_mode, old.button,
                                                     old.double)
                p.repeat, p.weight = old.repeat, old.weight
                self.settings.points[self._sel_index] = p
                self.refresh_tree()
                self._schedule_save()

        def cancelled() -> None:
            self.overlay = None
            set_corner_suppressed(False)

        set_corner_suppressed(True)
        try:
            self.overlay = ScreenOverlay(self.root, picked, cancelled)
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
            messagebox.showwarning(APP_NAME, f"點位數量已達上限 {MAX_POINTS}。")
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

    def _tree_toggle_enabled(self, _event=None) -> None:
        if self._sel_index is None:
            return "break"
        p = self.settings.points[self._sel_index]
        p.enabled = not p.enabled
        self.refresh_tree()
        self._schedule_save()
        return "break"

    def _test_point(self) -> None:
        if self._sel_index is None:
            messagebox.showinfo(APP_NAME, "先選擇一個點位再測試。")
            return
        if self.engine.is_running() or self.script_runner.is_running():
            messagebox.showwarning(APP_NAME, "請先停止再測試。")
            return
        p = self.settings.points[self._sel_index]
        try:
            win32.click_once(p.x, p.y, p.button,
                             uniform_range(p.hold_min_ms, p.hold_max_ms))
        except OSError as exc:
            self._show_error(str(exc))

    # ---- 螢幕資訊 ----
    def refresh_monitor_info(self) -> None:
        self.monitors = win32.list_monitors()
        lines = [f"螢幕 {m.index + 1}：{m.width}×{m.height}，{m.dpi} DPI"
                 + ("（主）" if m.primary else "")
                 + f"，範圍 ({m.left}, {m.top})" for m in self.monitors]
        self.monitor_label.config(text="\n".join(lines) or "未偵測到螢幕")

    def _layout_matches(self) -> bool:
        if not self.settings.monitor_layout:
            return True
        return win32.monitor_signature(self.monitors) == self.settings.monitor_layout

    def _recalibrate(self) -> None:
        self.refresh_monitor_info()
        for p in self.settings.points:
            m = win32.monitor_for_point(p.x, p.y, self.monitors)
            if m is not None:
                p.screen_index, p.screen_x, p.screen_y = m.index, m.left, m.top
                p.screen_width, p.screen_height = m.width, m.height
                p.screen_dpi = m.dpi
        self.settings.monitor_layout = win32.monitor_signature(self.monitors)
        self.refresh_tree()
        self._schedule_save()
        messagebox.showinfo(APP_NAME, "已依目前螢幕配置更新所有點位的螢幕資訊。")

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
                APP_NAME, "沒有啟用的點位：先按 F6 錄製，或勾選「啟用此點位」。")
            return
        self._apply_global()
        if not self._layout_matches():
            if not messagebox.askyesno(
                    APP_NAME,
                    "螢幕配置與錄製時不同，落點可能偏移。\n"
                    "建議先在「全域設定」按「重新校正螢幕資訊」。\n\n仍要開始？"):
                return
        elevated, pid = win32.foreground_elevation()
        if elevated and not win32.self_is_elevated():
            if not messagebox.askyesno(
                    APP_NAME,
                    f"前景程式（PID {pid}）以系統管理員執行，而本工具不是。\n"
                    "Windows UIPI 會封鎖輸入注入，點擊可能無效。\n\n仍要開始？"):
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
        if engine_on or script_on:
            paused = (self.engine.paused if engine_on
                      else self.script_runner.paused)
            self.start_btn.config(text="繼續 F8" if paused else "暫停 F8")
        else:
            self.start_btn.config(text="開始 F8")

    # ---- 熱鍵 ----
    def _register_hotkeys(self, bindings: dict[str, str] | None = None) -> bool:
        if bindings is None:
            g = self.settings.config
            bindings = {"start": g.hotkey_start, "stop": g.hotkey_stop,
                        "record": g.hotkey_record}
        errors = self.hotkeys.start(bindings)
        if errors:
            detail = "\n".join(f"{k}：{v}" for k, v in errors.items())
            messagebox.showerror(APP_NAME, f"熱鍵註冊失敗，請改用其他按鍵：\n\n{detail}")
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
        self._update_hint()
        self._schedule_save()

    # ---- 腳本 ----
    def _examples_dir(self) -> Path:
        base = Path(getattr(sys, "_MEIPASS",
                            Path(__file__).resolve().parent.parent))
        return base / "examples"

    def _refresh_examples(self) -> None:
        d = self._examples_dir()
        names = sorted(f.name for f in d.glob("*.json")) if d.is_dir() else []
        self.example_combo.config(values=names)
        if names:
            self.example_combo.current(0)

    def _script_text_parse(self):
        try:
            raw = json.loads(self.script_text.get("1.0", "end-1c"))
        except json.JSONDecodeError as exc:
            return None, [f"JSON 格式錯誤：{exc}"], []
        return scripting.parse_script(raw)

    def _fill_script_text(self, script: dict, path: str,
                          warnings: list[str]) -> None:
        self.script_text.delete("1.0", "end")
        self.script_text.insert(
            "1.0", json.dumps(script, ensure_ascii=False, indent=2))
        self.script_path_label.config(text=path)
        self._show_script_msg(warnings)

    def _script_load(self) -> None:
        path = filedialog.askopenfilename(
            title="載入腳本", filetypes=[("JSON 腳本", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        self._script_load_from_path(Path(path))

    def _script_load_from_path(self, path: Path) -> None:
        script, errors, warnings = scripting.load_script(path)
        if script is None:
            messagebox.showerror(APP_NAME, "腳本無法載入：\n\n" + "\n".join(errors[:10]))
            return
        self._fill_script_text(script, str(path), warnings)

    def _script_load_example(self) -> None:
        name = self.example_combo.get()
        if name:
            self._script_load_from_path(self._examples_dir() / name)

    def _script_export(self) -> None:
        script, errors, _warn = self._script_text_parse()
        if script is None:
            messagebox.showerror(APP_NAME,
                                 "腳本驗證失敗，無法匯出：\n\n" + "\n".join(errors[:10]))
            return
        path = filedialog.asksaveasfilename(
            title="匯出腳本", defaultextension=".json", initialfile="script.json",
            filetypes=[("JSON 腳本", "*.json")])
        if not path:
            return
        try:
            scripting.save_script(script, Path(path))
            self.script_path_label.config(text=path)
            self._show_script_msg(["已匯出（腳本僅含宣告式步驟，不含可執行程式碼）。"])
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"匯出失敗：{exc.strerror}")

    def _script_validate(self) -> None:
        script, errors, warnings = self._script_text_parse()
        if script is None:
            self._show_script_msg(errors)
        else:
            self._show_script_msg(
                [f"驗證通過：{len(script['steps'])} 個頂層步驟。"] + warnings)

    def _show_script_msg(self, lines: list[str]) -> None:
        first = lines[0] if lines else ""
        bad = first.startswith(("JSON 格式", "腳本", "步驟", "不支援", "僅支援",
                                "name", "steps", "展開", "無法"))
        self.script_msg.config(text="\n".join(lines[:10]),
                               foreground=WARNING if bad else MUTED)

    def _script_run(self) -> None:
        if self.engine.is_running() or self.script_runner.is_running():
            messagebox.showwarning(APP_NAME, "已有工作執行中。")
            return
        script, errors, warnings = self._script_text_parse()
        if script is None:
            messagebox.showerror(APP_NAME, "腳本驗證失敗：\n\n" + "\n".join(errors[:10]))
            return
        if warnings:
            self._show_script_msg(warnings)
        self._apply_global()
        g = self.settings.config
        self.script_runner.start(script, g.emergency_corner, g.corner_size)
        self._update_run_button()

    # ---- 狀態與訊息 ----
    def _on_status(self, st: EngineStatus) -> None:
        self.q.put(("status", st))

    def _on_error(self, msg: str) -> None:
        self.q.put(("error", msg))

    def _on_finished(self, st: EngineStatus) -> None:
        self.q.put(("finished", st))

    def _show_status(self, st: EngineStatus) -> None:
        text, color = STATE_STYLE.get(st.state, STATE_STYLE["idle"])
        if st.state == "idle" and st.clicks:
            text = "● 已停止"
        self.state_label.config(text=text, fg=color)
        self.point_value.config(text=st.point or "—",
                                fg=TEXT if st.point else MUTED)
        self.clicks_value.config(text=str(st.clicks))
        total = int(st.elapsed)
        self.time_value.config(text=f"{total // 60:02d}:{total % 60:02d}")
        self._update_run_button()

    def _show_error(self, message: str) -> None:
        self._update_run_button()
        messagebox.showerror(APP_NAME, message)

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
        self.root.after(50, self._poll)

    # ---- 存檔與關閉 ----
    def _schedule_save(self) -> None:
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._do_save)

    def _do_save(self) -> None:
        self._save_job = None
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"無法儲存設定：{exc.strerror}")

    def _on_close(self) -> None:
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
