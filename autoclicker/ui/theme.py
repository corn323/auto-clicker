"""Design tokens、字型與 ttk 樣式；主題切換只重套樣式，不重建元件。"""
from __future__ import annotations

from dataclasses import dataclass

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    danger_hover: str
    selection: str


DARK = Palette(
    name="dark",
    bg="#12161c", surface="#181e26", surface2="#202834", border="#2b3542",
    text="#e9eef6", muted="#9aa6b6",
    accent="#2f6fe0", accent_hover="#3b7bf0", accent_text="#ffffff",
    success="#35d399", warning="#f5b544", danger="#ff6b6b",
    danger_hover="#ff8585", selection="#26406b",
)

LIGHT = Palette(
    name="light",
    bg="#f5f7fa", surface="#ffffff", surface2="#eef1f6", border="#d5dce6",
    text="#1b2430", muted="#5b6675",
    accent="#2563eb", accent_hover="#1d4ed8", accent_text="#ffffff",
    success="#0b7a55", warning="#a15c07", danger="#c81e1e",
    danger_hover="#b91c1c", selection="#dbe7ff",
)

THEMES = {"dark": DARK, "light": LIGHT}


@dataclass
class Fonts:
    body: tkfont.Font
    small: tkfont.Font
    section: tkfont.Font
    head: tkfont.Font
    mono: tkfont.Font


def load_fonts(root: tk.Misc) -> Fonts:
    families = set(tkfont.families(root))
    zh = ("Microsoft JhengHei UI" if "Microsoft JhengHei UI" in families
          else "Microsoft JhengHei" if "Microsoft JhengHei" in families
          else "Segoe UI")
    mono = "Consolas" if "Consolas" in families else zh
    return Fonts(
        body=tkfont.Font(family=zh, size=10),
        small=tkfont.Font(family=zh, size=9),
        section=tkfont.Font(family=zh, size=11, weight="bold"),
        head=tkfont.Font(family=zh, size=15, weight="bold"),
        mono=tkfont.Font(family=mono, size=10),
    )


