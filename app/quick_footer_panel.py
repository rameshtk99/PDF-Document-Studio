"""
Quick Footer panel -- a simple "N-column flat footer, same on every
page" editor, docked as a tab right alongside the live PDF preview in
the main editor window.

Typing here only updates an in-memory draft (shown live in the PDF
canvas via the shared FooterPreviewController) -- nothing is written to
disk until "Apply to All Pages" commits it to the Document (a real,
undo-able action), and a completely separate "Export PDF..." action
actually saves a file. This mirrors PageSettingsPanel's (the other tab)
apply-vs-export split, and both read/write the same
Document.global_settings.footer_config, so switching tabs stays
consistent.
"""

import os
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, messagebox
from typing import Callable, Optional

from models import Document, FooterConfig
from utils.fonts import get_filtered_fonts, get_available_tk_fonts
from utils.constants import FOOTER_DEFAULT_FONT_SIZE, FOOTER_DEFAULT_COLUMNS, INCH_TO_PDF_POINT
from app.document_commands import ChangeGlobalFooterCommand


class QuickFooterPanel(tk.Frame):
    """Flat, same-footer-on-every-page editor with live preview."""

    def __init__(self, parent, undo_manager=None,
                 on_preview_changed: Optional[Callable[[Optional[FooterConfig], int], None]] = None,
                 on_export_requested: Optional[Callable] = None, **kwargs):
        """
        Args:
            parent: Parent widget
            undo_manager: Shared UndoRedoManager -- "Apply to All Pages"
                pushes a real, undo-able command here
            on_preview_changed: Callback(draft_footer_config, page_number)
                fired on every keystroke/font change for the live PDF
                preview; called with (None, page_number) to clear the
                draft. page_number is always the viewer's current page,
                since this panel applies uniformly to every page.
            on_export_requested: Callback for the "Export PDF..." button
        """
        super().__init__(parent, **kwargs)
        self.document: Optional[Document] = None
        self.undo_manager = undo_manager
        self.on_preview_changed = on_preview_changed
        self.on_export_requested = on_export_requested
        self.get_current_page: Optional[Callable[[], int]] = None  # set by editor_window

        available = get_available_tk_fonts()
        self.fonts_available = get_filtered_fonts(available) or ['Helvetica']

        self.font_var = tk.StringVar(value=self.fonts_available[0])
        self.font_size_var = tk.IntVar(value=FOOTER_DEFAULT_FONT_SIZE)
        self.col_count_var = tk.IntVar(value=FOOTER_DEFAULT_COLUMNS)
        self.gap_var = tk.DoubleVar(value=0.3)
        self.line_gap_var = tk.DoubleVar(value=4.0)
        self.footer_entries = []
        self.entry_widgets = []
        self.entries_frame: Optional[tk.Frame] = None
        self._suspend = False

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg='darkgray')
        header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(header, text="Quick Footer", bg='darkgray', fg='white',
                 font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=4, pady=2)

        tk.Label(self, justify=tk.LEFT, fg='gray20', font=('Arial', 8),
                 text="Type below to preview live on the current page.\n"
                      "Click Apply to set it on ALL pages; Export PDF to save a file.\n"
                      "For a different footer per page, use the Page Settings tab."
                 ).pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 8), anchor='w')

        font_frame = tk.Frame(self)
        font_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=3)
        tk.Label(font_frame, text="Font:").grid(row=0, column=0, sticky='e')
        font_combo = ttk.Combobox(font_frame, textvariable=self.font_var, values=self.fonts_available,
                                   state='readonly', width=16)
        font_combo.grid(row=0, column=1, padx=4)
        font_combo.bind('<<ComboboxSelected>>', lambda e: self._on_font_changed())
        tk.Label(font_frame, text="Size:").grid(row=0, column=2, sticky='e', padx=(8, 0))
        tk.Spinbox(font_frame, from_=6, to=72, textvariable=self.font_size_var, width=5,
                   command=self._on_font_changed).grid(row=0, column=3, padx=4)

        gap_frame = tk.Frame(self)
        gap_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=3)
        tk.Label(gap_frame, text="Gap below content:").pack(side=tk.LEFT)
        tk.Spinbox(gap_frame, from_=0.1, to=2.0, increment=0.05, textvariable=self.gap_var,
                   width=5, command=self._on_setting_changed).pack(side=tk.LEFT, padx=4)
        tk.Label(gap_frame, text="in").pack(side=tk.LEFT)

        line_gap_frame = tk.Frame(self)
        line_gap_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 3))
        tk.Label(line_gap_frame, text="Line 1 ↔ Line 2 spacing:").pack(side=tk.LEFT)
        tk.Spinbox(line_gap_frame, from_=0, to=30, increment=1, textvariable=self.line_gap_var,
                   width=5, command=self._on_setting_changed).pack(side=tk.LEFT, padx=4)
        tk.Label(line_gap_frame, text="pt").pack(side=tk.LEFT)

        tk.Label(self, text="Note: Preeti needs a Preeti keyboard layout to type Devanagari -- "
                             "a normal keyboard types plain English no matter which font is set.",
                 fg='gray30', font=('Arial', 7), wraplength=310, justify=tk.LEFT
                 ).pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 4), anchor='w')

        col_frame = tk.Frame(self)
        col_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=3)
        tk.Label(col_frame, text="Columns:").pack(side=tk.LEFT)
        tk.Spinbox(col_frame, from_=1, to=5, textvariable=self.col_count_var,
                   width=5).pack(side=tk.LEFT, padx=4)
        tk.Button(col_frame, text="Set Columns", command=self._set_columns).pack(side=tk.LEFT, padx=6)

        self.entries_container = tk.Frame(self)
        self.entries_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.status_label = tk.Label(self, text="", fg='gray30', font=('Arial', 8), anchor='w')
        self.status_label.pack(side=tk.TOP, fill=tk.X, padx=6)

        btns = tk.Frame(self)
        btns.pack(side=tk.TOP, pady=8)
        self.apply_button = tk.Button(btns, text="Apply to All Pages", command=self._apply_to_all,
                                       bg='lightgreen', width=18)
        self.apply_button.pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="Export PDF...", command=self._request_export,
                  bg='#2e7d32', fg='white', width=14).pack(side=tk.LEFT, padx=3)

        self._set_columns()

    def load_document(self, document: Document):
        self.document = document
        self.status_label.config(text=os.path.basename(document.pdf_path) if document else "")
        self.sync_from_document()

    def sync_from_document(self):
        """Populate the fields from Document.global_settings.footer_config
        -- called on load, and after undo/redo, so this panel never shows
        stale values that no longer match the document."""
        if not self.document:
            return
        cfg = self.document.global_settings.footer_config
        self._suspend = True
        self.font_var.set(cfg.font_name if cfg.font_name in self.fonts_available else self.fonts_available[0])
        self.font_size_var.set(cfg.font_size)
        self.gap_var.set(round(cfg.bottom_margin / INCH_TO_PDF_POINT, 3))
        self.line_gap_var.set(cfg.line_gap)
        self._suspend = False
        self._set_columns(preserve_values=cfg.text_columns)

    def _set_columns(self, preserve_values=None):
        if self.entries_frame:
            self.entries_frame.destroy()
        self.entries_frame = tk.Frame(self.entries_container)
        self.entries_frame.pack(fill=tk.BOTH, expand=True)

        font_obj = self._current_font()
        self.footer_entries = []
        self.entry_widgets = []
        count = max(1, min(5, self.col_count_var.get()))
        for i in range(count):
            tk.Label(self.entries_frame, text=f"Col {i + 1} Line 1:").grid(
                row=i, column=0, sticky='e', pady=2)
            l1 = tk.StringVar()
            e1 = tk.Entry(self.entries_frame, textvariable=l1, width=14, font=font_obj)
            e1.grid(row=i, column=1, padx=2)
            e1.bind('<KeyRelease>', lambda e: self._on_setting_changed())
            tk.Label(self.entries_frame, text="Line 2:").grid(
                row=i, column=2, sticky='e', padx=(6, 0))
            l2 = tk.StringVar()
            e2 = tk.Entry(self.entries_frame, textvariable=l2, width=14, font=font_obj)
            e2.grid(row=i, column=3, padx=2)
            e2.bind('<KeyRelease>', lambda e: self._on_setting_changed())

            if preserve_values and i < len(preserve_values):
                l1.set(preserve_values[i][0])
                l2.set(preserve_values[i][1])

            self.footer_entries.append((l1, l2))
            self.entry_widgets.append((e1, e2))

    def _current_font(self) -> tkFont.Font:
        family = self.font_var.get()
        if family not in tkFont.families():
            family = 'Helvetica'
        try:
            return tkFont.Font(family=family, size=self.font_size_var.get())
        except tk.TclError:
            return tkFont.Font(family='Helvetica', size=self.font_size_var.get())

    def _on_font_changed(self):
        """Re-apply the selected font/size to the already-typed entries,
        without rebuilding them (rebuilding would wipe whatever text the
        user already typed)."""
        font_obj = self._current_font()
        for e1, e2 in self.entry_widgets:
            e1.config(font=font_obj)
            e2.config(font=font_obj)
        self._on_setting_changed()

    def _build_footer_config_from_ui(self) -> FooterConfig:
        columns = [(l1.get(), l2.get()) for l1, l2 in self.footer_entries]
        while len(columns) < 5:
            columns.append(("", ""))
        try:
            gap_pt = float(self.gap_var.get()) * INCH_TO_PDF_POINT
        except (tk.TclError, ValueError):
            gap_pt = 0.3 * INCH_TO_PDF_POINT
        try:
            line_gap_pt = float(self.line_gap_var.get())
        except (tk.TclError, ValueError):
            line_gap_pt = 4.0
        return FooterConfig(
            font_name=self.font_var.get(),
            font_size=self.font_size_var.get(),
            text_columns=columns[:5],
            bottom_margin=gap_pt,
            line_gap=line_gap_pt,
        )

    def _current_viewer_page(self) -> int:
        if self.get_current_page:
            return self.get_current_page()
        return 1

    def _on_setting_changed(self):
        """Live-preview the in-progress (not-yet-applied) footer on
        whatever page is currently visible in the viewer."""
        if self._suspend or not self.document or not self.on_preview_changed:
            return
        self.on_preview_changed(self._build_footer_config_from_ui(), self._current_viewer_page())

    def _apply_to_all(self):
        if not self.document:
            messagebox.showwarning("No Document", "Open a PDF first.")
            return
        after_config = self._build_footer_config_from_ui()
        if not any(l1 or l2 for l1, l2 in after_config.text_columns):
            messagebox.showerror("Empty Footer", "Enter at least one footer line.")
            return

        before_global = self.document.global_settings.footer_config
        before_page_configs = dict(self.document.page_configs)

        if self.undo_manager:
            self.undo_manager.execute(ChangeGlobalFooterCommand(
                self.document, before_global, after_config, before_page_configs))
        else:
            self.document.global_settings.footer_config = after_config
            self.document.page_configs.clear()

        if self.on_preview_changed:
            self.on_preview_changed(None, self._current_viewer_page())  # clear draft
        messagebox.showinfo("Applied", "Footer applied to all pages. Use Export PDF to save it to a file.")

    def _request_export(self):
        if self.on_export_requested:
            self.on_export_requested()
        else:
            messagebox.showinfo("Export", "Use File > Export PDF to save the final PDF.")
