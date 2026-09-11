"""
Quick Footer panel -- a simple "N-column flat footer, same on every
page" editor, docked as a tab right alongside the live PDF preview in
the main editor window.

Typing here only updates an in-memory draft (shown live in the PDF
canvas via the shared FooterPreviewController) -- nothing is written to
disk until "Apply All" commits it to the Document (a real, undo-able
action), and a completely separate "Export PDF..." action actually
saves a file.
"""

import json
import os
import tkinter as tk
import tkinter.font as tkFont
from typing import Callable, Optional

import customtkinter as ctk

from models import Document, FooterConfig
from utils.fonts import get_filtered_fonts, get_available_tk_fonts
from utils.constants import (
    FOOTER_DEFAULT_FONT_SIZE, FOOTER_DEFAULT_COLUMNS, INCH_TO_PDF_POINT,
    QUICK_FOOTER_DRAFTS_DIR, QUICK_FOOTER_DRAFTS_FILE,
)
from utils.ui_theme import (
    ACCENT, ACCENT_HOVER, BG_SUBTLE, BG_SURFACE, BORDER, RADIUS, RADIUS_SM,
    SECONDARY_BTN, SECONDARY_BTN_HOVER, SPACE_4, SPACE_8,
    SUCCESS, TEXT_PRIMARY, TEXT_SECONDARY, font,
)
from utils.widgets import (
    create_button, create_icon_button, CollapsibleSection, NumberSpinner,
)
from app.document_commands import ChangeGlobalFooterCommand
from app.footer_mini_preview import FooterMiniPreview
from app import modern_dialogs as dialogs

_NO_DRAFT_SENTINEL = "-- Select Draft --"


