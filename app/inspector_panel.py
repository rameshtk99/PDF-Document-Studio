"""
Modern Segmented Inspector Panel for PDF Document Studio.

Replaces the squished accordion with a sleek, full-height tabbed inspector
(Footer, Files, Tools, Image). Keeps the same API as AccordionPanel so
editor_window integrates seamlessly.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, Optional

import customtkinter as ctk

from utils import ui_theme, icons as icon_lib
from utils.widgets import create_icon_button

TAB_HEIGHT = 38
RAIL_WIDTH = 36


class ModernInspectorPanel(ctk.CTkFrame):
    """Sleek tabbed inspector panel.

    Each tab receives the entire vertical height of the panel, avoiding
    nested scrollbar squeeze. Supports collapsing to a narrow icon rail.
    """

    def __init__(self, parent, on_collapsed_change: Optional[Callable[[bool], None]] = None, **kwargs):
        kwargs.setdefault("fg_color", ui_theme.BG_PANEL)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(parent, **kwargs)

        self._on_collapsed_change = on_collapsed_change
        self._tabs: Dict[str, dict] = {}  # name -> {title, icon, body, btn, rail_btn, visible}
        self._active_tab: Optional[str] = None
        self._collapsed = False

        # --- Main Expanded UI ---
        self._expanded_container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._expanded_container.pack(fill=tk.BOTH, expand=True)

        # Tab header bar
        self._header_bar = ctk.CTkFrame(
            self._expanded_container, fg_color=ui_theme.BG_SURFACE,
            corner_radius=0, height=TAB_HEIGHT)
        self._header_bar.pack(side=tk.TOP, fill=tk.X)
        self._header_bar.pack_propagate(False)

        # Tab buttons container
        self._tab_btn_container = ctk.CTkFrame(self._header_bar, fg_color="transparent")
        self._tab_btn_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 4), pady=4)

        # Collapse chevron button on header bar
        self._collapse_btn = create_icon_button(
            self._header_bar, "chevron_right", command=self.toggle_collapsed,
            tooltip="Hide panel", size=13, width=28, height=28, variant="tertiary"
        )
        self._collapse_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=4)

        # Subtle separator line beneath tab bar
        ctk.CTkFrame(
            self._expanded_container, height=1, fg_color=ui_theme.BORDER,
            corner_radius=0).pack(side=tk.TOP, fill=tk.X)

        # Content container where active tab's body lives
        self._content_container = ctk.CTkFrame(
            self._expanded_container, fg_color="transparent", corner_radius=0)
        self._content_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Collapsed Rail UI ---
        self._rail = ctk.CTkFrame(self, fg_color=ui_theme.BG_PANEL, width=RAIL_WIDTH, corner_radius=0)
        self._rail.pack_propagate(False)

        # Top expand button in rail
        create_icon_button(
            self._rail, "chevron_left", command=self.toggle_collapsed,
            tooltip="Expand inspector", size=13, width=28, height=28, variant="tertiary"
        ).pack(side=tk.TOP, pady=(6, 8))

        self._rail_btn_container = ctk.CTkFrame(self._rail, fg_color="transparent")
        self._rail_btn_container.pack(side=tk.TOP, fill=tk.X)

    def add(self, name: str, title: str, icon: Optional[str] = None, expanded: bool = False) -> ctk.CTkFrame:
        """Add a tab. Returns the body frame for child widgets."""
        if not icon:
            icon_map = {
                "footer": "footer",
                "files": "document",
                "tools": "compress",
                "image": "add_image",
            }
            icon = icon_map.get(name, "document")

        body = ctk.CTkFrame(self._content_container, fg_color="transparent", corner_radius=0)

        # Expanded tab button
        btn = ctk.CTkButton(
            self._tab_btn_container,
            text=title,
            image=icon_lib.get(icon, size=13, color=ui_theme.TEXT_SECONDARY),
            compound="left",
            height=28,
            corner_radius=ui_theme.RADIUS_SM,
            font=ui_theme.font(11, "normal"),
            fg_color="transparent",
            hover_color=ui_theme.BG_HOVER,
            text_color=ui_theme.TEXT_SECONDARY,
            command=lambda n=name: self.focus_section(n),
        )

        # Collapsed rail icon button
        rail_btn = create_icon_button(
            self._rail_btn_container,
            icon,
            command=lambda n=name: self._on_rail_click(n),
            tooltip=title,
            size=15,
            width=28,
            height=28,
            variant="ghost",
        )

        self._tabs[name] = {
            "title": title,
            "icon": icon,
            "body": body,
            "btn": btn,
            "rail_btn": rail_btn,
            "visible": True,
        }

        self._rebuild_tab_strip()

        if expanded or self._active_tab is None:
            self.focus_section(name)

        return body

    def _rebuild_tab_strip(self):
        """Pack visible tab buttons evenly in the tab bar and rail."""
        for name, tab in self._tabs.items():
            if tab["visible"]:
                tab["btn"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
                tab["rail_btn"].pack(side=tk.TOP, pady=3)
            else:
                tab["btn"].pack_forget()
                tab["rail_btn"].pack_forget()

    def focus_section(self, name: str):
        """Activate the specified tab."""
        if name not in self._tabs:
            return

        self._active_tab = name

        # Show active body, hide others
        for t_name, tab in self._tabs.items():
            if t_name == name:
                tab["body"].pack(fill=tk.BOTH, expand=True)
                tab["btn"].configure(
                    fg_color=ui_theme.ACCENT_SOFT,
                    text_color=ui_theme.ACCENT,
                    font=ui_theme.font(11, "bold"),
                    image=icon_lib.get(tab["icon"], size=13, color=ui_theme.ACCENT),
                )
                tab["rail_btn"].configure(
                    fg_color=ui_theme.ACCENT_SOFT,
                )
            else:
                tab["body"].pack_forget()
                tab["btn"].configure(
                    fg_color="transparent",
                    text_color=ui_theme.TEXT_SECONDARY,
                    font=ui_theme.font(11, "normal"),
                    image=icon_lib.get(tab["icon"], size=13, color=ui_theme.TEXT_SECONDARY),
                )
                tab["rail_btn"].configure(
                    fg_color="transparent",
                )

    def set_section_visible(self, name: str, visible: bool):
        """Show or hide a tab button completely (e.g. Image tab)."""
        if name not in self._tabs:
            return
        self._tabs[name]["visible"] = visible
        self._rebuild_tab_strip()

        # If active tab was hidden, fall back to first visible tab
        if not visible and self._active_tab == name:
            for t_name, tab in self._tabs.items():
                if tab["visible"]:
                    self.focus_section(t_name)
                    break

    def toggle_collapsed(self):
        """Toggle collapsed rail vs full expanded panel."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._expanded_container.pack_forget()
            self._rail.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self._rail.pack_forget()
            self._expanded_container.pack(fill=tk.BOTH, expand=True)

        if self._on_collapsed_change:
            self._on_collapsed_change(self._collapsed)

    def _on_rail_click(self, name: str):
        """Clicking an icon in the collapsed rail expands and focuses that tab."""
        if self._collapsed:
            self.toggle_collapsed()
        self.focus_section(name)

    def collapsed(self) -> bool:
        return self._collapsed
