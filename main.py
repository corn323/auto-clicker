"""AutoClicker 入口：先設定 DPI 感知，再建立 Tk 視窗。"""
from __future__ import annotations

from autoclicker import win32
from autoclicker.config import load_settings


def main() -> None:
    win32.enable_dpi_awareness()  # 必須在建立任何視窗之前
    import tkinter as tk
    from autoclicker.ui import App

    root = tk.Tk()
    settings, warnings = load_settings()
    App(root, settings, warnings)
    root.mainloop()


if __name__ == "__main__":
    main()
