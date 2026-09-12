"""
Modern menu bar for PDF Document Studio.

Replaces traditional Tkinter menu with a sleek, icon-enabled menu system
that matches the modern UI design. Features:
- Horizontal menu items with icons
- Smooth dropdown menus
- Keyboard shortcuts display
- Theme-aware styling
"""

import tkinter as tk
from typing import Callable, List, Optional, Tuple
import customtkinter as ctk

from utils import ui_theme, icons as icon_lib
from utils.tooltip import attach as attach_tooltip


class ModernMenuItem:
    """One menu item: label, icon, command, optional accelerator."""
    def __init__(self, label: str, command: Optional[Callable] = None,
                 accelerator: str = "", icon: Optional[str] = None,
                 is_separator: bool = False):
        self.label = label
        self.command = command
        self.accelerator = accelerator
        self.icon = icon
        self.is_separator = is_separator


class ModernMenuBar(ctk.CTkFrame):
    """Sleek horizontal menu bar with modern dropdowns.

    Menus are defined declaratively and rendered with icons, keyboard
    shortcuts, and smooth hover effects.
    """

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("fg_color", ui_theme.BG_SURFACE)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("height", 36)
        super().__init__(parent, **kwargs)
        self.pack_propagate(False)

        self._menus = {}  # name -> list of ModernMenuItem
        self._buttons = {}  # name -> CTkButton
        self._dropdowns = {}  # name -> Toplevel
        self._current_dropdown = None

        # Container for menu buttons
        self.menu_container = ctk.CTkFrame(self, fg_color="transparent")
        self.menu_container.pack(side=tk.LEFT, fill=tk.X, padx=4, pady=4)

    def add_menu(self, name: str, label: str, items: List[ModernMenuItem], icon: str = ""):
        """Add a top-level menu with items."""
        self._menus[name] = items

        # Create menu button
        btn = ctk.CTkButton(
            self.menu_container, text=label,
            image=icon_lib.get(icon, size=13, color=ui_theme.TEXT_SECONDARY) if icon else None,
            compound="left",
            command=lambda: self._toggle_menu(name),
            height=28, corner_radius=ui_theme.RADIUS_SM,
            fg_color="transparent", hover_color=ui_theme.BG_HOVER,
            text_color=ui_theme.TEXT_SECONDARY,
            font=ui_theme.font(11, "normal"),
        )
        btn.pack(side=tk.LEFT, padx=2)
        self._buttons[name] = btn

    def _toggle_menu(self, menu_name: str):
        """Open or close a dropdown menu."""
        if self._current_dropdown == menu_name:
            self._close_menu(menu_name)
            self._current_dropdown = None
        else:
            if self._current_dropdown:
                self._close_menu(self._current_dropdown)
            self._open_menu(menu_name)
            self._current_dropdown = menu_name

    def _open_menu(self, menu_name: str):
        """Create and display dropdown menu."""
        if menu_name not in self._menus:
            return

        items = self._menus[menu_name]
        button = self._buttons[menu_name]

        x = button.winfo_rootx()
        y = button.winfo_rooty() + button.winfo_height() + 4

        # Calculate menu height (dynamic based on items)
        separator_h = 8
        item_h = 32
        height = sum(separator_h if item.is_separator else item_h for item in items) + 12

        # Width should accommodate longest label + shortcut
        width = 300

        # Create floating menu window
        dropdown = tk.Toplevel(self.master)
        dropdown.wm_overrideredirect(True)
        dropdown.geometry(f"{width}x{height}+{x}+{y}")
        dropdown.configure(bg=ui_theme.resolve(ui_theme.BG_ELEVATED))

        menu_frame = tk.Frame(dropdown, bg=ui_theme.resolve(ui_theme.BG_ELEVATED),
                              highlightthickness=1, highlightbackground=ui_theme.resolve(ui_theme.BORDER))
        menu_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        for item in items:
            if item.is_separator:
                sep = tk.Frame(menu_frame, height=1, bg=ui_theme.resolve(ui_theme.BORDER))
                sep.pack(fill=tk.X, pady=4)
            else:
                self._add_menu_item_widget(menu_frame, item, dropdown)

        dropdown.bind("<FocusOut>", lambda e: self._close_menu(menu_name))
        dropdown.lift()

        self._dropdowns[menu_name] = dropdown

    def _add_menu_item_widget(self, parent, item: ModernMenuItem, dropdown_window):
        """Create a single menu item widget."""
        item_frame = tk.Frame(parent, bg=ui_theme.resolve(ui_theme.BG_ELEVATED),
                              highlightthickness=0, height=32)
        item_frame.pack(fill=tk.X, padx=4, pady=2)
        item_frame.pack_propagate(False)

        def on_click():
            if item.command:
                item.command()
            self._close_menu(next((k for k, v in self._dropdowns.items() if v == dropdown_window), None))
            self._current_dropdown = None

        def on_hover(hovering: bool):
            color = ui_theme.resolve(ui_theme.BG_HOVER) if hovering else ui_theme.resolve(ui_theme.BG_ELEVATED)
            for w in widgets_to_bind:
                w.configure(bg=color)

        # Keep reference to widgets for hover
        widgets_to_bind = [item_frame]

        # Icon + Label (left side)
        if item.icon:
            icon_img = icon_lib.get(item.icon, size=14, color=ui_theme.TEXT_SECONDARY)
            icon_label = tk.Label(
                item_frame, image=icon_img, text="",
                bg=ui_theme.resolve(ui_theme.BG_ELEVATED), bd=0, highlightthickness=0)
            icon_label.image = icon_img  # Keep reference
            icon_label.pack(side=tk.LEFT, padx=(6, 10), pady=0)
            widgets_to_bind.append(icon_label)

        label_widget = tk.Label(
            item_frame, text=item.label, font=("Segoe UI", 10),
            fg=ui_theme.resolve(ui_theme.TEXT_PRIMARY),
            bg=ui_theme.resolve(ui_theme.BG_ELEVATED), anchor="w", bd=0, highlightthickness=0)
        label_widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
        widgets_to_bind.append(label_widget)

        # Accelerator (shortcut, right side)
        accel_widget = tk.Label(
            item_frame, text=item.accelerator if item.accelerator else "",
            font=("Segoe UI", 8),
            fg=ui_theme.resolve(ui_theme.TEXT_SECONDARY),
            bg=ui_theme.resolve(ui_theme.BG_ELEVATED), bd=0, highlightthickness=0)
        if item.accelerator:
            accel_widget.pack(side=tk.RIGHT, padx=8, pady=0)
        widgets_to_bind.append(accel_widget)

        # Hover and click effects
        for w in widgets_to_bind:
            w.bind("<Enter>", lambda e: on_hover(True))
            w.bind("<Leave>", lambda e: on_hover(False))
            w.bind("<Button-1>", lambda e: on_click())
            w.configure(cursor="hand2")

    def _close_menu(self, menu_name: Optional[str]):
        """Close a dropdown menu."""
        if menu_name and menu_name in self._dropdowns:
            try:
                self._dropdowns[menu_name].destroy()
            except tk.TclError:
                pass
            del self._dropdowns[menu_name]

    def close_all_menus(self):
        """Close all open menus."""
        for dropdown in list(self._dropdowns.values()):
            try:
                dropdown.destroy()
            except tk.TclError:
                pass
        self._dropdowns.clear()
        self._current_dropdown = None