def apply_styles(root: tk.Misc, t: Palette, f: Fonts, px) -> None:
    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".", background=t.bg, foreground=t.text, font=f.body,
                borderwidth=0, focuscolor=t.accent)
    s.configure("TFrame", background=t.bg)
    s.configure("Surface.TFrame", background=t.surface)
    s.configure("TLabel", background=t.bg, foreground=t.text)
    s.configure("FieldLabel.TLabel", background=t.bg, foreground=t.text)
    s.configure("Muted.TLabel", background=t.bg, foreground=t.muted,
                font=f.small)
    s.configure("FieldHint.TLabel", background=t.bg, foreground=t.muted,
                font=f.small)
    s.configure("FieldError.TLabel", background=t.bg, foreground=t.danger,
                font=f.small)
    s.configure("Hint.TLabel", background=t.surface, foreground=t.muted,
                font=f.small)
    s.configure("Toast.TLabel", background=t.surface, foreground=t.success,
                font=f.small)
    s.configure("Head.TLabel", background=t.surface, foreground=t.text,
                font=f.head)
    s.configure("Section.TLabel", background=t.bg, foreground=t.text,
                font=f.section)
    s.configure("EmptyTitle.TLabel", background=t.bg, foreground=t.text,
                font=f.section)
    s.configure("EmptyHint.TLabel", background=t.bg, foreground=t.muted,
                font=f.small, justify="center")

    s.configure("TButton", background=t.surface2, foreground=t.text,
                padding=(px(12), px(5)), borderwidth=0)
    s.map("TButton", background=[("active", t.border), ("disabled", t.surface)],
          foreground=[("disabled", t.muted)])
    s.configure("Accent.TButton", background=t.accent, foreground=t.accent_text,
                font=f.body)
    s.map("Accent.TButton",
          background=[("disabled", t.surface2), ("active", t.accent_hover)],
          foreground=[("disabled", t.muted)])
    s.configure("Danger.TButton", background=t.danger, foreground="#ffffff")
    s.map("Danger.TButton",
          background=[("disabled", t.surface2), ("active", t.danger_hover)],
          foreground=[("disabled", t.muted)])
    s.configure("Ghost.TButton", background=t.bg, foreground=t.text,
                padding=(px(6), px(3)))
    s.map("Ghost.TButton", background=[("active", t.border)],
          foreground=[("active", t.text)])

    s.configure("TEntry", fieldbackground=t.surface2, foreground=t.text,
                insertcolor=t.text, bordercolor=t.border, lightcolor=t.border,
                darkcolor=t.border, padding=px(5))
    s.map("TEntry", focuscolor=[("focus", t.accent)])
    s.configure("Error.TEntry", fieldbackground=t.surface2, foreground=t.text,
                insertcolor=t.text, bordercolor=t.danger, lightcolor=t.danger,
                darkcolor=t.danger, padding=px(5))
    s.configure("TSpinbox", fieldbackground=t.surface2, foreground=t.text,
                insertcolor=t.text, arrowcolor=t.text, bordercolor=t.border,
                lightcolor=t.border, darkcolor=t.border, padding=px(3))
    s.configure("TCombobox", fieldbackground=t.surface2, background=t.surface2,
                foreground=t.text, arrowcolor=t.text, bordercolor=t.border,
                lightcolor=t.border, darkcolor=t.border, padding=px(4))
    s.map("TCombobox", fieldbackground=[("readonly", t.surface2)],
          selectbackground=[("readonly", t.surface2)],
          selectforeground=[("readonly", t.text)])
    s.configure("TCheckbutton", background=t.bg, foreground=t.text,
                focuscolor=t.accent)
    s.map("TCheckbutton", background=[("active", t.bg)])

    s.configure("Treeview", background=t.surface, fieldbackground=t.surface,
                foreground=t.text, rowheight=px(30), borderwidth=0,
                bordercolor=t.bg)
    s.map("Treeview", background=[("selected", t.selection)],
          foreground=[("selected", t.text)],
          lightcolor=[("active", t.bg), ("!active", t.bg), ("disabled", t.bg)],
          darkcolor=[("active", t.bg), ("!active", t.bg), ("disabled", t.bg)])
    s.configure("Treeview.Heading", background=t.surface2, foreground=t.muted,
                relief="flat", padding=(px(6), px(7)), font=f.small)
    s.map("Treeview.Heading", background=[("active", t.border)],
          lightcolor=[("active", t.surface2), ("!active", t.surface2)],
          darkcolor=[("active", t.surface2), ("!active", t.surface2)])

    s.configure("TNotebook", background=t.bg, borderwidth=0,
                bordercolor=t.bg, darkcolor=t.bg)
    s.map("TNotebook",
          lightcolor=[("active", t.bg), ("!active", t.bg), ("disabled", t.bg)],
          darkcolor=[("active", t.bg), ("!active", t.bg), ("disabled", t.bg)])
    s.configure("TNotebook.Tab", background=t.bg, foreground=t.muted,
                padding=(px(14), px(8)), bordercolor=t.bg, darkcolor=t.bg)
    s.map("TNotebook.Tab",
          background=[("selected", t.surface), ("active", t.surface)],
          foreground=[("selected", t.text), ("active", t.text)],
          lightcolor=[("selected", t.bg), ("active", t.bg), ("!selected", t.bg)],
          darkcolor=[("selected", t.bg), ("active", t.bg), ("!selected", t.bg)])

    s.configure("TScrollbar", background=t.surface2, troughcolor=t.bg,
                bordercolor=t.bg, arrowcolor=t.muted)
    s.map("TScrollbar", background=[("active", t.border)])

    for state, color in (("Idle", t.muted), ("Running", t.success),
                         ("Paused", t.warning), ("Stopping", t.danger)):
        s.configure(f"State{state}.TLabel", background=t.surface,
                    foreground=color, font=f.body)
    s.configure("Value.TLabel", background=t.surface, foreground=t.text,
                font=f.mono)
    s.configure("ValueMuted.TLabel", background=t.surface, foreground=t.muted,
                font=f.mono)
    s.configure("StatusMuted.TLabel", background=t.surface, foreground=t.muted,
                font=f.small)

    root.option_add("*TCombobox*Listbox.background", t.surface2)
    root.option_add("*TCombobox*Listbox.foreground", t.text)
    root.option_add("*TCombobox*Listbox.selectBackground", t.selection)
    root.option_add("*TCombobox*Listbox.selectForeground", t.text)
    root.configure(bg=t.bg)
