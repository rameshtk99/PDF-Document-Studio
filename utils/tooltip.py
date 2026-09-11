"""
Lightweight hover tooltip for icon-only buttons and other controls whose
purpose isn't obvious from a label alone. Plain tkinter (a borderless
Toplevel), styled to match the app's theme -- not tied to customtkinter
so it works on any widget.
"""

import tkinter as tk

from utils import ui_theme


class Tooltip:
    def __init__(self, widget, text: str, delay: int = 450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def set_text(self, text: str):
        self.text = text

    def _schedule(self, _event=None):
        self._cancel_timer()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel_timer(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        if self._tip is not None or not self.text:
            return
        try:
            if str(self.widget.cget("state")) == "disabled":
                return
        except tk.TclError:
            pass
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except tk.TclError:
            return

        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        border = tk.Frame(tip, bg=ui_theme.resolve(ui_theme.BORDER_STRONG))
        border.pack()
        tk.Label(
            border, text=self.text, bg=ui_theme.resolve(ui_theme.BG_SURFACE),
            fg=ui_theme.resolve(ui_theme.TEXT_PRIMARY),
            font=(ui_theme.FONT_FAMILY, 9), padx=8, pady=4, justify=tk.LEFT,
        ).pack(padx=1, pady=1)

        tip.update_idletasks()
        w = tip.winfo_width()
        screen_w = tip.winfo_screenwidth()
        x = max(0, min(x - w // 2, screen_w - w))
        tip.geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None):
        self._cancel_timer()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def attach(widget, text: str, delay: int = 450) -> Tooltip:
    return Tooltip(widget, text, delay=delay)
