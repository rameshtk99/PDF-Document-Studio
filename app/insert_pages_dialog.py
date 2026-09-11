"""
Insert Page(s) from PDF dialog -- lets the user pick a source PDF, see it
as a responsive grid of real page thumbnails with a running "N of M
selected" count, click pages on/off (all selected by default), then
hands the resulting PageRefs back to the caller. The caller
(editor_window.py) owns the actual insertion position and the
undo-managed Document.insert_pages call (via InsertPagesCommand) -- this
dialog only reads the chosen source file's metadata/thumbnails and
builds the PageRef list, it never touches the live Document itself.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Dict, List, Optional, Set

import customtkinter as ctk
import PIL.Image
import PIL.ImageTk

from models import PageRef
from pdf.pdf_loader import PDFLoader
from viewer.pdf_renderer import PDFRenderer
from utils.ui_theme import (
    ACCENT, BG_APP, BG_ELEVATED, BG_PANEL, BG_SUBTLE, BG_SURFACE, BORDER,
    BORDER_SUBTLE, BORDER_STRONG, PAD, PAD_LG, RADIUS, RADIUS_SM,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, apply_base_theme, font,
)
from utils.widgets import create_button, create_icon_button, vertical_separator
from utils.ui_helpers import center_window
from utils import icons as icon_lib
from app import modern_dialogs as dialogs

CARD_W, CARD_H = 136, 196
PREVIEW_W, PREVIEW_H = 100, 128
BADGE_SIZE = 20


def parse_page_range(spec: str, page_count: int) -> List[int]:
    """Parse "all" or "1-3,5,7-9" into a sorted, deduped list of 1-indexed
    page numbers, clamped to [1, page_count]. Raises ValueError if the
    spec is empty/malformed or resolves to no valid pages."""
    spec = (spec or '').strip()
    if not spec or spec.lower() == 'all':
        return list(range(1, page_count + 1))

    pages = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            start, end = int(a.strip()), int(b.strip())
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))

    pages = {p for p in pages if 1 <= p <= page_count}
    if not pages:
        raise ValueError(f"No valid pages in range (source has {page_count} page(s))")
    return sorted(pages)


class PageCard(ctk.CTkFrame):
    """One page-preview card in the gallery grid: a white document
    preview with a small floating selection badge in its corner and a
    'Page N' caption below a thin divider -- the preview stays the visual
    focus, not a checkbox row. Click anywhere on the card to toggle.
    Shows a placeholder until its thumbnail has actually finished
    rendering (rendering happens progressively, one page at a time, in a
    background thread)."""

    def __init__(self, parent, page_num: int, selected: bool,
                 on_toggle: Callable[[int], None]):
        super().__init__(parent, width=CARD_W, height=CARD_H, corner_radius=RADIUS,
                          fg_color=BG_SURFACE, border_width=1, border_color=BORDER)
        self.grid_propagate(False)
        self.page_num = page_num
        self.on_toggle = on_toggle
        self._selected = selected
        self._hovered = False
        self._photo: Optional[PIL.ImageTk.PhotoImage] = None

        self.preview = ctk.CTkFrame(self, width=PREVIEW_W, height=PREVIEW_H, corner_radius=RADIUS_SM,
                                     fg_color="white", border_width=1, border_color=BORDER_STRONG)
        self.preview.pack(padx=12, pady=(12, 8))
        self.preview.pack_propagate(False)
        self._placeholder = ctk.CTkLabel(self.preview, text="...", font=font(16),
                                          text_color=TEXT_SECONDARY)
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._image_label: Optional[tk.Label] = None

        ctk.CTkFrame(self, height=1, fg_color=BORDER_SUBTLE, corner_radius=0
                     ).pack(fill="x", padx=12)
        self.caption = ctk.CTkLabel(self, text=f"Page {page_num}", font=font(11),
                                     text_color=TEXT_SECONDARY)
        self.caption.pack(pady=(6, 10))

        # Floating selection badge -- a small circle overlapping the
        # preview's top-left corner (Google-Photos-style), always present
        # so the card's clickable/selectable affordance is visible even
        # before anything is selected, filled solid only once selected.
        self.badge = ctk.CTkFrame(self, width=BADGE_SIZE, height=BADGE_SIZE,
                                   corner_radius=BADGE_SIZE // 2, fg_color=BG_SURFACE,
                                   border_width=1.5, border_color=BORDER_STRONG)
        self.badge.place(x=8, y=8)
        self.badge.pack_propagate(False)
        self._badge_check = ctk.CTkLabel(self.badge, image=icon_lib.get("check", size=11, color="white"), text="")

        self.set_selected(selected)

        for widget in (self, self.preview, self.caption):
            widget.bind("<Button-1>", self._on_card_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def set_thumbnail(self, pil_image: PIL.Image.Image):
        self._placeholder.destroy()
        self._photo = PIL.ImageTk.PhotoImage(pil_image)
        # A plain tkinter.Label (not CTkLabel) for the actual bitmap --
        # CTkLabel's own image handling wants a CTkImage for correct
        # scaling; a raw PhotoImage label matches how ThumbnailPanel's
        # own thumbnails work elsewhere in this app.
        self._image_label = tk.Label(self.preview, image=self._photo, bg='white', bd=0)
        self._image_label.pack(expand=True)
        for widget in (self._image_label,):
            widget.bind("<Button-1>", self._on_card_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_card_click(self, _event=None):
        self.set_selected(not self._selected)
        self.on_toggle(self.page_num)

    def _on_enter(self, _event=None):
        self._hovered = True
        self._apply_style()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._apply_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.configure(fg_color=BG_ELEVATED, border_color=ACCENT, border_width=2)
            self.badge.configure(fg_color=ACCENT, border_width=0)
            self._badge_check.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self._badge_check.place_forget()
            self.badge.configure(fg_color=BG_SURFACE, border_width=1.5, border_color=BORDER_STRONG)
            if self._hovered:
                self.configure(fg_color=BG_ELEVATED, border_color=BORDER_STRONG, border_width=1)
            else:
                self.configure(fg_color=BG_SURFACE, border_color=BORDER, border_width=1)


class InsertPagesDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_insert: Callable[[List[PageRef]], None],
                 title: str = "Insert Page(s) from PDF"):
        """
        Args:
            on_insert: Called with the chosen PageRef list (in page order)
                once the user clicks "Insert Selected". Not called on
                Cancel.
        """
        super().__init__(parent)
        apply_base_theme()
        self.title(title)
        self.configure(fg_color=BG_APP)

        self.on_insert = on_insert
        self._refs: List[PageRef] = []          # all pages of the chosen source, once loaded
        self._selected: Set[int] = set()         # 0-based indices into self._refs
        self.cards: Dict[int, PageCard] = {}     # 0-based index -> card
        self._load_generation = 0
        self._columns = 1

        self._build_ui()
        center_window(self, parent, 640, 680)

        self.transient(parent)
        self.grab_set()
        self.focus_set()

    # ---------------------------------------------------------------- layout

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)  # only the gallery row expands

        # ---- header: title + short description ---------------------------------
        header = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=PAD_LG, pady=(PAD_LG, PAD))
        ctk.CTkLabel(header_inner, text="Insert Pages from PDF", font=font(15, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(fill="x")
        ctk.CTkLabel(header_inner, text="Choose pages from another PDF to insert into this document.",
                     font=font(11), text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", pady=(2, 0))

        # ---- source row: entry + Browse fused into one control group -----------
        source_row = ctk.CTkFrame(header, fg_color="transparent")
        source_row.pack(fill="x", padx=PAD_LG, pady=(0, 4))
        source_row.columnconfigure(0, weight=1)

        # Entry and Browse sit flush against each other (same height, a
        # hairline gap) so they read as one unified "source" control
        # rather than two unrelated widgets.
        self.path_entry = ctk.CTkEntry(
            source_row, placeholder_text="Choose a PDF to pull pages from...",
            height=34, corner_radius=RADIUS_SM, border_color=BORDER, fg_color=BG_SUBTLE,
            font=font(12))
        self.path_entry.grid(row=0, column=0, sticky="ew")

        browse_btn = create_button(source_row, text="Browse...", icon="open", command=self._browse,
                                   variant="secondary", height=34)
        browse_btn.grid(row=0, column=1, padx=(6, 0))

        self.info_label = ctk.CTkLabel(header, text="Choose a PDF to see its pages.",
                                        font=font(11), text_color=TEXT_MUTED, anchor="w")
        self.info_label.pack(fill="x", padx=PAD_LG, pady=(6, PAD_LG))

        ctk.CTkFrame(self, height=1, fg_color=BORDER_SUBTLE, corner_radius=0).grid(row=0, column=0, sticky="sew")

        # ---- action bar: select all/none + quick select ------------------------
        action_bar = ctk.CTkFrame(self, fg_color=BG_APP, corner_radius=0)
        action_bar.grid(row=1, column=0, sticky="ew", padx=PAD_LG, pady=PAD)

        create_button(action_bar, text="Select All", command=self._select_all,
                      variant="ghost", height=28).pack(side="left")
        create_button(action_bar, text="Select None", command=self._select_none,
                      variant="ghost", height=28).pack(side="left", padx=(2, 0))

        vertical_separator(action_bar, height=18)

        ctk.CTkLabel(action_bar, text="Quick select", font=font(11),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 8))
        self.range_entry = ctk.CTkEntry(
            action_bar, placeholder_text='e.g. "1-3,5" or "all"', width=150, height=28,
            corner_radius=RADIUS_SM, border_color=BORDER, fg_color=BG_SURFACE, font=font(12))
        self.range_entry.pack(side="left")
        self.range_entry.bind("<Return>", lambda e: self._apply_quick_range())
        create_button(action_bar, text="Apply", command=self._apply_quick_range,
                      variant="ghost", height=28).pack(side="left", padx=(4, 0))

        # ---- scrollable grid gallery --------------------------------------------
        self.gallery = ctk.CTkScrollableFrame(self, fg_color=BG_APP, corner_radius=0)
        self.gallery.grid(row=2, column=0, sticky="nsew", padx=(PAD_LG - 6, PAD_LG - 6))
        self.gallery.bind("<Configure>", self._on_gallery_resize)

        self._empty_label = ctk.CTkLabel(
            self.gallery, text="No PDF chosen yet.", font=font(12), text_color=TEXT_SECONDARY)
        self._empty_label.pack(pady=60)

        # ---- bottom bar: summary + primary/secondary actions --------------------
        ctk.CTkFrame(self, height=1, fg_color=BORDER_SUBTLE, corner_radius=0).grid(row=3, column=0, sticky="new")
        bottom = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=0)
        bottom.grid(row=4, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self.selection_label = ctk.CTkLabel(bottom, text="", font=font(12), text_color=TEXT_SECONDARY)
        self.selection_label.grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=PAD_LG)

        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.grid(row=0, column=1, sticky="e", padx=PAD_LG, pady=PAD)
        create_button(btn_row, text="Cancel", command=self.destroy,
                      variant="secondary", width=100, height=36).pack(side="left", padx=(0, 8))
        self.insert_button = create_button(
            btn_row, text="Insert Pages", icon="insert_pages", command=self._start_insert,
            variant="primary", width=150, height=36)
        self.insert_button.configure(state="disabled")
        self.insert_button.pack(side="left")

    # ---------------------------------------------------------------- source loading

    def _browse(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")], parent=self)
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)
            self._load_source(path)

    def _load_source(self, path: str):
        if not path or not os.path.exists(path):
            dialogs.show_error(self, "Insert Pages", "Please choose a valid PDF file.")
            return

        self._load_generation += 1
        generation = self._load_generation
        self._refs = []
        self._selected = set()
        self.cards.clear()
        for w in self.gallery.winfo_children():
            w.destroy()

        self.insert_button.configure(state="disabled")
        self.info_label.configure(text=f"Reading {os.path.basename(path)} ...", text_color="#C9962B")
        self.selection_label.configure(text="")
        loading_label = ctk.CTkLabel(self.gallery, text="Loading pages...", font=font(12),
                                      text_color=TEXT_SECONDARY)
        loading_label.pack(pady=60)

        def worker():
            try:
                refs = PDFLoader.build_page_refs(path)
            except Exception as e:
                error_message = str(e)
                self.after(0, lambda: self._on_load_error(error_message))
                return
            self.after(0, lambda: self._on_refs_ready(refs, generation, loading_label))
            for idx, ref in enumerate(refs):
                if generation != self._load_generation:
                    return  # a newer _load_source() superseded this run
                # zoom=1.0 at this dpi -> ~204x264px for a Letter page,
                # comfortably bigger than the card's preview box so
                # .thumbnail() (shrink-only) actually downscales with
                # real anti-aliasing.
                img = PDFRenderer.render_page(ref.source_path, ref.source_index + 1,
                                               dpi=24, zoom=1.0)
                if img is None:
                    img = PDFRenderer.create_placeholder_image(width=PREVIEW_W, height=PREVIEW_H,
                                                                 text=f"P{idx + 1}")
                img.thumbnail((PREVIEW_W, PREVIEW_H), PIL.Image.Resampling.LANCZOS)
                self.after(0, lambda i=idx, im=img: self._on_thumbnail_ready(i, im, generation))

        threading.Thread(target=worker, daemon=True).start()

    def _on_load_error(self, message: str):
        self.info_label.configure(text="Failed to read PDF.", text_color="#DC2626")
        dialogs.show_error(self, "Insert Pages", message)

    def _on_refs_ready(self, refs: List[PageRef], generation: int, loading_label: ctk.CTkLabel):
        if generation != self._load_generation:
            return
        loading_label.destroy()
        self._refs = refs
        self._selected = set(range(len(refs)))  # all selected by default
        name = os.path.basename(self.path_entry.get())
        self.info_label.configure(text=f"{name} -- {len(refs)} page(s)", text_color=TEXT_SECONDARY)
        self.insert_button.configure(state="normal" if refs else "disabled")
        self._update_selection_label()

        for idx in range(len(refs)):
            card = PageCard(self.gallery, idx + 1, idx in self._selected,
                             on_toggle=self._on_card_toggled)
            self.cards[idx] = card
        self._relayout_grid()

    def _on_thumbnail_ready(self, idx: int, pil_image: PIL.Image.Image, generation: int):
        if generation != self._load_generation:
            return
        card = self.cards.get(idx)
        if card:
            card.set_thumbnail(pil_image)

    # ---------------------------------------------------------------- responsive grid

    def _on_gallery_resize(self, event):
        columns = max(1, event.width // CARD_W)
        if columns != self._columns:
            self._columns = columns
            self._relayout_grid()

    def _relayout_grid(self):
        if not self.cards:
            return
        for col in range(self._columns):
            self.gallery.columnconfigure(col, weight=1, uniform="page_card")
        for idx, card in self.cards.items():
            row, col = divmod(idx, self._columns)
            card.grid(row=row, column=col, padx=6, pady=6)

    # ---------------------------------------------------------------- selection

    def _on_card_toggled(self, page_num: int):
        idx = page_num - 1
        if idx in self._selected:
            self._selected.discard(idx)
        else:
            self._selected.add(idx)
        self._update_selection_label()

    def _update_selection_label(self):
        total = len(self._refs)
        count = len(self._selected)
        self.selection_label.configure(text=f"{count} of {total} page(s) selected" if total else "")
        self.insert_button.configure(state="normal" if count else "disabled")

    def _select_all(self):
        self._selected = set(range(len(self._refs)))
        for idx, card in self.cards.items():
            card.set_selected(True)
        self._update_selection_label()

    def _select_none(self):
        self._selected = set()
        for idx, card in self.cards.items():
            card.set_selected(False)
        self._update_selection_label()

    def _apply_quick_range(self):
        if not self._refs:
            return
        try:
            selected = parse_page_range(self.range_entry.get(), len(self._refs))
        except ValueError as e:
            dialogs.show_error(self, "Insert Pages", str(e))
            return
        self._selected = {p - 1 for p in selected}
        for idx, card in self.cards.items():
            card.set_selected(idx in self._selected)
        self._update_selection_label()

    # ---------------------------------------------------------------- actions

    def _start_insert(self):
        if not self._selected or not self._refs:
            return
        chosen = [self._refs[i] for i in sorted(self._selected)]
        self.on_insert(chosen)
        self.destroy()
