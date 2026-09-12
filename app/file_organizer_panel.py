"""
File Organizer: one card per source PDF, showing that file's first page.

The Pages panel is page-level; this is the file-level view of the same
document -- drag a card to move every page of that file at once, or
remove the file entirely. Thumbnails render in a background thread, same
generation-guard pattern the Pages panel uses so a superseded reload
can't write stale images.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
import PIL.Image
import PIL.ImageTk

from models import Document
from viewer.pdf_renderer import PDFRenderer
from utils import ui_theme
from utils.widgets import create_icon_button, empty_state

THUMB_W, THUMB_H = 46, 60


class _FileCard(tk.Frame):
    """One file: thumbnail, name, page count, remove button."""

    def __init__(self, parent, index: int, name: str, page_count: int,
                 on_remove: Callable[[int], None], on_click: Callable[[int], None],
                 drag_binder: Optional[Callable] = None):
        card_bg = ui_theme.resolve(ui_theme.BG_SURFACE)
        super().__init__(parent, bg=card_bg, highlightthickness=1,
                          highlightbackground=card_bg, highlightcolor=card_bg, bd=0)
        self.index = index
        self._card_bg = card_bg

        self.indicator = tk.Frame(self, width=3, bg=card_bg)
        self.indicator.pack(side=tk.LEFT, fill=tk.Y)

        body = tk.Frame(self, bg=card_bg)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=5)

        self.thumb = tk.Label(body, bg=card_bg, width=THUMB_W, height=THUMB_H,
                               bd=0, highlightthickness=0)
        self.thumb.pack(side=tk.LEFT)

        text = tk.Frame(body, bg=card_bg)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        self.name_label = tk.Label(
            text, text=name, bg=card_bg, fg=ui_theme.resolve(ui_theme.TEXT_PRIMARY),
            font=(ui_theme.FONT_FAMILY, 9), anchor="w", justify=tk.LEFT, wraplength=150)
        self.name_label.pack(fill=tk.X, anchor="w")
        self.count_label = tk.Label(
            text, text=f"{page_count} page{'s' if page_count != 1 else ''}",
            bg=card_bg, fg=ui_theme.resolve(ui_theme.TEXT_SECONDARY),
            font=(ui_theme.FONT_FAMILY, 8), anchor="w")
        self.count_label.pack(fill=tk.X, anchor="w")

        remove = create_icon_button(body, "delete", command=lambda: on_remove(index),
                                     tooltip="Remove this file and all its pages",
                                     size=12, width=22, height=22, variant="danger_ghost")
        remove.pack(side=tk.RIGHT)

        self._surfaces = [self, body, text, self.thumb, self.name_label, self.count_label]
        for w in self._surfaces:
            w.bind("<Button-1>", lambda _e: on_click(index), add="+")
            w.bind("<Enter>", lambda _e: self._hover(True), add="+")
            w.bind("<Leave>", lambda _e: self._hover(False), add="+")
        if drag_binder:
            drag_binder(self, self._surfaces)

        self._selected = False
        self._hovered = False

    def _hover(self, hovered: bool):
        self._hovered = hovered
        self._restyle()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._restyle()

    def _restyle(self):
        if self._selected:
            bg = ui_theme.resolve(ui_theme.ACCENT_SOFT)
            border = ui_theme.ACCENT
            stripe = ui_theme.ACCENT
        elif self._hovered:
            bg = ui_theme.resolve(ui_theme.BG_HOVER)
            border = ui_theme.resolve(ui_theme.BORDER)
            stripe = ui_theme.resolve(ui_theme.BG_HOVER)
        else:
            bg = self._card_bg
            border = self._card_bg
            stripe = self._card_bg
        self.configure(highlightbackground=border, highlightcolor=border)
        self.indicator.configure(bg=stripe)
        for w in self._surfaces:
            if w is not self:
                w.configure(bg=bg)
        self.configure(bg=bg)

    def set_thumbnail(self, photo):
        self.thumb.configure(image=photo, width=photo.width(), height=photo.height())
        self.thumb.image = photo


class FileOrganizerPanel(ctk.CTkFrame):
    """File-level view: reorder or remove whole source PDFs."""

    def __init__(self, parent, on_reorder: Optional[Callable[[int, int], None]] = None,
                 on_remove: Optional[Callable[[int], None]] = None,
                 on_file_selected: Optional[Callable[[int], None]] = None,
                 on_add_files: Optional[Callable] = None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("height", 1)
        super().__init__(parent, **kwargs)

        self.on_reorder = on_reorder
        self.on_remove = on_remove
        self.on_file_selected = on_file_selected
        self.on_add_files = on_add_files

        self.document: Optional[Document] = None
        self._groups: List[dict] = []
        self._cards: Dict[int, _FileCard] = {}
        self._photos: Dict[int, PIL.ImageTk.PhotoImage] = {}
        self._load_generation = 0
        self._selected_index: Optional[int] = None

        # Drag state -- no re-render mid-drag (it would destroy the widget
        # holding Tk's pointer grab); an insertion line marks the drop and
        # the move happens on release.
        self._drag_index: Optional[int] = None
        self._drag_start_y = 0
        self._dragging = False
        self._drop_index: Optional[int] = None
        self._drop_line: Optional[tk.Frame] = None

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill=tk.BOTH, expand=True)

        self._empty = empty_state(
            self.scroll, icon="document", title="No files yet",
            subtitle="Open or import PDFs to see them listed here.")
        self._empty.pack(pady=20)

    # ---------------------------------------------------------------- data

    def load_document(self, document: Optional[Document]):
        self.document = document
        self._load_generation += 1
        self.refresh()

    def refresh(self):
        """Rebuild from the document's current file grouping."""
        self._load_generation += 1
        generation = self._load_generation
        self._groups = self.document.file_groups() if self.document else []
        self._render()
        if self._groups:
            threading.Thread(target=self._render_thumbnails, args=(generation,),
                             daemon=True).start()

    def _render(self):
        self._hide_drop_line()
        self._drop_line = None
        self._cards.clear()
        for child in self.scroll.winfo_children():
            child.destroy()

        if not self._groups:
            self._empty = empty_state(
                self.scroll, icon="document", title="No files yet",
                subtitle="Open or import PDFs to see them listed here.")
            self._empty.pack(pady=20)
            return

        for index, group in enumerate(self._groups):
            name = os.path.basename(group['source_path']) or group['source_path']
            card = _FileCard(self.scroll, index, name, len(group['page_indices']),
                             on_remove=self._request_remove,
                             on_click=self._select,
                             drag_binder=self._bind_drag)
            card.pack(fill=tk.X, padx=6, pady=3)
            self._cards[index] = card
            if index == self._selected_index:
                card.set_selected(True)

    def _render_thumbnails(self, generation: int):
        for index, group in enumerate(list(self._groups)):
            if generation != self._load_generation:
                return
            page_indices = group['page_indices']
            if not page_indices or not self.document:
                continue
            ref = self.document.pages[page_indices[0]]
            img = PDFRenderer.render_page(ref.source_path, ref.source_index + 1,
                                           dpi=24, zoom=1.0)
            if img is None:
                img = PDFRenderer.create_placeholder_image(
                    width=THUMB_W, height=THUMB_H, text="PDF")
            img.thumbnail((THUMB_W, THUMB_H), PIL.Image.Resampling.LANCZOS)
            self.after(0, self._apply_thumbnail, index, img, generation)

    def _apply_thumbnail(self, index: int, img, generation: int):
        if generation != self._load_generation:
            return
        card = self._cards.get(index)
        if not card:
            return
        photo = PIL.ImageTk.PhotoImage(img)
        self._photos[index] = photo     # keep a reference or Tk drops it
        card.set_thumbnail(photo)

    # ---------------------------------------------------------------- actions

    def _select(self, index: int):
        self._selected_index = index
        for i, card in self._cards.items():
            card.set_selected(i == index)
        if self.on_file_selected:
            self.on_file_selected(index)

    def _request_remove(self, index: int):
        if self.on_remove:
            self.on_remove(index)

    # ---------------------------------------------------------------- drag

    def _bind_drag(self, card: _FileCard, widgets):
        for w in widgets:
            w.configure(cursor="fleur")
            w.bind("<ButtonPress-1>", lambda e, c=card: self._drag_press(e, c), add="+")
            w.bind("<B1-Motion>", self._drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._drag_release, add="+")

    def _drag_press(self, event, card: _FileCard):
        self._drag_index = card.index
        self._drag_start_y = event.y_root
        self._dragging = False
        self._drop_index = None

    def _drag_motion(self, event):
        if self._drag_index is None:
            return
        if not self._dragging:
            if abs(event.y_root - self._drag_start_y) < 6:
                return
            self._dragging = True
        self._drop_index = self._insertion_index_at(event.y_root)
        self._show_drop_line(self._drop_index)

    def _drag_release(self, _event):
        drag_index, drop_index = self._drag_index, self._drop_index
        was_dragging = self._dragging
        self._drag_index = None
        self._dragging = False
        self._drop_index = None
        self._hide_drop_line()

        if not was_dragging or drag_index is None or drop_index is None:
            return
        target = drop_index - 1 if drop_index > drag_index else drop_index
        if target != drag_index and self.on_reorder:
            self.on_reorder(drag_index, target)

    def _insertion_index_at(self, y_root: int) -> int:
        for index in sorted(self._cards):
            card = self._cards[index]
            try:
                midpoint = card.winfo_rooty() + card.winfo_height() / 2
            except tk.TclError:
                continue
            if y_root < midpoint:
                return index
        return len(self._cards)

    def _show_drop_line(self, slot: int):
        if self._drop_line is None:
            self._drop_line = tk.Frame(self.scroll, bg=ui_theme.ACCENT, height=2)
        if not self._cards:
            return
        if slot < len(self._cards):
            y = self._cards[slot].winfo_y() - 2
        else:
            last = self._cards[len(self._cards) - 1]
            y = last.winfo_y() + last.winfo_height()
        self._drop_line.place(x=0, y=max(0, y), relwidth=1.0)
        self._drop_line.lift()

    def _hide_drop_line(self):
        if self._drop_line is not None:
            self._drop_line.place_forget()

    # ---------------------------------------------------------------- info

    def file_count(self) -> int:
        return len(self._groups)
