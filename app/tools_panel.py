"""
Tools panel -- quick access to whole-document actions (compress, add an
image/stamp, combine pages from another PDF, export) that don't need a
dedicated always-visible editing surface the way Quick Footer does.
Docked as a tab in the side notebook, replacing the former per-page
"Page Settings" tab.
"""

import tkinter as tk
from typing import Callable, Optional


class ToolsPanel(tk.Frame):
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
        super().__init__(parent, **kwargs)
        self.on_compress = on_compress
        self.on_add_image = on_add_image
        self.on_insert_pages = on_insert_pages
        self.on_export = on_export
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg='darkgray')
        header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(header, text="Tools", bg='darkgray', fg='white',
                 font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=4, pady=2)

        tk.Label(self, text="Actions for the whole document.", fg='gray40',
                 font=('Arial', 8), anchor='w').pack(side=tk.TOP, fill=tk.X, padx=10, pady=(8, 4))

        body = tk.Frame(self)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._add_action_card(
            body, icon="\U0001F5DC", title="Compress PDF",
            subtitle="Shrink the file size -- smart (keeps text sharp) or screenshot mode.",
            color='#1565C0', command=self._trigger('on_compress'))
        self._add_action_card(
            body, icon="\U0001F5BC", title="Add Image / Stamp",
            subtitle="Place a logo, signature, or stamp on the current page.",
            color='#2e7d32', command=self._trigger('on_add_image'))
        self._add_action_card(
            body, icon="\U0001F4CE", title="Insert Pages from PDF",
            subtitle="Combine pages from another PDF into this document.",
            color='#6a1b9a', command=self._trigger('on_insert_pages'))
        self._add_action_card(
            body, icon="\U0001F4E4", title="Export PDF",
            subtitle="Save the finished document, with all edits applied, to a file.",
            color='#8a5a00', command=self._trigger('on_export'))

    def _trigger(self, attr_name: str) -> Callable:
        def _call():
            cb = getattr(self, attr_name)
            if cb:
                cb()
        return _call

    def _add_action_card(self, parent, icon: str, title: str, subtitle: str,
                          color: str, command: Callable):
        card = tk.Frame(parent, bg='white', highlightbackground=color,
                         highlightcolor=color, highlightthickness=2, bd=0)
        card.pack(fill=tk.X, pady=6)

        inner = tk.Frame(card, bg='white')
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        inner.columnconfigure(1, weight=1)

        tk.Label(inner, text=icon, font=('Segoe UI Emoji', 20), bg='white', fg=color
                 ).grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky='n')
        tk.Label(inner, text=title, font=('Arial', 11, 'bold'), bg='white', fg='#1a1a1a',
                 anchor='w').grid(row=0, column=1, sticky='ew')
        tk.Label(inner, text=subtitle, font=('Arial', 8), bg='white', fg='gray45',
                 anchor='w', justify=tk.LEFT, wraplength=190
                 ).grid(row=1, column=1, sticky='ew', pady=(2, 0))

        self._bind_click_recursive(card, command)

    def _bind_click_recursive(self, widget, command: Callable):
        """Bind the click on the card and every descendant, so clicking
        anywhere on it (icon, title, subtitle -- not just a tiny button)
        triggers the action."""
        widget.bind("<Button-1>", lambda e: command())
        try:
            widget.config(cursor='hand2')
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._bind_click_recursive(child, command)
