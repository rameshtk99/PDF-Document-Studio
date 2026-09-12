"""
Import PDFs dialog -- pick several PDFs and set the order they're
stitched together in.

InsertPagesDialog answers "which pages of this file?"; this answers the
coarser question first: "these N files, in this order, as one document".
Only page counts are read until the user confirms; the caller does the
real load via PDFLoader.load_pdfs().
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog
from typing import Callable, List, Optional

import customtkinter as ctk

from pdf.pdf_loader import PDFLoader
from utils.ui_theme import (
    ACCENT, BG_APP, BG_SUBTLE, BG_SURFACE, BORDER, BORDER_SUBTLE, RADIUS, RADIUS_SM,
    SPACE_4, SPACE_8, SPACE_12, SPACE_16, TEXT_PRIMARY, TEXT_SECONDARY,
    apply_base_theme, font,
)
from utils.widgets import create_button, create_icon_button
from utils.ui_helpers import center_window
from app import modern_dialogs as dialogs

PDF_FILETYPES = [("PDF files", "*.pdf")]


class _FileRow(ctk.CTkFrame):
    """One file in the ordered list: position, name, page count, controls.

    The row body is a drag handle (press and drag to reorder); the
    buttons on the right are not, so clicking Move Up doesn't start a
    drag. Up/Down stay as the keyboard/precision path -- dragging is the
    fast one, not the only one.
    """

    def __init__(self, parent, index: int, path: str, page_count: Optional[int],
                 on_move: Callable[[int, int], None], on_remove: Callable[[int], None],
                 is_first: bool, is_last: bool, drag_binder: Optional[Callable] = None):
        super().__init__(parent, fg_color=BG_SURFACE, corner_radius=RADIUS_SM, height=44)
        self.pack_propagate(False)
        self.index = index

        self.position_label = ctk.CTkLabel(self, text=str(index + 1), font=font(11, "bold"),
                                            text_color=TEXT_SECONDARY, width=18)
        self.position_label.pack(side=tk.LEFT, padx=(SPACE_8, 4))

        text = ctk.CTkFrame(self, fg_color="transparent")
        text.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, SPACE_8))
        name_label = ctk.CTkLabel(text, text=os.path.basename(path), font=font(12),
                                   text_color=TEXT_PRIMARY, anchor="w")
        name_label.pack(fill="x", pady=(5, 0))
        detail = "reading..." if page_count is None else (
            f"{page_count} page{'s' if page_count != 1 else ''}")
        detail_label = ctk.CTkLabel(text, text=detail, font=font(10), text_color=TEXT_SECONDARY,
                                     anchor="w")
        detail_label.pack(fill="x")

        create_icon_button(self, "delete", command=lambda: on_remove(index),
                            tooltip="Remove this file", size=13, width=24, height=24,
                            variant="danger_ghost").pack(side=tk.RIGHT, padx=(2, SPACE_8))
        down = create_icon_button(self, "move_down", command=lambda: on_move(index, index + 1),
                                   tooltip="Move down", size=13, width=24, height=24,
                                   variant="tertiary")
        down.pack(side=tk.RIGHT, padx=2)
        up = create_icon_button(self, "move_up", command=lambda: on_move(index, index - 1),
                                 tooltip="Move up", size=13, width=24, height=24,
                                 variant="tertiary")
        up.pack(side=tk.RIGHT, padx=2)
        if is_first:
            up.configure(state="disabled")
        if is_last:
            down.configure(state="disabled")

        if drag_binder:
            drag_binder(self, [self, text, self.position_label, name_label, detail_label])

    def set_dragging(self, dragging: bool):
        self.configure(fg_color=BG_SUBTLE if dragging else BG_SURFACE)


class ImportPdfsDialog(ctk.CTkToplevel):
    """Modal file-ordering step. Calls on_import(ordered_paths) on confirm."""

    def __init__(self, parent, on_import: Callable[[List[str]], None],
                 initial_paths: Optional[List[str]] = None,
                 title: str = "Import PDFs"):
        super().__init__(parent)
        apply_base_theme()
        self.title(title)
        self.configure(fg_color=BG_APP)

        self.on_import = on_import
        self.paths: List[str] = []
        self._page_counts: dict = {}

        # Drag-to-reorder state. The list is NOT re-rendered mid-drag --
        # that would destroy the very widget holding Tk's implicit
        # pointer grab and the gesture would die halfway. Instead a thin
        # insertion line marks where the row will land, and the actual
        # reorder happens once on release.
        self._rows: List[_FileRow] = []
        self._drag_index: Optional[int] = None
        self._drag_start_y: int = 0
        self._dragging = False
        self._drop_index: Optional[int] = None
        self._drop_line: Optional[tk.Frame] = None

        self._build_ui()
        if initial_paths:
            self._add_paths(initial_paths)

        center_window(self, parent, 560, 520)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    # ---------------------------------------------------------------- layout

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)   # only the file list grows

        header = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=SPACE_16, pady=SPACE_12)
        ctk.CTkLabel(inner, text="Import PDFs", font=font(15, "bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(fill="x")
        ctk.CTkLabel(inner, text="Combined top to bottom · drag a file to reorder.",
                     font=font(11), text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", pady=(2, SPACE_8))

        add_row = ctk.CTkFrame(inner, fg_color="transparent")
        add_row.pack(fill="x")
        create_button(add_row, text="Add files...", icon="open", command=self._browse,
                      variant="secondary", height=30).pack(side=tk.LEFT)
        self.summary_label = ctk.CTkLabel(add_row, text="No files yet", font=font(11),
                                           text_color=TEXT_SECONDARY)
        self.summary_label.pack(side=tk.RIGHT)

        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0
                     ).grid(row=0, column=0, sticky="sew")

        self.list_area = ctk.CTkScrollableFrame(self, fg_color=BG_APP, corner_radius=0)
        self.list_area.grid(row=1, column=0, sticky="nsew", padx=SPACE_12, pady=SPACE_12)

        self.empty_label = ctk.CTkLabel(
            self.list_area, text="No PDFs chosen yet.\nUse \"Add files...\" to pick one or more.",
            font=font(12), text_color=TEXT_SECONDARY, justify=tk.CENTER)
        self.empty_label.pack(pady=60)

        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0
                     ).grid(row=2, column=0, sticky="new")
        footer = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=0)
        footer.grid(row=3, column=0, sticky="ew")
        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(side=tk.RIGHT, padx=SPACE_16, pady=SPACE_12)
        create_button(btn_row, text="Cancel", command=self.destroy,
                      variant="secondary", height=34, width=90).pack(side=tk.LEFT, padx=(0, SPACE_8))
        self.import_button = create_button(
            btn_row, text="Import", icon="import", command=self._confirm,
            variant="primary", height=34, width=120)
        self.import_button.pack(side=tk.LEFT)
        self.import_button.configure(state="disabled")

    # ---------------------------------------------------------------- files

    def _browse(self):
        chosen = filedialog.askopenfilenames(
            title="Choose PDF files", filetypes=PDF_FILETYPES, parent=self)
        if chosen:
            self._add_paths(list(chosen))

    def _add_paths(self, paths: List[str]):
        added = 0
        for path in paths:
            if path in self.paths:
                continue   # same file twice in one import is a mis-click
            is_valid, error = PDFLoader.validate_pdf(path)
            if not is_valid:
                dialogs.show_error(self, "Cannot Add File",
                                    f"{os.path.basename(path)}\n\n{error}")
                continue
            self.paths.append(path)
            self._page_counts[path] = self._count_pages(path)
            added += 1
        if added:
            self._render()

    @staticmethod
    def _count_pages(path: str) -> Optional[int]:
        """Page count only -- cheap metadata read, no page content."""
        try:
            return len(PDFLoader.build_page_refs(path))
        except Exception:
            return None

    def _move(self, index: int, new_index: int):
        if not (0 <= new_index < len(self.paths)):
            return
        self.paths.insert(new_index, self.paths.pop(index))
        self._render()

    def _remove(self, index: int):
        if 0 <= index < len(self.paths):
            self._page_counts.pop(self.paths[index], None)
            del self.paths[index]
            self._render()

    # ---------------------------------------------------------------- drag to reorder

    def _bind_drag(self, row: "_FileRow", widgets):
        for w in widgets:
            w.configure(cursor="fleur")
            w.bind("<ButtonPress-1>", lambda e, r=row: self._drag_press(e, r), add="+")
            w.bind("<B1-Motion>", self._drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._drag_release, add="+")

    def _drag_press(self, event, row: "_FileRow"):
        self._drag_index = row.index
        self._drag_start_y = event.y_root
        self._dragging = False
        self._drop_index = None

    def _drag_motion(self, event):
        if self._drag_index is None:
            return
        if not self._dragging:
            if abs(event.y_root - self._drag_start_y) < 6:
                return          # still inside click tolerance
            self._dragging = True
            self._rows[self._drag_index].set_dragging(True)

        self._drop_index = self._insertion_index_at(event.y_root)
        self._show_drop_line(self._drop_index)

    def _drag_release(self, _event):
        drag_index, drop_index = self._drag_index, self._drop_index
        was_dragging = self._dragging
        self._drag_index = None
        self._dragging = False
        self._drop_index = None
        self._hide_drop_line()
        if 0 <= (drag_index or -1) < len(self._rows):
            self._rows[drag_index].set_dragging(False)

        if not was_dragging or drag_index is None or drop_index is None:
            return
        # drop_index counts slots BETWEEN rows; removing the dragged row
        # first shifts every later slot down by one.
        target = drop_index - 1 if drop_index > drag_index else drop_index
        if target != drag_index:
            self.paths.insert(target, self.paths.pop(drag_index))
            self._render()

    def _insertion_index_at(self, y_root: int) -> int:
        """Which gap (0..len) the pointer is closest to, by comparing
        against each row's vertical midpoint."""
        for i, row in enumerate(self._rows):
            try:
                midpoint = row.winfo_rooty() + row.winfo_height() / 2
            except tk.TclError:
                continue
            if y_root < midpoint:
                return i
        return len(self._rows)

    def _show_drop_line(self, slot: int):
        if self._drop_line is None:
            self._drop_line = tk.Frame(self.list_area, bg=ACCENT, height=2)
        if not self._rows:
            return
        if slot < len(self._rows):
            y = self._rows[slot].winfo_y() - 2
        else:
            last = self._rows[-1]
            y = last.winfo_y() + last.winfo_height()
        self._drop_line.place(x=0, y=max(0, y), relwidth=1.0)
        self._drop_line.lift()

    def _hide_drop_line(self):
        if self._drop_line is not None:
            self._drop_line.place_forget()

    def _render(self):
        self._hide_drop_line()
        self._drop_line = None
        self._rows = []
        for child in self.list_area.winfo_children():
            child.destroy()

        if not self.paths:
            self.empty_label = ctk.CTkLabel(
                self.list_area, text="No PDFs chosen yet.\nUse \"Add files...\" to pick one or more.",
                font=font(12), text_color=TEXT_SECONDARY, justify=tk.CENTER)
            self.empty_label.pack(pady=60)
            self.summary_label.configure(text="No files yet")
            self.import_button.configure(state="disabled")
            return

        last = len(self.paths) - 1
        for i, path in enumerate(self.paths):
            row = _FileRow(self.list_area, i, path, self._page_counts.get(path),
                           on_move=self._move, on_remove=self._remove,
                           is_first=(i == 0), is_last=(i == last),
                           drag_binder=self._bind_drag)
            row.pack(fill="x", pady=(0, SPACE_4))
            self._rows.append(row)

        total = sum(c for c in (self._page_counts.get(p) for p in self.paths) if c)
        self.summary_label.configure(
            text=f"{len(self.paths)} file{'s' if len(self.paths) != 1 else ''} · {total} pages")
        self.import_button.configure(state="normal")

    # ---------------------------------------------------------------- confirm

    def _confirm(self):
        if not self.paths:
            return
        ordered = list(self.paths)
        self.destroy()
        self.on_import(ordered)
