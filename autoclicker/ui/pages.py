"""版面：點位清單、點位編輯、全域設定、狀態列。"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import win32
from ..config import (MAX_POINTS, button_label, point_to_dict,
                      sanitize_global, sanitize_point)
from ..engine import uniform_range
from . import strings as S
from .widgets import Disclosure, FormGrid, ScrollArea


class PointsPanelMixin:
    def _build_points_panel(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        self.points_panel = left
        left.grid(row=0, column=0, sticky="nsew", padx=(0, self._px(8)))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        hotkey = self.settings.config.hotkey_record
        bar = ttk.Frame(left)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, self._px(6)))
        self.add_btn = ttk.Button(bar, text=S.BTN_ADD.format(hotkey=hotkey),
                                  style="Accent.TButton", command=self.record_point)
        self.add_btn.pack(side="left")
        self._attach_tip(self.add_btn, S.TIP_ADD.format(hotkey=hotkey))
        pick = ttk.Button(bar, text=S.BTN_PICK, command=self._pick_add)
        pick.pack(side="left", padx=(self._px(6), 0))
        self._attach_tip(pick, S.TIP_PICK)
        test = ttk.Button(bar, text=S.BTN_TEST, command=self._test_point)
        test.pack(side="left", padx=(self._px(6), 0))
        self._attach_tip(test, S.TIP_TEST)

        bar2 = ttk.Frame(left)
        bar2.grid(row=1, column=0, sticky="ew", pady=(0, self._px(6)))
        for text, tip, cmd, width in (
                (S.BTN_UP, S.TIP_UP, lambda: self._move_point(-1), 5),
                (S.BTN_DOWN, S.TIP_DOWN, lambda: self._move_point(1), 5),
                (S.BTN_COPY, S.TIP_COPY, self._copy_point, 5),
                (S.BTN_DELETE, S.TIP_DELETE, self._delete_point, 5)):
            btn = ttk.Button(bar2, text=text, width=width, command=cmd)
            btn.pack(side="left", padx=(0, self._px(6)))
            self._attach_tip(btn, tip)

        self.tree_frame = ttk.Frame(left)
        self.tree_frame.grid(row=2, column=0, sticky="nsew")
        cols = tuple(cid for cid, _ in S.TREE_HEADINGS)
        self.tree = ttk.Treeview(self.tree_frame, columns=cols,
                                 show="headings", selectmode="browse")
        for cid, text in S.TREE_HEADINGS:
            self.tree.heading(cid, text=text)
            anchor = "e" if cid in ("offset", "count") else (
                "center" if cid == "enabled" else "w")
            self.tree.column(cid, width=self._px(S.TREE_MIN_WIDTHS[cid]),
                             minwidth=self._px(40), anchor=anchor,
                             stretch=cid in ("name", "screen"))
        scroll = ttk.Scrollbar(self.tree_frame, orient="vertical",
                               command=self.tree.yview)
        hscroll = ttk.Scrollbar(self.tree_frame, orient="horizontal",
                                command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set,
                            xscrollcommand=hscroll.set)
        self.tree_frame.rowconfigure(0, weight=1)
        self.tree_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<ButtonPress-1>", self._tree_press)
        self.tree.bind("<B1-Motion>", self._tree_motion)
        self.tree.bind("<ButtonRelease-1>", self._tree_release)
        self.tree.bind("<Delete>", lambda e: self._delete_point())
        self.tree.bind("<space>", self._tree_toggle_enabled)

        self.empty_frame = ttk.Frame(self.tree_frame)
        ttk.Label(self.empty_frame, text=S.EMPTY_TITLE,
                  style="EmptyTitle.TLabel").pack(anchor="w")
        self.empty_hint = ttk.Label(
            self.empty_frame,
            text=S.EMPTY_HINT.format(hotkey=hotkey),
            style="EmptyHint.TLabel", justify="left", wraplength=self._px(320))
        self.empty_hint.pack(anchor="w", pady=(self._px(6), 0))

    def _refresh_empty(self) -> None:
        hotkey = self.settings.config.hotkey_record
        self.empty_hint.configure(
            text=S.EMPTY_HINT.format(hotkey=hotkey))
        self.add_btn.configure(text=S.BTN_ADD.format(hotkey=hotkey))
        self.editor_empty_hint.configure(
            text=S.EMPTY_EDITOR.format(hotkey=hotkey))

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
            self.empty_frame.place_forget()
        else:
            self.empty_frame.place(relx=0.5, rely=0.36, anchor="center")
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

    def _build_point_editor(self, tab: ttk.Frame) -> None:
        self.editor_form = ttk.Frame(tab)
        self.editor_form.grid(row=0, column=0, sticky="nsew")
        tab.columnconfigure(0, weight=1)
        form = FormGrid(self.editor_form, self._px, self._attach_tip)

        f, h = form.field(S.LBL_NAME, S.EDITOR_HINTS["name"])
        self.e_name = ttk.Entry(f, textvariable=self.v_name, width=22)
        self.e_name.pack(side="left", fill="x", expand=True)
        self.e_name.bind("<FocusOut>", lambda e: self._apply_editor())
        self.e_name.bind("<Return>", lambda e: self._apply_editor())
        form.tip(self.e_name, S.EDITOR_TIPS["name"])

        f, h = form.field("啟用", S.EDITOR_HINTS["enabled"])
        chk = ttk.Checkbutton(f, text=S.LBL_ENABLED, variable=self.v_enabled,
                              command=self._apply_editor)
        chk.pack(side="left")
        self._attach_tip(chk, "勾選後執行時才會點擊此點位")

        f, h = form.field(S.LBL_POS, S.EDITOR_HINTS["pos"], unit=S.UNIT_PX)
        pos = ttk.Label(f, textvariable=self.v_pos,
                        font=self.fonts.mono)
        pos.pack(side="left")
        repick = ttk.Button(f, text=S.BTN_REPICK, width=9,
                            command=self._pick_edit)
        repick.pack(side="left", padx=(self._px(8), 0))
        self._attach_tip(pos, "例：1920, 1080（左上角為 0, 0）")
        self._attach_tip(repick, S.TIP_PICK)

        f, h = form.field(S.LBL_SCREEN, S.EDITOR_HINTS["screen"])
        screen = ttk.Label(f, textvariable=self.v_screen,
                           style="Muted.TLabel")
        screen.pack(side="left")
        self._attach_tip(screen, "多螢幕時用來確認落點所屬螢幕")

        f, h = form.field(S.LBL_RADIUS, S.EDITOR_HINTS["radius"],
                          unit=S.UNIT_PX)
        sp = self._spinbox(f, self.v_radius, 0, 1000, self._apply_editor,
                           h, S.EDITOR_HINTS["radius"], width=9)
        self._attach_tip(sp, S.EDITOR_TIPS["radius"])

        f, h = form.field(S.LBL_HOLD, S.EDITOR_HINTS["hold"], unit=S.UNIT_MS)
        self._spinbox(f, self.v_hold_min, 1, 5000, self._apply_editor,
                      h, S.EDITOR_HINTS["hold"], width=7)
        ttk.Label(f, text="–", style="Muted.TLabel").pack(side="left",
                                                          padx=self._px(3))
        self._spinbox(f, self.v_hold_max, 1, 5000, self._apply_editor,
                      h, S.EDITOR_HINTS["hold"], width=7)
        self._attach_tip(f, S.EDITOR_TIPS["hold"])

        f, h = form.field(S.LBL_INTERVAL, S.EDITOR_HINTS["interval"],
                          unit=S.UNIT_MS)
        sp = self._spinbox(f, self.v_interval, 10, 3_600_000,
                           self._apply_editor, h,
                           S.EDITOR_HINTS["interval"], width=10)
        self._attach_tip(sp, S.EDITOR_TIPS["interval"])

        f, h = form.field(S.LBL_JITTER, S.EDITOR_HINTS["jitter"],
                          unit=S.UNIT_PCT)
        sp = self._spinbox(f, self.v_jitter, 0, 100, self._apply_editor,
                           h, S.EDITOR_HINTS["jitter"], width=7)
        self.jitter_combo = ttk.Combobox(
            f, textvariable=self.v_jitter_mode,
            values=list(self.JITTER_LABELS.values()), state="readonly",
            width=7)
        self.jitter_combo.pack(side="left", padx=(self._px(6), 0))
        self.jitter_combo.bind("<<ComboboxSelected>>",
                               lambda e: self._apply_editor())
        self._attach_tip(sp, S.EDITOR_TIPS["jitter"])
        self._attach_tip(self.jitter_combo, S.EDITOR_TIPS["jitter_mode"])

        f, h = form.field(S.LBL_BUTTON, S.EDITOR_HINTS["button"])
        combo = ttk.Combobox(f, textvariable=self.v_button,
                             values=list(self.BUTTON_LABELS.values()),
                             state="readonly", width=7)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self._apply_editor())
        self._attach_tip(combo, "右鍵常用於開啟內容選單；中鍵常用於遊戲標記")
        ttk.Checkbutton(f, text=S.CHK_DOUBLE, variable=self.v_double,
                        command=self._apply_editor).pack(side="left",
                                                         padx=(self._px(10), 0))

        f, h = form.field(S.LBL_REPEAT, S.EDITOR_HINTS["repeat"],
                          unit=S.UNIT_TIMES)
        sp = self._spinbox(f, self.v_repeat, 1, 100000, self._apply_editor,
                           h, S.EDITOR_HINTS["repeat"], width=9)
        self._attach_tip(sp, S.EDITOR_TIPS["repeat"])

        f, h = form.field(S.LBL_WEIGHT, S.EDITOR_HINTS["weight"])
        sp = self._spinbox(f, self.v_weight, 1, 100, self._apply_editor,
                           h, S.EDITOR_HINTS["weight"], width=7)
        self._attach_tip(sp, S.EDITOR_TIPS["weight"])

        self.editor_empty = ttk.Frame(tab)
        self.editor_empty_hint = ttk.Label(
            self.editor_empty,
            text=S.EMPTY_EDITOR.format(
                hotkey=self.settings.config.hotkey_record),
            style="EmptyHint.TLabel", justify="left",
            wraplength=self._px(320))
        self.editor_empty_hint.pack(anchor="w", pady=(self._px(20), 0))
        self.editor_empty.grid(row=0, column=0, sticky="nw")
        self.editor_form.grid_remove()

    def _spinbox(self, parent: tk.Misc, var: tk.StringVar, lo: int, hi: int,
                 apply_cb, hint_label: ttk.Label, hint_text: str,
                 width: int = 8) -> ttk.Spinbox:
        sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var,
                         width=width)
        sp.pack(side="left")

        def check(*_args):
            raw = str(var.get()).strip()
            try:
                ok = lo <= int(raw) <= hi
            except (ValueError, tk.TclError):
                ok = False
            hint_label.configure(
                text=hint_text if ok else S.RANGE_ERROR.format(lo=lo, hi=hi),
                style="FieldHint.TLabel" if ok else "FieldError.TLabel")

        sp.bind("<KeyRelease>", check)
        sp.bind("<FocusOut>", lambda e: (check(), apply_cb()))
        sp.bind("<Return>", lambda e: (check(), apply_cb()))
        var.trace_add("write", check)
        return sp

    def _show_editor(self, index: int | None) -> None:
        if index is None or index >= len(self.settings.points):
            self._sel_index = None
            self.editor_form.grid_remove()
            self.editor_empty.grid()
            return
        self.editor_empty.grid_remove()
        self.editor_form.grid()
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
        self.v_jitter_mode.set(self.JITTER_LABELS.get(p.jitter_mode, "均勻"))
        self.v_button.set(button_label(p.button))
        self.v_double.set(p.double)
        self.v_repeat.set(str(p.repeat))
        self.v_weight.set(str(p.weight))

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
               "jitter_mode": self._key_of(self.JITTER_LABELS,
                                           str(self.v_jitter_mode.get()))
               or p.jitter_mode,
               "button": self._key_of(self.BUTTON_LABELS,
                                      str(self.v_button.get())) or p.button,
               "double": bool(self.v_double.get()),
               "repeat": self._read_int_var(self.v_repeat, p.repeat),
               "weight": self._read_int_var(self.v_weight, p.weight)}
        self.settings.points[self._sel_index] = sanitize_point(
            raw, self._sel_index, [])
        self.refresh_tree()
        self._schedule_save()

    def _test_point(self) -> None:
        if self._sel_index is None:
            messagebox.showinfo(self.APP_TITLE, S.DLG_TEST_FIRST)
            return
        if self.engine.is_running() or self.script_runner.is_running():
            messagebox.showwarning(self.APP_TITLE, S.DLG_TEST_RUNNING)
            return
        p = self.settings.points[self._sel_index]
        try:
            win32.click_once(p.x, p.y, p.button,
                             uniform_range(p.hold_min_ms, p.hold_max_ms))
        except OSError as exc:
            self._show_error(str(exc))

    def refresh_monitor_info(self) -> None:
        self.monitors = win32.list_monitors()
        lines = [f"螢幕 {m.index + 1}：{m.width}×{m.height}，{m.dpi} DPI"
                 + ("（主）" if m.primary else "")
                 + f"，範圍 ({m.left}, {m.top})" for m in self.monitors]
        self.monitor_label.config(text="\n".join(lines) or "未偵測到螢幕")


class GlobalPageMixin:
    def _build_global_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        form = FormGrid(tab, self._px, self._attach_tip)

        form.section(S.SECTION_BEHAVIOR)
        f, self.order_hint = form.field(
            S.LBL_ORDER, S.HINT_ORDER["sequential"])
        combo = ttk.Combobox(f, textvariable=self.v_order,
                             values=list(self.ORDER_LABELS.values()),
                             state="readonly", width=12)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self._apply_global())
        form.tip(combo, S.TIP_ORDER)

        f, self.move_hint = form.field(S.LBL_MOVE,
                                       S.HINT_MOVE["curve"])
        combo = ttk.Combobox(f, textvariable=self.v_move,
                             values=list(self.MOVE_LABELS.values()),
                             state="readonly", width=12)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self._apply_global())
        form.tip(combo, S.TIP_MOVE)

        f, h = form.field(S.LBL_MIN_INTERVAL, S.HINT_MIN_INTERVAL,
                          unit=S.UNIT_MS)
        sp = self._spinbox(f, self.v_min_interval, 10, 5000,
                           self._apply_global, h, S.HINT_MIN_INTERVAL,
                           width=9)
        form.tip(sp, S.TIP_MIN_INTERVAL)

        form.section(S.SECTION_STOP)
        f, self.stop_hint = form.field(
            S.LBL_STOP, S.HINT_STOP["manual"])
        combo = ttk.Combobox(f, textvariable=self.v_stop_mode,
                             values=list(self.STOP_LABELS.values()),
                             state="readonly", width=10)
        combo.grid(row=0, column=0, sticky="w")
        combo.bind("<<ComboboxSelected>>",
                   lambda e: self._apply_global())
        self.repeat_box = ttk.Frame(f)
        self.repeat_box.grid(row=0, column=1, sticky="w",
                             padx=(self._px(8), 0))
        self.spin_repeats = ttk.Spinbox(
            self.repeat_box, from_=1, to=10_000_000,
            textvariable=self.v_total_repeats, width=8)
        self.spin_repeats.pack(side="left")
        ttk.Label(self.repeat_box, text=S.UNIT_TIMES,
                  style="Muted.TLabel").pack(side="left",
                                             padx=(self._px(3), 0))
        self.time_box = ttk.Frame(f)
        self.time_box.grid(row=0, column=2, sticky="w",
                           padx=(self._px(8), 0))
        self.spin_time = ttk.Spinbox(
            self.time_box, from_=1, to=86400, textvariable=self.v_total_time,
            width=7)
        self.spin_time.pack(side="left")
        ttk.Label(self.time_box, text=S.UNIT_SEC,
                  style="Muted.TLabel").pack(side="left",
                                             padx=(self._px(3), 0))
        self.spin_repeats.bind("<FocusOut>", lambda e: self._apply_global())
        self.spin_time.bind("<FocusOut>", lambda e: self._apply_global())
        form.tip(combo, S.TIP_STOP)

        f, h = form.field(S.LBL_HOTKEYS, S.HINT_HOTKEYS)
        f.columnconfigure(0, weight=1)
        entries = ttk.Frame(f)
        entries.grid(row=0, column=0, sticky="w")
        for caption, var in (("開始/暫停", self.v_hk_start),
                             ("緊急停止", self.v_hk_stop),
                             ("新增點位", self.v_hk_record)):
            ttk.Label(entries, text=caption,
                      style="Muted.TLabel").pack(
                side="left", padx=(self._px(8), self._px(3)))
            e = ttk.Entry(entries, textvariable=var, width=7)
            e.bind("<Return>", lambda ev: self._apply_hotkeys())
            e.pack(side="left")
            self._attach_tip(e, "例：F7、Ctrl+F8；按 Enter 或「套用熱鍵」生效")
        apply_btn = ttk.Button(f, text=S.BTN_APPLY_HOTKEYS,
                               command=self._apply_hotkeys)
        apply_btn.grid(row=1, column=0, sticky="w",
                       pady=(self._px(4), 0))
        form.tip(apply_btn, S.TIP_HOTKEYS)

        self.advanced = Disclosure(tab, S.SECTION_ADVANCED, expanded=False)
        self.advanced.grid(row=form._row + 1, column=0, columnspan=2,
                           sticky="we", pady=(self._px(18), 0))
        body = self.advanced.body
        form2 = FormGrid(body, self._px, self._attach_tip)

        f, h = form2.field(S.LBL_PRESS_DELAY, S.HINT_PRESS_DELAY,
                           unit=S.UNIT_MS)
        sp = self._spinbox(f, self.v_press_delay, 0, 50,
                           self._apply_global, h, S.HINT_PRESS_DELAY,
                           width=7)
        form2.tip(sp, S.TIP_PRESS_DELAY)

        f, h = form2.field(S.LBL_PAUSE, S.HINT_PAUSE)
        ttk.Label(f, text=S.LBL_PAUSE_CHANCE,
                  style="Muted.TLabel").pack(side="left")
        self._spinbox(f, self.v_pause_chance, 0, 100, self._apply_global,
                      h, S.HINT_PAUSE, width=5)
        ttk.Label(f, text="%",
                  style="Muted.TLabel").pack(side="left",
                                             padx=(self._px(3), self._px(8)))
        self._spinbox(f, self.v_pause_min, 100, 600000, self._apply_global,
                      h, S.HINT_PAUSE, width=7)
        ttk.Label(f, text="–",
                  style="Muted.TLabel").pack(side="left",
                                             padx=self._px(2))
        self._spinbox(f, self.v_pause_max, 100, 600000, self._apply_global,
                      h, S.HINT_PAUSE, width=7)
        ttk.Label(f, text=S.UNIT_MS,
                  style="Muted.TLabel").pack(side="left",
                                             padx=(self._px(3), 0))
        form2.tip(f, S.TIP_PAUSE)

        f, h = form2.field(S.LBL_CORNER, S.HINT_CORNER)
        ttk.Checkbutton(f, text=S.LBL_CORNER_ON,
                        variable=self.v_corner_enabled,
                        command=self._apply_global).pack(side="left")
        combo = ttk.Combobox(f, textvariable=self.v_corner,
                             values=list(self.CORNER_LABELS.values()),
                             state="readonly", width=6)
        combo.pack(side="left", padx=(self._px(8), 0))
        combo.bind("<<ComboboxSelected>>", lambda e: self._apply_global())
        ttk.Label(f, text=S.LBL_CORNER_TOLERANCE,
                  style="Muted.TLabel").pack(side="left",
                                             padx=(self._px(10), self._px(3)))
        sp = self._spinbox(f, self.v_corner_size, 2, 100,
                           self._apply_global, h, S.HINT_CORNER, width=5)
        ttk.Label(f, text=("px（最少 2px）"),
                  style="Muted.TLabel").pack(side="left", padx=(self._px(3), 0))
        form2.tip(sp, S.TIP_CORNER)

        f, h = form2.field(S.LBL_MONITORS, S.HINT_MONITORS)
        self.monitor_label = ttk.Label(f, text="…", style="Muted.TLabel",
                                       justify="left")
        self.monitor_label.pack(side="left", anchor="n")
        btn = ttk.Button(f, text=S.BTN_RECALIBRATE,
                         command=self._recalibrate)
        btn.pack(side="left", padx=(self._px(10), 0), anchor="n")
        form2.tip(btn, S.TIP_MONITORS)

    def _load_global_vars(self) -> None:
        g = self.settings.config
        self.v_order.set(self.ORDER_LABELS.get(g.order, "依序"))
        self.v_move.set(self.MOVE_LABELS.get(g.move_mode, "曲線移動"))
        self.v_min_interval.set(str(g.min_interval_ms))
        self.v_pause_chance.set(str(g.long_pause_chance))
        self.v_pause_min.set(str(g.long_pause_min_ms))
        self.v_pause_max.set(str(g.long_pause_max_ms))
        self.v_stop_mode.set(self.STOP_LABELS.get(g.stop_mode, "手動熱鍵"))
        self.v_total_repeats.set(str(g.total_repeats))
        self.v_total_time.set(str(g.total_time_sec))
        self.v_hk_start.set(g.hotkey_start)
        self.v_hk_stop.set(g.hotkey_stop)
        self.v_hk_record.set(g.hotkey_record)
        self.v_corner.set(self.CORNER_LABELS.get(g.emergency_corner, "左上"))
        self.v_corner_size.set(str(g.corner_size))
        self.v_corner_enabled.set(g.corner_enabled)
        self.v_press_delay.set(str(g.press_delay_ms))
        self._update_stop_extra()

    def _apply_global(self) -> None:
        g = self.settings.config
        raw = {**vars(g),
               "order": self._key_of(self.ORDER_LABELS,
                                     str(self.v_order.get())) or g.order,
               "move_mode": self._key_of(self.MOVE_LABELS,
                                         str(self.v_move.get())) or g.move_mode,
               "min_interval_ms": self._read_int_var(self.v_min_interval,
                                                     g.min_interval_ms),
               "long_pause_chance": self._read_int_var(self.v_pause_chance,
                                                       g.long_pause_chance),
               "long_pause_min_ms": self._read_int_var(self.v_pause_min,
                                                       g.long_pause_min_ms),
               "long_pause_max_ms": self._read_int_var(self.v_pause_max,
                                                       g.long_pause_max_ms),
               "stop_mode": self._key_of(self.STOP_LABELS,
                                         str(self.v_stop_mode.get()))
               or g.stop_mode,
               "total_repeats": self._read_int_var(self.v_total_repeats,
                                                   g.total_repeats),
               "total_time_sec": self._read_int_var(self.v_total_time,
                                                    g.total_time_sec),
               "emergency_corner": self._key_of(self.CORNER_LABELS,
                                                str(self.v_corner.get()))
               or g.emergency_corner,
               "corner_size": self._read_int_var(self.v_corner_size,
                                                 g.corner_size),
               "corner_enabled": bool(self.v_corner_enabled.get()),
               "press_delay_ms": self._read_int_var(self.v_press_delay,
                                                    g.press_delay_ms)}
        self.settings.config = sanitize_global(raw, [])
        self._load_global_vars()
        self._update_hint()
        self._schedule_save()

    def _update_stop_extra(self) -> None:
        mode = self._key_of(self.STOP_LABELS, str(self.v_stop_mode.get()))
        if mode == "repeats":
            self.repeat_box.grid()
            self.time_box.grid_remove()
        elif mode == "time":
            self.time_box.grid()
            self.repeat_box.grid_remove()
        else:
            self.repeat_box.grid_remove()
            self.time_box.grid_remove()
        if hasattr(self, "stop_hint"):
            self.stop_hint.configure(text=S.HINT_STOP.get(mode or "manual", ""))
        if hasattr(self, "order_hint"):
            self.order_hint.configure(
                text=S.HINT_ORDER.get(
                    self._key_of(self.ORDER_LABELS, str(self.v_order.get()))
                    or "sequential", ""))
        if hasattr(self, "move_hint"):
            self.move_hint.configure(
                text=S.HINT_MOVE.get(
                    self._key_of(self.MOVE_LABELS, str(self.v_move.get()))
                    or "curve", ""))

    def _update_hint(self) -> None:
        g = self.settings.config
        self.hint_label.config(text=S.HINT.format(
            record=g.hotkey_record, start=g.hotkey_start, stop=g.hotkey_stop))
        self._refresh_empty()


class StatusBarMixin:
    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root, style="Surface.TFrame",
                        padding=(self._px(16), self._px(8)))
        bar.grid(row=2, column=0, sticky="ew")
        self.state_label = ttk.Label(bar, text=S.STATE_LABELS["idle"],
                                     style=S.STATE_STYLES["idle"])
        self.state_label.pack(side="left")
        self.point_value = ttk.Label(bar, text="—", style="ValueMuted.TLabel")
        self.clicks_value = ttk.Label(bar, text="0", style="Value.TLabel")
        self.time_value = ttk.Label(bar, text="00:00", style="Value.TLabel")
        for caption, value in ((S.STAT_POINT, self.point_value),
                               (S.STAT_CLICKS, self.clicks_value),
                               (S.STAT_TIME, self.time_value)):
            ttk.Label(bar, text=caption,
                      style="StatusMuted.TLabel").pack(
                side="left", padx=(self._px(20), self._px(4)))
            value.pack(side="left")

        g = self.settings.config
        self.start_btn = ttk.Button(
            bar, text=S.BTN_START.format(hotkey=g.hotkey_start),
            style="Accent.TButton", command=self.toggle_run, width=11)
        self.start_btn.pack(side="right")
        self.stop_btn = ttk.Button(
            bar, text=S.BTN_STOP.format(hotkey=g.hotkey_stop),
            style="Danger.TButton", command=self.stop_all, width=9)
        self.stop_btn.pack(side="right", padx=(0, self._px(8)))
