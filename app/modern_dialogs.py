"""
Themed replacements for tkinter's messagebox/simpledialog, which render
as OS-native dialogs that clash with the rest of the UI.

Each blocks and returns a plain value, so call sites map ~1:1:
askyesno -> ask_yes_no, showinfo -> show_info, showerror -> show_error,
askstring -> ask_text.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

from utils.ui_theme import (
    ACCENT, ACCENT_HOVER, BG_APP, BG_SUBTLE, BORDER, DANGER,
    DANGER_HOVER, PAD, PAD_LG, RADIUS, RADIUS_SM, SECONDARY_BTN,
    SECONDARY_BTN_HOVER, TEXT_PRIMARY, font,
)

_ICONS = {"info": ("ℹ", ACCENT), "error": ("⚠", DANGER),
          "question": ("?", ACCENT)}


class _ModernDialog(ctk.CTkToplevel):
    """Shared chrome: icon + title + message, centered over parent, modal."""

    def __init__(self, parent, title: str, message: str, kind: str = "info",
                 width: int = 400):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=BG_APP)
        self.resizable(False, False)
        self.result = None

        icon, icon_color = _ICONS.get(kind, _ICONS["info"])

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_LG)

        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text=icon, font=font(22, "bold"), text_color=icon_color,
                     width=32).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text=message, font=font(13), text_color=TEXT_PRIMARY,
                     justify="left", wraplength=width - 90, anchor="w"
                     ).pack(side="left", fill="x", expand=True)

        self.button_row = ctk.CTkFrame(body, fg_color="transparent")
        self.button_row.pack(fill="x", pady=(PAD_LG, 0))

        self._build_buttons(self.button_row)

        self.update_idletasks()
        self._center_over_parent(parent, width)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build_buttons(self, row):
        raise NotImplementedError

    def _center_over_parent(self, parent, width: int):
        height = self.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except tk.TclError:
            px = py = 0
            pw, ph = self.winfo_screenwidth(), self.winfo_screenheight()
        x = px + max(0, (pw - width) // 2)
        y = py + max(0, (ph - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _on_cancel(self):
        self.result = False
        self._destroy_safely()

    def _finish(self, value):
        self.result = value
        self._destroy_safely()

    def _destroy_safely(self):
        # CTkToplevel runs a ~15ms after() chain on Windows to color the
        # title bar; destroying inside it logs a noisy TclError.
        self.after(50, self.destroy)


class _MessageDialog(_ModernDialog):
    def _build_buttons(self, row):
        ctk.CTkButton(
            row, text="OK", command=lambda: self._finish(True), width=100, height=34,
            corner_radius=RADIUS, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=font(12, "bold"),
        ).pack(side="right")


class _ConfirmDialog(_ModernDialog):
    def __init__(self, parent, title, message, danger=False, **kwargs):
        self._danger = danger
        super().__init__(parent, title, message, kind="error" if danger else "question", **kwargs)

    def _build_buttons(self, row):
        confirm_color = DANGER if self._danger else ACCENT
        confirm_hover = DANGER_HOVER if self._danger else ACCENT_HOVER
        ctk.CTkButton(
            row, text="Yes" if not self._danger else "Delete", command=lambda: self._finish(True),
            width=100, height=34, corner_radius=RADIUS, fg_color=confirm_color,
            hover_color=confirm_hover, font=font(12, "bold"),
        ).pack(side="right")
        ctk.CTkButton(
            row, text="Cancel" if self._danger else "No", command=lambda: self._finish(False),
            width=100, height=34, corner_radius=RADIUS, fg_color=SECONDARY_BTN,
            hover_color=SECONDARY_BTN_HOVER, text_color=TEXT_PRIMARY, font=font(12, "bold"),
        ).pack(side="right", padx=(0, 8))


class _InputDialog(_ModernDialog):
    def __init__(self, parent, title, message, initial="", **kwargs):
        self._initial = initial
        super().__init__(parent, title, message, kind="question", **kwargs)

    def _build_buttons(self, row):
        self.entry = ctk.CTkEntry(
            self.button_row.master, height=34, corner_radius=RADIUS_SM,
            border_color=BORDER, fg_color=BG_SUBTLE, font=font(12),
        )
        self.entry.insert(0, self._initial)
        self.entry.pack(fill="x", pady=(0, PAD), before=row)
        self.entry.bind("<Return>", lambda e: self._submit())
        self.entry.select_range(0, "end")
        self.entry.focus_set()

        ctk.CTkButton(
            row, text="OK", command=self._submit, width=100, height=34,
            corner_radius=RADIUS, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=font(12, "bold"),
        ).pack(side="right")
        ctk.CTkButton(
            row, text="Cancel", command=lambda: self._finish(None), width=100, height=34,
            corner_radius=RADIUS, fg_color=SECONDARY_BTN, hover_color=SECONDARY_BTN_HOVER,
            text_color=TEXT_PRIMARY, font=font(12, "bold"),
        ).pack(side="right", padx=(0, 8))

    def _submit(self):
        self._finish(self.entry.get().strip())


def show_info(parent, title: str, message: str) -> None:
    dlg = _MessageDialog(parent, title, message, kind="info")
    parent.wait_window(dlg)


def show_error(parent, title: str, message: str) -> None:
    dlg = _MessageDialog(parent, title, message, kind="error")
    parent.wait_window(dlg)


def ask_yes_no(parent, title: str, message: str, danger: bool = False) -> bool:
    dlg = _ConfirmDialog(parent, title, message, danger=danger)
    parent.wait_window(dlg)
    return bool(dlg.result)


def ask_text(parent, title: str, message: str, initial: str = "") -> Optional[str]:
    dlg = _InputDialog(parent, title, message, initial=initial)
    parent.wait_window(dlg)
    return dlg.result if dlg.result else None
