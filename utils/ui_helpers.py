"""
Small shared Tkinter UI helpers used across dialogs/Toplevels.
"""

import tkinter as tk


def center_window(win, parent, width: int, height: int, margin: int = 80):
    """Size and place `win` centered over `parent`, clamped to the screen.

    Use instead of a bare geometry("WxH"), which leaves placement to the
    window manager (Windows stacks new windows top-left, not over the
    app). Dialogs that can be shrunk to fit should have an expanding
    scroll area, or content gets clipped rather than scrolled.
    """
    screen_w, screen_h = win.winfo_screenwidth(), win.winfo_screenheight()
    max_w = max(200, screen_w - margin)
    max_h = max(150, screen_h - margin)
    if width > max_w or height > max_h:
        # Scale both axes down by the SAME factor rather than clamping
        # each independently -- keeps the dialog's proportions (its
        # "default" look/ratio) consistent across screen sizes instead of
        # letting one axis get squashed relative to the other.
        scale = min(max_w / width, max_h / height)
        width = max(200, round(width * scale))
        height = max(150, round(height * scale))

    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
    except tk.TclError:
        px = py = 0
        pw = ph = 0

    if pw <= 1 or ph <= 1:
        # Parent not yet mapped/sized (e.g. still initializing) -- fall
        # back to centering on the screen instead of at (0,0).
        px = py = 0
        pw, ph = screen_w, screen_h

    x = px + (pw - width) // 2
    y = py + (ph - height) // 2

    # Reserve half the margin at the trailing edge too (not just via the
    # size clamp above) -- winfo_screenheight() reports the full display
    # resolution, not the work area excluding the Windows taskbar, so a
    # dialog whose height fits the raw screen size could still land with
    # its bottom edge (often the primary/Cancel buttons) hidden behind it.
    edge_reserve = margin // 2
    x = min(max(0, x), max(0, screen_w - width - edge_reserve))
    y = min(max(0, y), max(0, screen_h - height - edge_reserve))

    win.geometry(f"{width}x{height}+{x}+{y}")