class QuickFooterPanel(ctk.CTkScrollableFrame):
    """Flat, same-footer-on-every-page editor with live preview.

    (A version of this pinned the Apply/Export/Compress row outside the
    scroll area so it would always stay put at the panel's bottom edge.
    That's the "right" layout on paper, but CTkScrollableFrame turned out
    to have an internal overlay that silently painted over any sibling
    placed below it once the panel got tall -- the buttons were still
    there per grid/pack geometry, just never actually rendered. Reverted
    to the simpler single-scroll-area layout, which doesn't have a
    sibling for that overlay to cover.)
    """

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
        super().__init__(parent, fg_color="transparent", **kwargs)
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
        self.entries_frame: Optional[ctk.CTkFrame] = None
        self._suspend = False

        self.drafts: dict = self._load_drafts_from_disk()
        self.draft_var = tk.StringVar(value=_NO_DRAFT_SENTINEL)

        self._build_ui()

    def _build_ui(self):
        # Sections rather than one long wall of fields, ordered as a
        # setup -> content -> result read: pick a draft, set type, type
        # the footer, then see it. Only the section you actually type
        # into starts open.
        self._build_drafts_section()
        self._build_typography_section()
        self._build_columns_section()

        self.preview = FooterMiniPreview(self)
        self.preview.pack(fill="x")

        self.status_label = ctk.CTkLabel(self, text="", font=font(10), text_color=TEXT_SECONDARY,
                                          anchor="w")
        self.status_label.pack(fill="x", pady=(SPACE_8, SPACE_4))

        # ---- actions -- one row, not three stacked full-width buttons ----------
        actions_row = ctk.CTkFrame(self, fg_color="transparent")
        actions_row.pack(fill="x", pady=(SPACE_4, 0))
        self.apply_button = ctk.CTkButton(
            actions_row, text="Apply", command=self._apply_to_all, height=30,
            corner_radius=RADIUS_SM, fg_color=SUCCESS, hover_color="#0F7A2E", font=font(11, "bold"))
        self.apply_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        create_button(actions_row, text="Export", icon="export", command=self._request_export,
                      variant="primary", height=30, font_weight="bold"
                      ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        create_button(actions_row, text="Compress", icon="compress", command=self._request_compress,
                      variant="secondary", height=30).pack(side="left", fill="x", expand=True)

        self._set_columns()

    def _build_columns_section(self):
        section = CollapsibleSection(self, "Footer text", expanded=True)
        section.pack(fill="x", pady=(0, SPACE_8))

        # Column count lives in the header row -- it's a property OF this
        # section, not another field inside it.
        self.col_count_entry = ctk.CTkEntry(
            section.header_slot, textvariable=self.col_count_var, width=34, height=20,
            corner_radius=RADIUS_SM, border_color=BORDER, fg_color=BG_SUBTLE, font=font(11))
        self.col_count_entry.pack(side="right")
        ctk.CTkLabel(section.header_slot, text="Columns", font=font(10),
                     text_color=TEXT_SECONDARY).pack(side="right", padx=(0, 4))
        create_icon_button(section.header_slot, "check", command=self._set_columns,
                            tooltip="Apply column count", width=20, height=20, variant="tertiary"
                            ).pack(side="right", padx=(0, 2))

        self.entries_container = ctk.CTkFrame(section.body, fg_color=BG_SUBTLE,
                                               corner_radius=RADIUS)
        self.entries_container.pack(fill="x")

    def _build_typography_section(self):
        section = CollapsibleSection(self, "Typography & spacing", expanded=False)
        section.pack(fill="x", pady=(0, SPACE_8))
        grid = ctk.CTkFrame(section.body, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

        def grid_row(row, label, widget_factory, col=0):
            ctk.CTkLabel(grid, text=label, font=font(11), text_color=TEXT_SECONDARY, anchor="w"
                         ).grid(row=row, column=col, sticky="w", pady=2, padx=(0, 6))
            w = widget_factory()
            w.grid(row=row, column=col + 1, sticky="ew", pady=2, padx=(0, 10 if col == 0 else 0))
            return w

        self.font_menu = grid_row(0, "Font", lambda: ctk.CTkOptionMenu(
            grid, variable=self.font_var, values=self.fonts_available,
            command=lambda v: self._on_font_changed(), fg_color=BG_SUBTLE,
            button_color=SECONDARY_BTN, button_hover_color=SECONDARY_BTN_HOVER,
            text_color=TEXT_PRIMARY, dropdown_fg_color=BG_SURFACE, font=font(12), height=26,
            width=1))
        self.font_size_entry = grid_row(0, "Size", lambda: ctk.CTkEntry(
            grid, textvariable=self.font_size_var, height=26, corner_radius=RADIUS_SM,
            border_color=BORDER, fg_color=BG_SUBTLE, font=font(12)), col=2)
        self.font_size_entry.bind('<KeyRelease>', lambda e: self._on_font_changed())

        # Bottom gap / line spacing -- stepper spinboxes (not bare text
        # entries) so a small nudge doesn't require selecting the text,
        # typing a new value, and hoping it parses.
        grid_row(1, "Bottom gap (in)", lambda: NumberSpinner(
            grid, self.gap_var, step=0.1, minval=0.0, maxval=5.0, decimals=2,
            height=26, on_change=self._on_setting_changed))
        grid_row(1, "Line spacing (pt)", lambda: NumberSpinner(
            grid, self.line_gap_var, step=0.5, minval=0.0, maxval=50.0, decimals=1,
            height=26, on_change=self._on_setting_changed), col=2)

        self.shrink_check = ctk.CTkCheckBox(
            section.body, text="Auto-shrink page content to fit footer", font=font(11),
            variable=self.compress_var, command=self._on_setting_changed,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, checkbox_width=16, checkbox_height=16)
        self.shrink_check.pack(fill="x", pady=(SPACE_8, 0), anchor="w")

    def _build_drafts_section(self):
        section = CollapsibleSection(self, "Saved drafts", expanded=False)
        section.pack(fill="x", pady=(0, SPACE_8))
        drafts_frame = ctk.CTkFrame(section.body, fg_color="transparent")
        drafts_frame.pack(fill="x")
        # Icon buttons (fixed width, side="right") MUST be packed before
        # the expanding dropdown -- pack() hands out cavity space in
        # packing order, so an expand=True widget packed first claims the
        # whole row and pushes anything packed after it off the visible
        # edge. Packed in reverse (delete, edit, save) so the on-screen
        # left-to-right order still reads dropdown -> save -> edit -> delete.
        create_icon_button(drafts_frame, "delete", command=self._delete_selected_draft,
                            tooltip="Delete selected draft", width=24, height=24,
                            variant="danger_ghost").pack(side="right")
        create_icon_button(drafts_frame, "edit", command=self._rename_selected_draft,
                            tooltip="Rename selected draft", width=24, height=24
                            ).pack(side="right", padx=2)
        create_icon_button(drafts_frame, "save", command=self._save_current_as_draft,
                            tooltip="Save current settings as a new draft", width=24, height=24
                            ).pack(side="right")
        self.draft_menu = ctk.CTkOptionMenu(
            drafts_frame, variable=self.draft_var, values=self._draft_menu_values(),
            command=self._on_draft_selected, fg_color=BG_SUBTLE, button_color=SECONDARY_BTN,
            button_hover_color=SECONDARY_BTN_HOVER, text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_SURFACE, font=font(12), height=26, width=1)
        self.draft_menu.pack(side="left", fill="x", expand=True, padx=(0, 6))

    def _refresh_preview(self):
        """Keep the compact footer thumbnail in step with the fields."""
        total = self.document.page_count if self.document else 1
        try:
            size = int(self.font_size_var.get())
        except (tk.TclError, ValueError):
            size = FOOTER_DEFAULT_FONT_SIZE
        try:
            line_gap = float(self.line_gap_var.get())
        except (tk.TclError, ValueError):
            line_gap = 4.0
        self.preview.update_preview(
            [(l1.get(), l2.get()) for l1, l2 in self.footer_entries],
            font_name=self.font_var.get(), font_size=size, line_gap=line_gap,
            page_num=self._current_viewer_page(), total_pages=total)

    def load_document(self, document: Document):
        self.document = document
        self.status_label.configure(text=os.path.basename(document.pdf_path) if document else "")
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
        self.entries_frame = ctk.CTkFrame(self.entries_container, fg_color="transparent")
        self.entries_frame.pack(fill="x", padx=SPACE_8, pady=SPACE_4)
        # Entry columns (1 and 3) stretch to fill whatever width the side
        # panel/window currently has; label columns (0 and 2) stay
        # content-sized -- so the text boxes grow/shrink as the panel is
        # resized instead of being stuck at a fixed character width.
        self.entries_frame.columnconfigure(1, weight=1)
        self.entries_frame.columnconfigure(3, weight=1)

        font_obj = self._current_font()
        self.footer_entries = []
        self.entry_widgets = []
        try:
            count = max(1, min(5, self.col_count_var.get()))
        except tk.TclError:
            count = FOOTER_DEFAULT_COLUMNS
        for i in range(count):
            ctk.CTkLabel(self.entries_frame, text=f"Col {i + 1} Line 1", font=font(11),
                         text_color=TEXT_SECONDARY).grid(row=i, column=0, sticky='e', pady=2, padx=(0, 4))
            l1 = tk.StringVar()
            e1 = ctk.CTkEntry(self.entries_frame, textvariable=l1, font=self._as_ctk_font(font_obj),
                               height=28, corner_radius=RADIUS_SM, border_color=BORDER, fg_color=BG_SURFACE)
            e1.grid(row=i, column=1, sticky='ew', padx=2, pady=2)
            e1.bind('<KeyRelease>', lambda e: self._on_setting_changed())
            ctk.CTkLabel(self.entries_frame, text="Line 2", font=font(11),
                         text_color=TEXT_SECONDARY).grid(row=i, column=2, sticky='e', padx=(6, 4), pady=2)
            l2 = tk.StringVar()
            e2 = ctk.CTkEntry(self.entries_frame, textvariable=l2, font=self._as_ctk_font(font_obj),
                               height=28, corner_radius=RADIUS_SM, border_color=BORDER, fg_color=BG_SURFACE)
            e2.grid(row=i, column=3, sticky='ew', padx=2, pady=2)
            e2.bind('<KeyRelease>', lambda e: self._on_setting_changed())

            if preserve_values and i < len(preserve_values):
                l1.set(preserve_values[i][0])
                l2.set(preserve_values[i][1])

            self.footer_entries.append((l1, l2))
            self.entry_widgets.append((e1, e2))

        self._refresh_preview()

    @staticmethod
    def _as_ctk_font(tk_font_obj: tkFont.Font) -> ctk.CTkFont:
        """The live footer preview needs a real tkinter.font.Font (for
        accurate PDF-point sizing math elsewhere), but CTkEntry's `font`
        argument wants a CTkFont for correct scaling/theming -- build the
        matching CTkFont here rather than changing what _current_font()
        returns everywhere else it's used."""
        return ctk.CTkFont(family=tk_font_obj.cget('family'), size=tk_font_obj.cget('size'))

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
        font_obj = self._as_ctk_font(self._current_font())
        for e1, e2 in self.entry_widgets:
            e1.configure(font=font_obj)
            e2.configure(font=font_obj)
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
        # The compact preview refreshes even with no document open --
        # it's showing what you're typing, not what's on a page.
        self._refresh_preview()
        if self._suspend or not self.document or not self.on_preview_changed:
            return
        self.on_preview_changed(self._build_footer_config_from_ui(), self._current_viewer_page())

    def _apply_to_all(self):
        if not self.document:
            dialogs.show_error(self, "No Document", "Open a PDF first.")
            return
        after_config = self._build_footer_config_from_ui()
        if not any(l1 or l2 for l1, l2 in after_config.text_columns):
            dialogs.show_error(self, "Empty Footer", "Enter at least one footer line.")
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
        dialogs.show_info(self, "Applied", "Footer applied to all pages. Use Export PDF to save it to a file.")

    def _request_export(self):
        if self.on_export_requested:
            self.on_export_requested()
        else:
            dialogs.show_info(self, "Export", "Use File > Export PDF to save the final PDF.")

    def _request_compress(self):
        if self.on_compress_requested:
            self.on_compress_requested()
        else:
            dialogs.show_info(self, "Compress", "Use File > Compress PDF to save a compressed PDF.")

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
            dialogs.show_error(self, "Draft Not Saved", f"Could not write draft file:\n{e}")

    def _draft_menu_values(self) -> list:
        names = sorted(self.drafts.keys())
        return [_NO_DRAFT_SENTINEL] + names if names else [_NO_DRAFT_SENTINEL]

    def _refresh_draft_list(self, select_name: Optional[str] = None):
        self.draft_menu.configure(values=self._draft_menu_values())
        self.draft_var.set(select_name or _NO_DRAFT_SENTINEL)

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

    def _on_draft_selected(self, value: Optional[str] = None):
        name = value if value is not None else self.draft_var.get()
        if name and name != _NO_DRAFT_SENTINEL and name in self.drafts:
            self._apply_draft_data_to_ui(self.drafts[name])

    def _save_current_as_draft(self):
        suggested = self.draft_var.get()
        if suggested == _NO_DRAFT_SENTINEL:
            suggested = ""
        name = dialogs.ask_text(self, "Save Draft", "Draft name:", initial=suggested)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.drafts and not dialogs.ask_yes_no(
                self, "Overwrite Draft", f'A draft named "{name}" already exists. Overwrite it?'):
            return
        self.drafts[name] = self._draft_data_from_ui()
        self._save_drafts_to_disk()
        self._refresh_draft_list(select_name=name)

    def _rename_selected_draft(self):
        old_name = self.draft_var.get()
        if not old_name or old_name == _NO_DRAFT_SENTINEL or old_name not in self.drafts:
            dialogs.show_info(self, "Rename Draft", "Select a draft first.")
            return
        new_name = dialogs.ask_text(self, "Rename Draft", "New name:", initial=old_name)
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if new_name in self.drafts and not dialogs.ask_yes_no(
                self, "Overwrite Draft", f'A draft named "{new_name}" already exists. Overwrite it?'):
            return
        self.drafts[new_name] = self.drafts.pop(old_name)
        self._save_drafts_to_disk()
        self._refresh_draft_list(select_name=new_name)

    def _delete_selected_draft(self):
        name = self.draft_var.get()
        if not name or name == _NO_DRAFT_SENTINEL or name not in self.drafts:
            dialogs.show_info(self, "Delete Draft", "Select a draft first.")
            return
        if not dialogs.ask_yes_no(self, "Delete Draft", f'Delete draft "{name}"?', danger=True):
            return
        del self.drafts[name]
        self._save_drafts_to_disk()
        self._refresh_draft_list()
