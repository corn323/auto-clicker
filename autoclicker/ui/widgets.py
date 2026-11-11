"""可重用 UI 元件：Tooltip、可捲動區、收合區、表單列。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Tooltip:
    """延遲顯示的說明氣泡；離開或點擊即消失，位置不超出工作畫面。"""

    DELAY_MS = 500

    def __init__(self, widget: tk.Misc, text: str, get_palette,
                 font, px) -> None:
        self.widget = widget
        self.text = text
        self._get_palette = get_palette
        self._font = font
        self._px = px
        self._after: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        try:
            self._after = self.widget.after(self.DELAY_MS, self._show)
        except tk.TclError:
            self._after = None

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self) -> None:
        self._after = None
        if self._tip is not None or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            px = self._px
            t = self._get_palette()
            x = self.widget.winfo_rootx() + px(10)
            y = (self.widget.winfo_rooty() + self.widget.winfo_height()
                 + px(6))
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            try:
                tip.attributes("-topmost", True)
            except tk.TclError:
                pass
            frame = tk.Frame(tip, bg=t.border, padx=1, pady=1)
            frame.pack(fill="both", expand=True)
            label = tk.Label(frame, text=self.text, bg=t.surface2, fg=t.text,
                             font=self._font, justify="left", anchor="w",
                             padx=px(8), pady=px(6), wraplength=px(280))
            label.pack()
            tip.update_idletasks()
            sw = self.widget.winfo_screenwidth()
            sh = self.widget.winfo_screenheight()
            w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
            if x + w > sw - px(8):
                x = max(px(8), sw - w - px(8))
            if y + h > sh - px(8):
                y = max(px(8), self.widget.winfo_rooty() - h - px(6))
            tip.geometry(f"+{x}+{y}")
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


class ScrollArea(ttk.Frame):
    """Canvas + 內部 Frame；視窗太小時可垂直捲動，滾輪僅在游標進入時生效。"""

    def __init__(self, parent: tk.Misc, px, style: str = "TFrame") -> None:
        super().__init__(parent, style=style)
        self._px = px
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg="#000000")
        self.vbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style=style)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self.inner.bind("<Enter>", self._bind_wheel)
        self.inner.bind("<Leave>", self._unbind_wheel)

    def _on_inner(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _unbind_wheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _wheel(self, event) -> None:
        if self.inner.winfo_height() <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def apply_theme(self, t) -> None:
        self.canvas.configure(bg=t.bg)


class Disclosure(ttk.Frame):
    """預設收合的區塊；標題列可展開／收合。"""

    def __init__(self, parent: tk.Misc, title: str, expanded: bool = False
                 ) -> None:
        super().__init__(parent)
        self._title = title
        self._open = expanded
        self.columnconfigure(0, weight=1)
        self.btn = ttk.Button(self, style="Ghost.TButton", command=self.toggle)
        self.btn.grid(row=0, column=0, sticky="w")
        self.body = ttk.Frame(self)
        self.body.grid(row=1, column=0, sticky="we", pady=(4, 0))
        self._render()

    def _render(self) -> None:
        self.btn.configure(text=("▾ " if self._open else "▸ ") + self._title)
        if self._open:
            self.body.grid()
        else:
            self.body.grid_remove()

    def toggle(self) -> None:
        self._open = not self._open
        self._render()

    def set_open(self, open_: bool) -> None:
        self._open = open_
        self._render()


class FormGrid:
    """兩欄式設定表單：標籤＋控制項，下方一句灰字說明。"""

    def __init__(self, parent: ttk.Frame, px, attach_tip) -> None:
        self.parent = parent
        self._px = px
        self._attach_tip = attach_tip
        self._row = 0
        self._hints: list[ttk.Label] = []
        parent.columnconfigure(0, minsize=px(96))
        parent.columnconfigure(1, weight=1)
        parent.bind("<Configure>", self._resize, add="+")

    def _resize(self, event) -> None:
        width = max(self._px(160), event.width - self._px(112))
        for hint in self._hints:
            hint.configure(wraplength=width)

    def field(self, label: str, hint: str = "", unit: str | None = None
              ) -> tuple[ttk.Frame, ttk.Label]:
        row = self._row
        self._row += 2
        text = f"{label}（{unit}）" if unit else label
        ttk.Label(self.parent, text=text,
                  style="FieldLabel.TLabel").grid(row=row, column=0,
                                                  sticky="nw",
                                                  pady=(self._px(7), 0))
        holder = ttk.Frame(self.parent)
        holder.grid(row=row, column=1, sticky="we",
                    pady=(self._px(7), 0))
        hint_label = ttk.Label(self.parent, text=hint, style="FieldHint.TLabel",
                               justify="left")
        hint_label.grid(row=row + 1, column=1, sticky="w",
                        pady=(self._px(1), self._px(2)))
        self._hints.append(hint_label)
        return holder, hint_label

    def section(self, title: str) -> None:
        row = self._row
        self._row += 1
        ttk.Label(self.parent, text=title,
                  style="Section.TLabel").grid(row=row, column=0, columnspan=2,
                                               sticky="w",
                                               pady=(self._px(18),
                                                     self._px(2)))

    def note(self, text: str) -> None:
        row = self._row
        self._row += 1
        ttk.Label(self.parent, text=text, style="FieldHint.TLabel",
                  justify="left").grid(row=row, column=0, columnspan=2,
                                       sticky="w", pady=(self._px(2), 0))

    def tip(self, widget: tk.Misc, text: str) -> None:
        if text:
            self._attach_tip(widget, text)
