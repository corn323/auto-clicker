"""腳本分頁：載入、驗證、匯出、執行；僅操作宣告式 JSON。"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import scripting
from . import strings as S


class ScriptPageMixin:
    def _build_script_tab(self, tab: ttk.Frame) -> None:
        tab.rowconfigure(3, weight=1)
        tab.columnconfigure(0, weight=1)
        bar = ttk.Frame(tab)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, self._px(8)))
        for text, cmd in ((S.BTN_SCRIPT_LOAD, self._script_load),
                          (S.BTN_SCRIPT_EXPORT, self._script_export),
                          (S.BTN_SCRIPT_VALIDATE, self._script_validate),
                          (S.BTN_SCRIPT_EXAMPLE, self._script_load_example)):
            ttk.Button(bar, text=text, command=cmd).pack(
                side="left", padx=(0, self._px(6)))
        bar2 = ttk.Frame(tab)
        bar2.grid(row=1, column=0, sticky="ew", pady=(0, self._px(8)))
        ttk.Button(bar2, text=S.BTN_SCRIPT_RUN, style="Accent.TButton",
                   command=self._script_run).pack(side="left")
        ttk.Button(bar2, text=S.BTN_SCRIPT_STOP,
                   command=self.stop_all).pack(side="left",
                                               padx=(self._px(6), 0))
        self.example_combo = ttk.Combobox(bar2, state="readonly", width=16)
        self.example_combo.pack(side="right")
        self._refresh_examples()
        self.script_path_label = ttk.Label(tab, style="Muted.TLabel",
                                           text=S.SCRIPT_NO_FILE)
        self.script_path_label.grid(row=2, column=0, sticky="w")
        text_frame = ttk.Frame(tab)
        text_frame.grid(row=3, column=0, sticky="nsew",
                        pady=(self._px(4), self._px(4)))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        t = self.palette
        self.script_text = tk.Text(text_frame, height=14, wrap="word",
                                   undo=True, bg=t.surface, fg=t.text,
                                   insertbackground=t.text, relief="flat",
                                   padx=self._px(10), pady=self._px(8),
                                   highlightthickness=1,
                                   highlightbackground=t.border,
                                   highlightcolor=t.accent,
                                   font=self.fonts.mono)
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
                                    justify="left")
        self.script_msg.grid(row=4, column=0, sticky="w")
        tab.bind("<Configure>", self._resize_script_msg, add="+")

    def _resize_script_msg(self, event) -> None:
        self.script_msg.configure(
            wraplength=max(self._px(240), event.width - self._px(24)))

    def _examples_dir(self) -> Path:
        base = Path(getattr(sys, "_MEIPASS",
                            Path(__file__).resolve().parent.parent.parent))
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
            title=S.SCRIPT_DIALOG_LOAD_TITLE,
            filetypes=[(S.FILE_JSON, "*.json"), (S.FILE_ALL, "*.*")])
        if not path:
            return
        self._script_load_from_path(Path(path))

    def _script_load_from_path(self, path: Path) -> None:
        script, errors, warnings = scripting.load_script(path)
        if script is None:
            messagebox.showerror(
                self.APP_TITLE,
                S.DLG_SCRIPT_LOAD_FAILED.format(errors="\n".join(errors[:10])))
            return
        self._fill_script_text(script, str(path), warnings)

    def _script_load_example(self) -> None:
        name = self.example_combo.get()
        if name:
            self._script_load_from_path(self._examples_dir() / name)

    def _script_export(self) -> None:
        script, errors, _warn = self._script_text_parse()
        if script is None:
            messagebox.showerror(
                self.APP_TITLE,
                S.DLG_SCRIPT_EXPORT_FAILED.format(
                    errors="\n".join(errors[:10])))
            return
        path = filedialog.asksaveasfilename(
            title=S.SCRIPT_DIALOG_EXPORT_TITLE, defaultextension=".json",
            initialfile="script.json",
            filetypes=[(S.FILE_JSON, "*.json")])
        if not path:
            return
        try:
            scripting.save_script(script, Path(path))
            self.script_path_label.config(text=path)
            self._show_script_msg([S.SCRIPT_MSG_EXPORTED])
        except OSError as exc:
            messagebox.showerror(
                self.APP_TITLE, S.DLG_EXPORT_ERROR.format(reason=exc.strerror))

    def _script_validate(self) -> None:
        script, errors, warnings = self._script_text_parse()
        if script is None:
            self._show_script_msg(errors)
        else:
            self._show_script_msg(
                [S.SCRIPT_MSG_OK.format(count=len(script["steps"]))]
                + warnings)

    def _show_script_msg(self, lines: list[str]) -> None:
        first = lines[0] if lines else ""
        bad = not first.startswith(("驗證通過", "已匯出"))
        self.script_msg.config(
            text="\n".join(lines[:10]),
            foreground=self.palette.warning if bad else self.palette.muted)

    def _script_run(self) -> None:
        if self.engine.is_running() or self.script_runner.is_running():
            messagebox.showwarning(self.APP_TITLE, S.DLG_SCRIPT_RUNNING)
            return
        script, errors, warnings = self._script_text_parse()
        if script is None:
            messagebox.showerror(
                self.APP_TITLE,
                S.DLG_SCRIPT_RUN_FAILED.format(
                    errors="\n".join(errors[:10])))
            return
        if warnings:
            self._show_script_msg(warnings)
        self._apply_global()
        g = self.settings.config
        self.script_runner.start(script, g.emergency_corner, g.corner_size)
        self._update_run_button()
