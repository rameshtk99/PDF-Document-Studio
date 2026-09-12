"""
Modern menu bar for PDF Document Studio.

Replaces the traditional Tkinter menu with a sleek, icon-enabled menu
system that matches the rest of the UI: horizontal menu buttons, floating
dropdowns with icons and keyboard shortcuts, and theme-aware styling.

Dropdown rows are customtkinter widgets rather than plain tk ones --
icon_lib hands out CTkImage, which only the ctk widgets know how to
scale and draw (a plain tk.Label renders it blank).
"""

import tkinter as tk
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from utils import ui_theme, icons as icon_lib

MENU_BAR_HEIGHT = 34
_ITEM_HEIGHT = 30
_SEPARATOR_HEIGHT = 9
_ICON_SIZE = 14


class ModernMenuItem:
    """One dropdown row: label, command, optional icon and accelerator."""

    def __init__(self, label: str, command: Optional[Callable] = None,
                 accelerator: str = "", icon: Optional[str] = None,
                 is_separator: bool = False):
        self.label = label
        self.command = command
        self.accelerator = accelerator
        self.icon = icon
        self.is_separator = is_separator


class ModernMenuBar(ctk.CTkFrame):
    """Horizontal menu bar with floating, icon-enabled dropdowns."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("fg_color", ui_theme.BG_PANEL)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("height", MENU_BAR_HEIGHT)
        super().__init__(parent, **kwargs)
        self.pack_propagate(False)

        self._menus: Dict[str, List[ModernMenuItem]] = {}
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._open_name: Optional[str] = None
        self._open_window: Optional[tk.Toplevel] = None
        self._outside_click_binding: Optional[str] = None

        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.pack(side=tk.LEFT, fill=tk.Y, padx=ui_theme.SPACE_8, pady=3)

    # ---- construction ----------------------------------------------------

    def add_menu(self, name: str, label: str, items: List[ModernMenuItem],
                 icon: str = ""):
        """Register a top-level menu and its dropdown rows."""
        self._menus[name] = items

        btn = ctk.CTkButton(
            self._container,
            text=label,
            image=icon_lib.get(icon, size=13, color=ui_theme.TEXT_SECONDARY) if icon else None,
            compound="left",
            command=lambda n=name: self._toggle(n),
            # CTkButton defaults to width=140, which would spread seven
            # menus across the whole window -- size each to its label.
            width=len(label) * 7 + (30 if icon else 16),
            height=26,
            corner_radius=ui_theme.RADIUS_SM,
            fg_color="transparent",
            hover_color=ui_theme.BG_HOVER,
            text_color=ui_theme.TEXT_SECONDARY,
            font=ui_theme.font(11),
        )
        btn.pack(side=tk.LEFT, padx=1)
        # Once a menu is open, sliding across the bar should follow, the
        # way every other desktop menu behaves.
        btn.bind("<Enter>", lambda _e, n=name: self._on_button_enter(n))
        self._buttons[name] = btn

    # ---- open / close ----------------------------------------------------

    def _toggle(self, name: str):
        if self._open_name == name:
            self.close_all_menus()
        else:
            self._open(name)

    def _on_button_enter(self, name: str):
        if self._open_name is not None and self._open_name != name:
            self._open(name)

    def _open(self, name: str):
        self.close_all_menus()
        items = self._menus.get(name)
        button = self._buttons.get(name)
        if not items or button is None:
            return

        window = tk.Toplevel(self.winfo_toplevel())
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=ui_theme.resolve(ui_theme.BORDER))

        card = ctk.CTkFrame(window, fg_color=ui_theme.BG_ELEVATED,
                            corner_radius=0, border_width=0)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        width = self._measure_width(items)
        height = 8
        for item in items:
            if item.is_separator:
                ctk.CTkFrame(card, height=1, fg_color=ui_theme.BORDER_SUBTLE,
                             corner_radius=0).pack(fill=tk.X, padx=8, pady=4)
                height += _SEPARATOR_HEIGHT
            else:
                self._add_row(card, item)
                height += _ITEM_HEIGHT

        x = button.winfo_rootx()
        y = button.winfo_rooty() + button.winfo_height() + 2
        window.geometry(f"{width}x{height}+{x}+{y}")

        self._open_name = name
        self._open_window = window
        button.configure(fg_color=ui_theme.BG_HOVER, text_color=ui_theme.TEXT_PRIMARY)

        # overrideredirect windows never take focus, so <FocusOut> never
        # fires -- watch for a click anywhere in the app instead.
        self._outside_click_binding = self.winfo_toplevel().bind(
            "<Button-1>", self._on_root_click, add="+")

    def _add_row(self, parent, item: ModernMenuItem):
        row = ctk.CTkFrame(parent, fg_color="transparent",
                           corner_radius=ui_theme.RADIUS_SM, height=_ITEM_HEIGHT)
        row.pack(fill=tk.X, padx=4, pady=1)
        row.pack_propagate(False)

        children = [row]

        icon_label = ctk.CTkLabel(
            row, text="", width=_ICON_SIZE + 2, fg_color="transparent",
            image=icon_lib.get(item.icon, size=_ICON_SIZE,
                               color=ui_theme.TEXT_SECONDARY) if item.icon else None)
        icon_label.pack(side=tk.LEFT, padx=(8, 8))
        children.append(icon_label)

        text_label = ctk.CTkLabel(
            row, text=item.label, font=ui_theme.font(11), anchor="w",
            text_color=ui_theme.TEXT_PRIMARY, fg_color="transparent")
        text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        children.append(text_label)

        if item.accelerator:
            accel_label = ctk.CTkLabel(
                row, text=item.accelerator, font=ui_theme.font(10), anchor="e",
                text_color=ui_theme.TEXT_MUTED, fg_color="transparent")
            accel_label.pack(side=tk.RIGHT, padx=(8, 10))
            children.append(accel_label)

        def on_enter(_event=None):
            row.configure(fg_color=ui_theme.BG_HOVER)

        def on_leave(_event=None):
            row.configure(fg_color="transparent")

        def on_click(_event=None):
            self.close_all_menus()
            if item.command:
                item.command()

        for widget in children:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", on_click)
            widget.configure(cursor="hand2")

    @staticmethod
    def _measure_width(items: List[ModernMenuItem]) -> int:
        label_font = ui_theme.font(11)
        accel_font = ui_theme.font(10)
        widest = 0
        for item in items:
            if item.is_separator:
                continue
            width = label_font.measure(item.label)
            if item.accelerator:
                width += accel_font.measure(item.accelerator) + 24
            widest = max(widest, width)
        # icon gutter + row padding + right margin
        return max(200, min(widest + 70, 420))

    def _on_root_click(self, event):
        """Close on a click anywhere except the menu buttons themselves --
        those run _toggle(), which would otherwise reopen what this just
        closed."""
        widget = event.widget
        while widget is not None:
            if widget in self._buttons.values() or widget is self._container:
                return
            widget = getattr(widget, "master", None)
        self.close_all_menus()

    def close_all_menus(self):
        if self._open_window is not None:
            try:
                self._open_window.destroy()
            except tk.TclError:
                pass
            self._open_window = None

        if self._open_name is not None:
            button = self._buttons.get(self._open_name)
            if button is not None:
                button.configure(fg_color="transparent",
                                 text_color=ui_theme.TEXT_SECONDARY)
            self._open_name = None

        if self._outside_click_binding is not None:
            try:
                self.winfo_toplevel().unbind("<Button-1>", self._outside_click_binding)
            except tk.TclError:
                pass
            self._outside_click_binding = None
