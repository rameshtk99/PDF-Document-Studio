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

import json
import os
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, messagebox, simpledialog
from typing import Callable, Optional

from models import Document, FooterConfig
from utils.fonts import get_filtered_fonts, get_available_tk_fonts
from utils.constants import (
    FOOTER_DEFAULT_FONT_SIZE, FOOTER_DEFAULT_COLUMNS, INCH_TO_PDF_POINT,
    QUICK_FOOTER_DRAFTS_DIR, QUICK_FOOTER_DRAFTS_FILE,
)
from app.document_commands import ChangeGlobalFooterCommand


class QuickFooterPanel(tk.Frame):
    """Flat, same-footer-on-every-page editor with live preview."""

    def __init__(self, parent, undo_manager=None,
                 on_preview_changed: Optional[Callable[[Optional[FooterConfig], int], None]] = None,
                 on_export_requested: Optional[Callable] = None,
                 on_compress_requested: Optional[Callable] = None, **kwargs):
        """
        Args:
            parent: Parent widget
            undo_manager: Shared UndoRedoManager -- "Apply All"
                pushes a real, undo-able command here
            on_preview_changed: Callback(draft_footer_config, page_number)
                fired on every keystroke/font change for the live PDF
                preview; called with (None, page_number) to clear the
                draft. page_number is always the viewer's current page,
                since this panel applies uniformly to every page.
            on_export_requested: Callback for the "Export PDF..." button
                (exports as-is, no compression)
            on_compress_requested: Callback for the "Compress PDF..."
                button (exports, then runs it through the compressor)
        """
        super().__init__(parent, **kwargs)
        self.document: Optional[Document] = None
        self.undo_manager = undo_manager
        self.on_preview_changed = on_preview_changed
        self.on_export_requested = on_export_requested
        self.on_compress_requested = on_compress_requested
        self.get_current_page: Optional[Callable[[], int]] = None  # set by editor_window

        available = get_available_tk_fonts()
        self.fonts_available = get_filtered_fonts(available) or ['Helvetica']

        self.font_var = tk.StringVar(value=self.fonts_available[0])
        self.font_size_var = tk.IntVar(value=FOOTER_DEFAULT_FONT_SIZE)
        self.col_count_var = tk.IntVar(value=FOOTER_DEFAULT_COLUMNS)
        self.gap_var = tk.DoubleVar(value=1.0)
        self.line_gap_var = tk.DoubleVar(value=4.0)
        self.compress_var = tk.BooleanVar(value=True)
        self.footer_entries = []
        self.entry_widgets = []
        self.entries_frame: Optional[tk.Frame] = None
        self._suspend = False

        self.drafts: dict = self._load_drafts_from_disk()
        self.draft_var = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg='darkgray')
        header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(header, text="Quick Footer", bg='darkgray', fg='white',
                 font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=4, pady=2)

        drafts_frame = tk.Frame(self)
        drafts_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(8, 8))
        drafts_frame.columnconfigure(1, weight=1)
        tk.Label(drafts_frame, text="Draft:").grid(row=0, column=0, sticky='w')
        self.draft_combo = ttk.Combobox(drafts_frame, textvariable=self.draft_var,
                                         values=sorted(self.drafts.keys()), state='readonly')
        self.draft_combo.grid(row=0, column=1, sticky='ew', padx=4)
        self.draft_combo.bind('<<ComboboxSelected>>', lambda e: self._on_draft_selected())
        icon_font = ('Segoe UI Emoji', 10)
        tk.Button(drafts_frame, text="\U0001F4BE", font=icon_font, width=3,
                  command=self._save_current_as_draft).grid(row=0, column=2, padx=(6, 1))
        tk.Button(drafts_frame, text="✎", font=icon_font, width=3,
                  command=self._rename_selected_draft).grid(row=0, column=3, padx=1)
        tk.Button(drafts_frame, text="\U0001F5D1", font=icon_font, width=3,
                  command=self._delete_selected_draft).grid(row=0, column=4, padx=1)

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
        tk.Spinbox(gap_frame, from_=0.1, to=4.0, increment=0.05, textvariable=self.gap_var,
                   width=5, command=self._on_setting_changed).pack(side=tk.LEFT, padx=4)
        tk.Label(gap_frame, text="in").pack(side=tk.LEFT)

        line_gap_frame = tk.Frame(self)
        line_gap_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 3))
        tk.Label(line_gap_frame, text="Line 1 ↔ Line 2 spacing:").pack(side=tk.LEFT)
        tk.Spinbox(line_gap_frame, from_=0, to=100, increment=1, textvariable=self.line_gap_var,
                   width=5, command=self._on_setting_changed).pack(side=tk.LEFT, padx=4)
        tk.Label(line_gap_frame, text="pt").pack(side=tk.LEFT)

        shrink_frame = tk.Frame(self)
        shrink_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 3))
        tk.Checkbutton(shrink_frame, text="Auto-shrink page content to fit footer",
                       variable=self.compress_var,
                       command=self._on_setting_changed
                       ).pack(side=tk.LEFT)

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
        self.apply_button = tk.Button(btns, text="Apply All", command=self._apply_to_all,
                                       bg='lightgreen', width=12)
        self.apply_button.pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="Export PDF...", command=self._request_export,
                  bg='#2e7d32', fg='white', width=13).pack(side=tk.LEFT, padx=3)
        tk.Button(btns, text="Compress PDF...", command=self._request_compress,
                  bg='#1565c0', fg='white', width=13).pack(side=tk.LEFT, padx=3)

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
        self.compress_var.set(getattr(cfg, 'compress_content', True))
        self._suspend = False
        self._set_columns(preserve_values=cfg.text_columns)

    def _set_columns(self, preserve_values=None):
        if self.entries_frame:
            self.entries_frame.destroy()
        self.entries_frame = tk.Frame(self.entries_container)
        self.entries_frame.pack(fill=tk.BOTH, expand=True)
        # Entry columns (1 and 3) stretch to fill whatever width the side
        # panel/window currently has; label columns (0 and 2) stay
        # content-sized -- so the text boxes grow/shrink as the panel is
        # resized instead of being stuck at a fixed character width.
        self.entries_frame.columnconfigure(1, weight=1)
        self.entries_frame.columnconfigure(3, weight=1)

        font_obj = self._current_font()
        self.footer_entries = []
        self.entry_widgets = []
        count = max(1, min(5, self.col_count_var.get()))
        for i in range(count):
            tk.Label(self.entries_frame, text=f"Col {i + 1} Line 1:").grid(
                row=i, column=0, sticky='e', pady=3)
            l1 = tk.StringVar()
            e1 = tk.Entry(self.entries_frame, textvariable=l1, font=font_obj)
            e1.grid(row=i, column=1, sticky='ew', padx=2)
            e1.bind('<KeyRelease>', lambda e: self._on_setting_changed())
            tk.Label(self.entries_frame, text="Line 2:").grid(
                row=i, column=2, sticky='e', padx=(6, 0))
            l2 = tk.StringVar()
            e2 = tk.Entry(self.entries_frame, textvariable=l2, font=font_obj)
            e2.grid(row=i, column=3, sticky='ew', padx=2)
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
            compress_content=self.compress_var.get(),
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

    def _request_compress(self):
        if self.on_compress_requested:
            self.on_compress_requested()
        else:
            messagebox.showinfo("Compress", "Use File > Compress PDF to save a compressed PDF.")

    # ------------------------------------------------------------------ named drafts

    @staticmethod
    def _load_drafts_from_disk() -> dict:
        try:
            with open(QUICK_FOOTER_DRAFTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_drafts_to_disk(self):
        try:
            os.makedirs(QUICK_FOOTER_DRAFTS_DIR, exist_ok=True)
            with open(QUICK_FOOTER_DRAFTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.drafts, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showwarning("Draft Not Saved", f"Could not write draft file:\n{e}")

    def _refresh_draft_list(self, select_name: Optional[str] = None):
        self.draft_combo.config(values=sorted(self.drafts.keys()))
        self.draft_var.set(select_name or "")

    def _draft_data_from_ui(self) -> dict:
        return {
            'font_name': self.font_var.get(),
            'font_size': self.font_size_var.get(),
            'gap_in': self.gap_var.get(),
            'line_gap': self.line_gap_var.get(),
            'compress': self.compress_var.get(),
            'columns': self.col_count_var.get(),
            'entries': [[l1.get(), l2.get()] for l1, l2 in self.footer_entries],
        }

    def _apply_draft_data_to_ui(self, data: dict):
        self._suspend = True
        self.font_var.set(data.get('font_name') if data.get('font_name') in self.fonts_available
                           else self.fonts_available[0])
        self.font_size_var.set(data.get('font_size', FOOTER_DEFAULT_FONT_SIZE))
        self.gap_var.set(data.get('gap_in', 1.0))
        self.line_gap_var.set(data.get('line_gap', 4.0))
        self.compress_var.set(data.get('compress', True))
        self.col_count_var.set(data.get('columns', FOOTER_DEFAULT_COLUMNS))
        self._suspend = False
        self._set_columns(preserve_values=data.get('entries'))
        self._on_setting_changed()

    def _on_draft_selected(self):
        name = self.draft_var.get()
        if name and name in self.drafts:
            self._apply_draft_data_to_ui(self.drafts[name])

    def _save_current_as_draft(self):
        suggested = self.draft_var.get()
        name = simpledialog.askstring("Save Draft", "Draft name:", initialvalue=suggested, parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.drafts and not messagebox.askyesno(
                "Overwrite Draft", f'A draft named "{name}" already exists. Overwrite it?'):
            return
        self.drafts[name] = self._draft_data_from_ui()
        self._save_drafts_to_disk()
        self._refresh_draft_list(select_name=name)

    def _rename_selected_draft(self):
        old_name = self.draft_var.get()
        if not old_name or old_name not in self.drafts:
            messagebox.showinfo("Rename Draft", "Select a draft first.")
            return
        new_name = simpledialog.askstring("Rename Draft", "New name:", initialvalue=old_name, parent=self)
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if new_name in self.drafts and not messagebox.askyesno(
                "Overwrite Draft", f'A draft named "{new_name}" already exists. Overwrite it?'):
            return
        self.drafts[new_name] = self.drafts.pop(old_name)
        self._save_drafts_to_disk()
        self._refresh_draft_list(select_name=new_name)

    def _delete_selected_draft(self):
        name = self.draft_var.get()
        if not name or name not in self.drafts:
            messagebox.showinfo("Delete Draft", "Select a draft first.")
            return
        if not messagebox.askyesno("Delete Draft", f'Delete draft "{name}"?'):
            return
        del self.drafts[name]
        self._save_drafts_to_disk()
        self._refresh_draft_list()
