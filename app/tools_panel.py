"""
Tools panel -- quick access to whole-document actions (compress, add an
image/stamp, combine pages from another PDF, export) that don't need a
dedicated always-visible editing surface the way Quick Footer does.
Docked as a tab in the side notebook, replacing the former per-page
"Page Settings" tab.
"""

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from utils.ui_theme import (
    BG_ELEVATED, BG_SURFACE, BORDER, PAD, PAD_LG, RADIUS, RADIUS_SM,
    TEXT_PRIMARY, TEXT_SECONDARY, font,
)
from utils import icons as icon_lib

# Each action gets its own identity color, carried by a small icon badge
# rather than a full-perimeter colored border -- keeps the card itself
# neutral (matching every other surface in the app) while still giving
# the four actions distinct, memorable accents.
_CARD_ACCENT = ('#3468C0', '#2F9E5B', '#8A4FD1', '#C08A2E')


class ToolsPanel(ctk.CTkScrollableFrame):
    """A short list of big, clearly-labeled action cards -- click
    anywhere on a card (icon, title, or subtitle) to trigger it."""

    def __init__(self, parent,
                 on_compress: Optional[Callable] = None,
                 on_add_image: Optional[Callable] = None,
                 on_insert_pages: Optional[Callable] = None,
                 on_export: Optional[Callable] = None,
                 **kwargs):
        """
        Args:
            on_compress: "Compress PDF" card
            on_add_image: "Add Image / Stamp" card
            on_insert_pages: "Insert Pages from PDF" (combine) card
            on_export: "Export PDF" card
        """
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_compress = on_compress
        self.on_add_image = on_add_image
        self.on_insert_pages = on_insert_pages
        self.on_export = on_export
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Tools", font=font(13, "bold"), anchor="w"
                     ).pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(self, text="Actions for the whole document.", font=font(11),
                     text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", pady=(0, PAD_LG))

        self._add_action_card(
            icon="compress", title="Compress PDF",
            subtitle="Shrink the file size -- smart (keeps text sharp) or screenshot mode.",
            color=_CARD_ACCENT[0], command=self._trigger('on_compress'))
        self._add_action_card(
            icon="add_image", title="Add Image / Stamp",
            subtitle="Place a logo, signature, or stamp on the current page.",
            color=_CARD_ACCENT[1], command=self._trigger('on_add_image'))
        self._add_action_card(
            icon="insert_pages", title="Insert Pages from PDF",
            subtitle="Combine pages from another PDF into this document.",
            color=_CARD_ACCENT[2], command=self._trigger('on_insert_pages'))
        self._add_action_card(
            icon="export", title="Export PDF",
            subtitle="Save the finished document, with all edits applied, to a file.",
            color=_CARD_ACCENT[3], command=self._trigger('on_export'))

    def _trigger(self, attr_name: str) -> Callable:
        def _call():
            cb = getattr(self, attr_name)
            if cb:
                cb()
        return _call

    def _add_action_card(self, icon: str, title: str, subtitle: str,
                          color: str, command: Callable):
        card = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=RADIUS,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=5)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        inner.columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(inner, width=36, height=36, corner_radius=RADIUS_SM, fg_color=color)
        badge.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky='n')
        badge.grid_propagate(False)
        ctk.CTkLabel(badge, image=icon_lib.get(icon, size=17, color="white"), text=""
                     ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text=title, font=font(12, "bold"), text_color=TEXT_PRIMARY,
                     anchor='w').grid(row=0, column=1, sticky='ew')
        ctk.CTkLabel(inner, text=subtitle, font=font(10), text_color=TEXT_SECONDARY,
                     anchor='w', justify=tk.LEFT, wraplength=190
                     ).grid(row=1, column=1, sticky='ew', pady=(2, 0))

        def on_enter(_e=None):
            card.configure(fg_color=BG_ELEVATED, border_color=color)
        def on_leave(_e=None):
            card.configure(fg_color=BG_SURFACE, border_color=BORDER)
        card.bind("<Enter>", on_enter, add="+")
        card.bind("<Leave>", on_leave, add="+")

        self._bind_click_recursive(card, command)

    def _bind_click_recursive(self, widget, command: Callable):
        """Bind the click on the card and every descendant, so clicking
        anywhere on it (icon, title, subtitle -- not just a tiny button)
        triggers the action."""
        widget.bind("<Button-1>", lambda e: command())
        try:
            widget.configure(cursor='hand2')
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._bind_click_recursive(child, command)
