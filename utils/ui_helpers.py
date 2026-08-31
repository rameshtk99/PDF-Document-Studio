"""
Small shared Tkinter UI helpers used across dialogs/Toplevels.
"""

import tkinter as tk


def center_window(win, parent, width: int, height: int, margin: int = 80):
    """Position `win` centered over `parent`'s current on-screen position,
    clamped so it never lands partly off-screen -- AND clamped so its
    requested width/height never exceed the actual screen size (minus
    `margin` for taskbar/title bar breathing room), so a dialog sized for
    a large monitor doesn't get cut off on a small laptop screen. Sets
    the window's full geometry (size + position) in one call -- pass the
    same width/height you'd otherwise give a plain
    win.geometry(f"{width}x{height}") call.

    A plain win.geometry("WxH") (no position) leaves placement up to the
    window manager, which on Windows tends to stack new windows near the
    top-left of the screen rather than over the app -- this is what
    should be called instead, right after construction. Callers whose
    dialog has a scrollable content area should size that area to expand
    (row/columnconfigure weight, not plain pack()) so shrinking to fit
    the screen makes that area scroll rather than clipping other content
    (e.g. buttons) -- clamping the outer window size alone doesn't give
    you that for free.

    Toplevel windows keep their normal title bar (nothing here disables
    it), so they remain draggable/movable by the user exactly as any
    other window is.
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

    x = min(max(0, x), max(0, screen_w - width))
    y = min(max(0, y), max(0, screen_h - height))

    win.geometry(f"{width}x{height}+{x}+{y}")
