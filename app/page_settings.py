"""
Page-specific footer settings UI panel for editing per-page footer configuration
"""

import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, messagebox
from typing import Optional, Callable
from models import Document, FooterConfig
from utils.fonts import get_filtered_fonts, get_available_tk_fonts
from utils.constants import INCH_TO_PDF_POINT
from app.document_commands import (
    ChangePageFooterCommand, ChangeGlobalFooterCommand, ResetPageFooterCommand,
)


class PageSettingsPanel(tk.Frame):
    """Panel for editing page-specific footer settings
    
    Features:
    - Select and navigate between pages
    - Edit footer text columns for current page
    - Customize font name and size per page
    - Apply settings to single page, range, or all pages
    - Visual indication of page-specific vs global settings
    - Real-time validation
    """
    
    def __init__(self, parent, document: Optional[Document] = None,
                 undo_manager=None,
                 on_settings_changed: Optional[Callable] = None,
                 on_export_requested: Optional[Callable] = None,
                 on_preview_changed: Optional[Callable[[Optional[FooterConfig], int], None]] = None,
                 **kwargs):
        """
        Initialize page settings panel

        Args:
            parent: Parent widget
            document: Document object to edit
            undo_manager: Shared UndoRedoManager -- Apply/Reset actions
                push real, undo-able commands here instead of mutating
                the document directly
            on_settings_changed: Callback when settings change
            on_export_requested: Callback for the "Export PDF..." button,
                so the actual export flow lives in one place (the main
                window) instead of duplicated here
            on_preview_changed: Callback(draft_footer_config, page_number)
                fired on every keystroke/font change so the live PDF
                preview can show the in-progress (not-yet-applied)
                footer; called with (None, page_number) to clear the
                draft and fall back to showing the committed state
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)

        self.document = document
        self.undo_manager = undo_manager
        self.on_settings_changed = on_settings_changed
        self.on_export_requested = on_export_requested
        self.on_preview_changed = on_preview_changed
        self.current_page = 1
        
        # Available fonts -- pulled from the system (via the same helper
        # the CLI/Quick Footer tab use), so custom TTF fonts like Preeti
        # actually show up here too instead of a fixed hardcoded list.
        self.available_fonts = get_filtered_fonts(get_available_tk_fonts())

        self.entry_widgets = []

        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI"""
        # Header
        header = tk.Frame(self, bg='darkgray')
        header.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        
        tk.Label(header, text="Page Settings", bg='darkgray', fg='white',
                font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        # Page navigation
        nav_frame = tk.Frame(self)
        nav_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        tk.Label(nav_frame, text="Page:").pack(side=tk.LEFT)
        
        tk.Button(nav_frame, text="◄ Prev", command=self.prev_page, width=8).pack(side=tk.LEFT, padx=2)
        
        self.page_label = tk.Label(nav_frame, text="1 of 1", font=('Arial', 10, 'bold'), width=10)
        self.page_label.pack(side=tk.LEFT, padx=5)
        
        tk.Button(nav_frame, text="Next ►", command=self.next_page, width=8).pack(side=tk.LEFT, padx=2)
        
        # Jump to page
        tk.Label(nav_frame, text="Go to:").pack(side=tk.LEFT, padx=(10, 0))
        self.page_input = tk.Entry(nav_frame, width=5)
        self.page_input.pack(side=tk.LEFT, padx=2)
        tk.Button(nav_frame, text="Jump", command=self.jump_to_page, width=6).pack(side=tk.LEFT)
        
        # Settings area
        settings_frame = tk.LabelFrame(self, text="Footer Settings", font=('Arial', 9, 'bold'))
        settings_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Status indicator
        self.status_label = tk.Label(settings_frame, text="Using global settings", 
                                     fg='blue', font=('Arial', 8, 'italic'))
        self.status_label.pack(anchor=tk.W, padx=5, pady=2)
        
        # Font settings
        font_frame = tk.Frame(settings_frame)
        font_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(font_frame, text="Font:").pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value=self.available_fonts[0])
        self.font_dropdown = ttk.Combobox(font_frame, textvariable=self.font_var,
                                          values=self.available_fonts, state='readonly', width=20)
        self.font_dropdown.pack(side=tk.LEFT, padx=5)
        self.font_dropdown.bind('<<ComboboxSelected>>', lambda e: self._on_font_changed())

        tk.Label(font_frame, text="Size:").pack(side=tk.LEFT, padx=(10, 0))
        self.size_var = tk.IntVar(value=13)
        self.size_spinbox = tk.Spinbox(font_frame, from_=8, to=72, textvariable=self.size_var,
                                       width=5, command=self._on_font_changed)
        self.size_spinbox.pack(side=tk.LEFT, padx=5)
        tk.Label(font_frame, text="pt").pack(side=tk.LEFT)

        gap_frame = tk.Frame(settings_frame)
        gap_frame.pack(fill=tk.X, padx=5, pady=(0, 2))
        tk.Label(gap_frame, text="Gap below content:").pack(side=tk.LEFT)
        self.gap_var = tk.DoubleVar(value=0.3)
        self.gap_spinbox = tk.Spinbox(gap_frame, from_=0.1, to=2.0, increment=0.05,
                                       textvariable=self.gap_var, width=5,
                                       command=self._on_setting_changed)
        self.gap_spinbox.pack(side=tk.LEFT, padx=5)
        tk.Label(gap_frame, text="in").pack(side=tk.LEFT)

        line_gap_frame = tk.Frame(settings_frame)
        line_gap_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        tk.Label(line_gap_frame, text="Line 1 ↔ Line 2 spacing:").pack(side=tk.LEFT)
        self.line_gap_var = tk.DoubleVar(value=4.0)
        self.line_gap_spinbox = tk.Spinbox(line_gap_frame, from_=0, to=30, increment=1,
                                            textvariable=self.line_gap_var, width=5,
                                            command=self._on_setting_changed)
        self.line_gap_spinbox.pack(side=tk.LEFT, padx=5)
        tk.Label(line_gap_frame, text="pt").pack(side=tk.LEFT)

        tk.Label(settings_frame,
                 text="Gap below content = how far the footer block sits below the page's "
                      "actual content (pulled down to the page edge only if content fills the "
                      "page). Line spacing = the gap between each column's Top and Bottom line.",
                 fg='gray30', font=('Arial', 7), wraplength=310, justify=tk.LEFT
                 ).pack(anchor=tk.W, padx=5, pady=(0, 4))

        # Footer columns (simplified to 3 columns for space)
        columns_frame = tk.LabelFrame(settings_frame, text="Footer Text (max 3 columns shown)",
                                      font=('Arial', 8))
        columns_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(columns_frame, text='Tip: "Page {page} of {total}"',
                 fg='gray30', font=('Arial', 7, 'italic')).pack(anchor=tk.W, padx=5, pady=(2, 4))

        self.column_entries = []
        for i in range(3):
            col_frame = tk.LabelFrame(columns_frame, text=f"Col {i + 1}", font=('Arial', 8))
            col_frame.pack(fill=tk.X, padx=5, pady=4)

            # Top and Bottom each get their own full-width row -- side by
            # side they had to share ~300px with 4 labels, which squeezed
            # the Bottom box down to almost nothing.
            font_obj = self._current_font()
            tk.Label(col_frame, text="Top:", anchor='w', width=7).grid(
                row=0, column=0, sticky='w', padx=(4, 2), pady=2)
            line1_var = tk.StringVar()
            entry1 = tk.Entry(col_frame, textvariable=line1_var, font=font_obj)
            entry1.grid(row=0, column=1, sticky='ew', padx=(0, 4), pady=2)
            entry1.bind('<KeyRelease>', lambda e: self._on_setting_changed())

            tk.Label(col_frame, text="Bottom:", anchor='w', width=7).grid(
                row=1, column=0, sticky='w', padx=(4, 2), pady=2)
            line2_var = tk.StringVar()
            entry2 = tk.Entry(col_frame, textvariable=line2_var, font=font_obj)
            entry2.grid(row=1, column=1, sticky='ew', padx=(0, 4), pady=2)
            entry2.bind('<KeyRelease>', lambda e: self._on_setting_changed())

            col_frame.columnconfigure(1, weight=1)

            self.column_entries.append((line1_var, line2_var))
            self.entry_widgets.append((entry1, entry2))

        # Apply buttons
        buttons_frame = tk.Frame(settings_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=(5, 0))

        tk.Button(buttons_frame, text="Apply to This Page", command=self.apply_to_page,
                 bg='lightblue', width=20).pack(side=tk.LEFT, padx=2)

        tk.Button(buttons_frame, text="Apply to All Pages", command=self.apply_to_all,
                 bg='lightgreen', width=20).pack(side=tk.LEFT, padx=2)

        tk.Button(buttons_frame, text="Reset to Global", command=self.reset_to_global,
                 bg='lightyellow', width=20).pack(side=tk.LEFT, padx=2)

        tk.Label(settings_frame,
                 text="⚠ \"Apply to All Pages\" replaces the global footer AND clears "
                      "any page-specific edits you've made on other pages.",
                 fg='#8a5a00', font=('Arial', 7), wraplength=310, justify=tk.LEFT
                 ).pack(anchor=tk.W, padx=5, pady=(4, 5))

        export_frame = tk.Frame(settings_frame)
        export_frame.pack(fill=tk.X, padx=5, pady=(0, 6))
        tk.Button(export_frame, text="Export PDF...", command=self._request_export,
                  bg='#2e7d32', fg='white', width=20).pack(side=tk.LEFT, padx=2)
        tk.Label(export_frame, text="(saves ALL pages with their current footer settings)",
                 fg='gray30', font=('Arial', 7)).pack(side=tk.LEFT, padx=6)

    def _current_font(self) -> tkFont.Font:
        family = self.font_var.get() if self.available_fonts else 'Helvetica'
        if family not in tkFont.families():
            family = 'Helvetica'
        try:
            return tkFont.Font(family=family, size=self.size_var.get() if hasattr(self, 'size_var') else 13)
        except tk.TclError:
            return tkFont.Font(family='Helvetica', size=13)

    def _on_font_changed(self):
        """Re-apply the selected font/size to the footer text boxes live
        (without rebuilding them, so typed text isn't lost), then notify
        as a normal setting change."""
        font_obj = self._current_font()
        for entry1, entry2 in self.entry_widgets:
            entry1.config(font=font_obj)
            entry2.config(font=font_obj)
        self._on_setting_changed()

    def _request_export(self):
        """Trigger the actual PDF export (handled by the main window)"""
        if self.on_export_requested:
            self.on_export_requested()
        else:
            messagebox.showinfo("Export", "Use File > Export PDF to save the final PDF.")
    
    def load_document(self, document: Document):
        """Load a document for editing
        
        Args:
            document: Document object to edit
        """
        self.document = document
        self.current_page = 1
        self._refresh_ui()
    
    def _refresh_ui(self):
        """Refresh UI with current page settings"""
        if not self.document:
            return
        
        # Update page label
        self.page_label.config(text=f"{self.current_page} of {self.document.page_count}")
        
        # Get current page config
        config = self.document.get_page_config(self.current_page)
        
        # Update status
        if config.overrides_global:
            self.status_label.config(text="✓ Using page-specific settings", fg='darkgreen')
        else:
            self.status_label.config(text="Using global settings", fg='blue')
        
        # Update font settings
        self.font_var.set(config.footer_config.font_name)
        self.size_var.set(config.footer_config.font_size)
        self.gap_var.set(round(config.footer_config.bottom_margin / INCH_TO_PDF_POINT, 3))
        self.line_gap_var.set(config.footer_config.line_gap)
        font_obj = self._current_font()
        for entry1, entry2 in self.entry_widgets:
            entry1.config(font=font_obj)
            entry2.config(font=font_obj)

        # Update footer columns
        columns = config.footer_config.text_columns
        for i, (line1_var, line2_var) in enumerate(self.column_entries):
            if i < len(columns):
                line1, line2 = columns[i]
                line1_var.set(line1)
                line2_var.set(line2)
            else:
                line1_var.set("")
                line2_var.set("")
    
    def _build_footer_config_from_ui(self) -> FooterConfig:
        """Snapshot the current UI fields into a fresh FooterConfig --
        used both for the live preview draft and for the config actually
        committed on Apply, so the two always match exactly."""
        columns = [(l1.get(), l2.get()) for l1, l2 in self.column_entries]
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
            font_size=self.size_var.get(),
            text_columns=columns[:5],
            bottom_margin=gap_pt,
            line_gap=line_gap_pt,
        )

    def _on_setting_changed(self):
        """Called on every keystroke/font change -- updates the live PDF
        preview with a draft (not yet applied/saved) footer, and notifies
        as a normal setting change."""
        if self.document and self.on_preview_changed:
            self.on_preview_changed(self._build_footer_config_from_ui(), self.current_page)
        if self.on_settings_changed:
            self.on_settings_changed()
    
    def next_page(self):
        """Go to next page"""
        if not self.document:
            return
        if self.current_page < self.document.page_count:
            self.current_page += 1
            self._refresh_ui()

    def prev_page(self):
        """Go to previous page"""
        if not self.document:
            return
        if self.current_page > 1:
            self.current_page -= 1
            self._refresh_ui()
    
    def jump_to_page(self):
        """Jump to specified page"""
        try:
            page_num = int(self.page_input.get())
            if 1 <= page_num <= self.document.page_count:
                self.current_page = page_num
                self.page_input.delete(0, tk.END)
                self._refresh_ui()
            else:
                messagebox.showerror("Invalid Page", 
                                   f"Page must be between 1 and {self.document.page_count}")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid page number")
    
    def apply_to_page(self):
        """Commit the current UI settings to this page only. Pushed
        through the shared undo manager (if provided) so it's a real,
        undo-able action -- this only sets the in-memory Document state
        (and the live preview), it never touches disk; use Export PDF
        separately to actually save."""
        if not self.document:
            return

        current_config = self.document.get_page_config(self.current_page)
        before_had_override = self.current_page in self.document.page_configs
        before_config = current_config.footer_config
        after_config = self._build_footer_config_from_ui()

        if self.undo_manager:
            self.undo_manager.execute(ChangePageFooterCommand(
                self.document, self.current_page, before_config, after_config, before_had_override))
        else:
            page_config = self.document.get_page_config(self.current_page)
            page_config.footer_config = after_config
            self.document.set_page_config(self.current_page, page_config)

        if self.on_preview_changed:
            self.on_preview_changed(None, self.current_page)  # clear draft, fall back to committed state
        self._refresh_ui()
        messagebox.showinfo("Applied", f"Footer applied to page {self.current_page}. "
                                        f"Use Export PDF to save it to a file.")

    def apply_to_all(self):
        """Commit the current UI settings as the global footer for every
        page, clearing per-page overrides -- undo-able, no file write."""
        if not self.document:
            return

        response = messagebox.askyesno("Confirm",
                                      "Apply these settings to all pages?\nThis will override all page-specific settings.")
        if not response:
            return

        before_global = self.document.global_settings.footer_config
        before_page_configs = dict(self.document.page_configs)
        after_global = self._build_footer_config_from_ui()

        if self.undo_manager:
            self.undo_manager.execute(ChangeGlobalFooterCommand(
                self.document, before_global, after_global, before_page_configs))
        else:
            self.document.global_settings.footer_config = after_global
            self.document.page_configs.clear()

        if self.on_preview_changed:
            self.on_preview_changed(None, self.current_page)
        self._refresh_ui()
        messagebox.showinfo("Applied", "Footer applied to all pages. "
                                        "Use Export PDF to save it to a file.")

    def reset_to_global(self):
        """Remove this page's footer override -- undo-able, no file write."""
        if not self.document:
            return

        response = messagebox.askyesno("Confirm",
                                      f"Reset page {self.current_page} to global settings?")
        if not response:
            return

        if self.current_page in self.document.page_configs:
            before_config = self.document.page_configs[self.current_page].footer_config
            if self.undo_manager:
                self.undo_manager.execute(ResetPageFooterCommand(
                    self.document, self.current_page, before_config))
            else:
                del self.document.page_configs[self.current_page]

        if self.on_preview_changed:
            self.on_preview_changed(None, self.current_page)
        self._refresh_ui()
        messagebox.showinfo("Applied", f"Page {self.current_page} reset to global settings.")
    
    def get_current_page(self) -> int:
        """Get current page number
        
        Returns:
            Current page number (1-indexed)
        """
        return self.current_page
    
    def set_current_page(self, page_num: int):
        """Set current page
        
        Args:
            page_num: Page number (1-indexed)
        """
        if self.document and 1 <= page_num <= self.document.page_count:
            self.current_page = page_num
            self._refresh_ui()
