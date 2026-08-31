"""
Insert Page(s) from PDF dialog -- lets the user pick a source PDF, see it
as a grid of real page thumbnails with a running "N of M selected" count,
click pages on/off (all selected by default), then hands the resulting
PageRefs back to the caller. The caller (editor_window.py) owns the
actual insertion position and the undo-managed Document.insert_pages
call (via InsertPagesCommand) -- this dialog only reads the chosen
source file's metadata/thumbnails and builds the PageRef list, it never
touches the live Document itself.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import PIL.Image
import PIL.ImageTk
import PIL.ImageOps
import PIL.ImageEnhance

from models import PageRef
from pdf.pdf_loader import PDFLoader
from viewer.pdf_renderer import PDFRenderer
from utils.ui_helpers import center_window

_GRID_COLUMNS = 4
_THUMB_MAX = (90, 120)

# Selection styling -- three redundant cues (checkbox glyph, border
# color/thickness, dimmed-vs-bright image) so selected/unselected is
# obvious at a glance, not a subtle color difference to hunt for.
_SELECTED_BORDER = '#1565C0'
_UNSELECTED_BORDER = '#bbbbbb'
_CHECK_ON = "☑"   # ☑
_CHECK_OFF = "☐"  # ☐


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


class InsertPagesDialog(tk.Toplevel):
    def __init__(self, parent, on_insert: Callable[[List[PageRef]], None],
                 title: str = "Insert Page(s) from PDF"):
        """
        Args:
            on_insert: Called with the chosen PageRef list (in page order)
                once the user clicks "Insert Selected". Not called on
                Cancel.
        """
        super().__init__(parent)
        self.title(title)
        # Rough placeholder geometry -- immediately replaced below by
        # _fit_to_content() once the real (empty-state) content exists to
        # measure, so this number barely matters. Without it, the window
        # briefly flashes at whatever size Tk defaults to before layout.
        center_window(self, parent, 480, 300)
        self.minsize(420, 260)
        self.transient(parent)

        self.on_insert = on_insert
        self._refs: List[PageRef] = []          # all pages of the chosen source, once loaded
        self._selected: set = set()              # 0-based indices into self._refs
        self._thumb_frames: Dict[int, tk.Frame] = {}
        self._thumb_labels: Dict[int, tk.Label] = {}       # the image label (swapped bright/dimmed)
        self._thumb_checks: Dict[int, tk.Label] = {}       # checkbox glyph label
        self._thumb_page_labels: Dict[int, tk.Label] = {}  # "Page N" caption label
        self._thumb_images: Dict[int, PIL.ImageTk.PhotoImage] = {}         # bright (selected) version
        self._thumb_images_dim: Dict[int, PIL.ImageTk.PhotoImage] = {}     # dimmed/grayscale (unselected) version
        self._load_generation = 0
        self._loading = False
        self._build_ui()

        # Size to the actual "no PDF chosen yet" placeholder content, the
        # same way _fit_to_content() sizes to a loaded page grid later --
        # not the old fixed 600x680, which stayed oversized-and-mostly-
        # empty until a file was picked.
        self._fit_to_content(self._load_generation)

    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        # grid (not pack) for the top-level stack, with weight only on the
        # thumbnail-grid row: pack()ing a side=TOP/expand=True widget
        # *before* a widget that must stay pinned (here, the bottom
        # Insert/Cancel bar) starves that later widget of space whenever
        # the window is too short to fit everything at once -- exactly
        # what was happening (the button bar getting squeezed off-screen
        # with a long page list). grid's explicit row weights make the
        # thumbnail area the only one that shrinks/grows/scrolls; the top
        # controls and bottom button bar always get their full requested
        # size regardless of window height.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)  # row 1 = the scrollable thumbnail grid

        top = tk.Frame(self)
        top.grid(row=0, column=0, sticky='ew')
        top.columnconfigure(1, weight=1)
        self._top_frame = top  # measured later to size the window to fit actual content

        tk.Label(top, text="Source PDF:").grid(row=0, column=0, sticky='w', **pad)
        self.path_var = tk.StringVar(value="")
        tk.Entry(top, textvariable=self.path_var).grid(row=0, column=1, sticky='ew', **pad)
        tk.Button(top, text="Browse...", command=self._browse).grid(row=0, column=2, **pad)

        self.info_label = tk.Label(top, text="Choose a PDF to see its pages.",
                                    fg='gray30', font=('Arial', 9), anchor='w')
        self.info_label.grid(row=1, column=0, columnspan=3, sticky='w', padx=10)

        controls = tk.Frame(top)
        controls.grid(row=2, column=0, columnspan=3, sticky='ew', padx=6, pady=(8, 2))
        tk.Button(controls, text="Select All", command=self._select_all).pack(side=tk.LEFT, padx=4)
        tk.Button(controls, text="Select None", command=self._select_none).pack(side=tk.LEFT, padx=4)
        tk.Label(controls, text="Quick select:").pack(side=tk.LEFT, padx=(16, 2))
        self.range_var = tk.StringVar(value="")
        range_entry = tk.Entry(controls, textvariable=self.range_var, width=12)
        range_entry.pack(side=tk.LEFT)
        range_entry.bind('<Return>', lambda e: self._apply_quick_range())
        tk.Button(controls, text="Apply", command=self._apply_quick_range).pack(side=tk.LEFT, padx=4)
        tk.Label(top, text='Quick select e.g. "1-3,5" or "all" -- or just click pages below',
                 fg='gray40', font=('Arial', 8)).grid(row=3, column=0, columnspan=3, sticky='w', padx=10)

        # -- scrollable thumbnail grid (the one row/widget that expands) --
        grid_container = tk.Frame(self, relief=tk.SUNKEN, bd=1)
        grid_container.grid(row=1, column=0, sticky='nsew', padx=10, pady=(8, 4))

        scrollbar = tk.Scrollbar(grid_container, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.grid_canvas = tk.Canvas(grid_container, bg='#eeeeee', highlightthickness=0,
                                      yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.grid_canvas.yview)
        self.grid_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.grid_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.grid_canvas.bind("<Button-4>", self._on_mousewheel)
        self.grid_canvas.bind("<Button-5>", self._on_mousewheel)

        self.grid_frame = tk.Frame(self.grid_canvas, bg='#eeeeee')
        # anchor='n' (top-center) at x=canvas_width/2, not 'nw' at x=0 --
        # the dialog's overall width is often wider than the thumbnail
        # grid's own natural width (the header controls need more room
        # than a 4-column grid does), and stretching the frame to fill
        # that width left an obviously lopsided empty area on the right.
        # Centering the grid horizontally instead turns any extra width
        # into a symmetric margin on both sides, which reads as normal
        # breathing room rather than a "why is this empty?" mistake.
        self.grid_window = self.grid_canvas.create_window((0, 0), window=self.grid_frame, anchor=tk.N)
        self.grid_frame.bind("<Configure>", lambda e: self.grid_canvas.config(
            scrollregion=self.grid_canvas.bbox("all")))
        self.grid_canvas.bind("<Configure>", lambda e: self.grid_canvas.coords(
            self.grid_window, max(e.width, self.grid_frame.winfo_reqwidth()) // 2, 0))

        self._placeholder_label = tk.Label(self.grid_frame, text="No PDF chosen yet.",
                                            bg='#eeeeee', fg='gray40')
        self._placeholder_label.pack(pady=30)

        # -- bottom bar (fixed row, never shrinks/scrolls away) --
        bottom = tk.Frame(self)
        bottom.grid(row=2, column=0, sticky='ew', padx=10, pady=(0, 10))
        self._bottom_frame = bottom  # measured later to size the window to fit actual content
        self.selection_label = tk.Label(bottom, text="", fg='gray20', anchor='w')
        self.selection_label.pack(side=tk.LEFT)

        btns = tk.Frame(bottom)
        btns.pack(side=tk.RIGHT)
        self.insert_button = tk.Button(btns, text="Insert Selected", command=self._start_insert,
                                        bg='#2e7d32', fg='white', width=16, state=tk.DISABLED)
        self.insert_button.pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _on_mousewheel(self, event):
        delta = 3 if (event.num == 5 or event.delta < 0) else -3
        self.grid_canvas.yview_scroll(delta, "units")

    def _browse(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.path_var.set(path)
            self._load_source(path)

    def _load_source(self, path: str):
        if not path or not os.path.exists(path):
            messagebox.showerror("Insert Pages", "Please choose a valid PDF file.")
            return

        self._load_generation += 1
        generation = self._load_generation
        self._loading = True
        self._refs = []
        self._selected = set()
        self._thumb_frames.clear()
        self._thumb_labels.clear()
        self._thumb_images.clear()
        for w in self.grid_frame.winfo_children():
            w.destroy()

        self.insert_button.config(state=tk.DISABLED)
        self.info_label.config(text=f"Reading {os.path.basename(path)} ...", fg='#8a5a00')
        self.selection_label.config(text="")
        loading_label = tk.Label(self.grid_frame, text="Loading pages...", bg='#eeeeee', fg='gray40')
        loading_label.pack(pady=30)

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
                img = PDFRenderer.render_page(ref.source_path, ref.source_index + 1,
                                               dpi=24, zoom=0.2)
                if img is None:
                    img = PDFRenderer.create_placeholder_image(width=90, height=120,
                                                                 text=f"P{idx + 1}")
                img.thumbnail(_THUMB_MAX, PIL.Image.Resampling.LANCZOS)
                self.after(0, lambda i=idx, im=img: self._add_thumbnail(i, im, generation))
            self.after(0, lambda: self._fit_to_content(generation))

        threading.Thread(target=worker, daemon=True).start()

    def _on_load_error(self, message: str):
        self._loading = False
        self.info_label.config(text="Failed to read PDF.", fg='#a02020')
        messagebox.showerror("Insert Pages", message)

    def _on_refs_ready(self, refs: List[PageRef], generation: int, loading_label: tk.Label):
        if generation != self._load_generation:
            return
        loading_label.destroy()
        self._refs = refs
        self._selected = set(range(len(refs)))  # all selected by default
        name = os.path.basename(self.path_var.get())
        self.info_label.config(text=f"{name} -- {len(refs)} page(s)", fg='gray30')
        self.insert_button.config(state=tk.NORMAL if refs else tk.DISABLED)
        self._update_selection_label()

    def _add_thumbnail(self, idx: int, pil_image: PIL.Image.Image, generation: int):
        if generation != self._load_generation:
            return
        photo = PIL.ImageTk.PhotoImage(pil_image)
        # Dimmed/grayscale twin, shown when this page is NOT selected, so
        # selection state is visible in the image itself, not just a thin
        # border -- unmistakable even at a glance across a full grid.
        dimmed_src = PIL.ImageOps.grayscale(pil_image).convert('RGB')
        dimmed_src = PIL.ImageEnhance.Brightness(dimmed_src).enhance(1.5)  # washed-out, not just dark
        dimmed_photo = PIL.ImageTk.PhotoImage(dimmed_src)

        row, col = divmod(idx, _GRID_COLUMNS)
        frame = tk.Frame(self.grid_frame, bg=_SELECTED_BORDER, bd=4, relief=tk.SOLID)
        frame.grid(row=row, column=col, padx=6, pady=6)

        header = tk.Frame(frame, bg=_SELECTED_BORDER)
        header.pack(fill=tk.X)
        check_lbl = tk.Label(header, text=_CHECK_ON, font=('Segoe UI Symbol', 11),
                              bg=_SELECTED_BORDER, fg='white')
        check_lbl.pack(side=tk.LEFT, padx=(4, 2), pady=1)
        page_lbl = tk.Label(header, text=f"Page {idx + 1}", bg=_SELECTED_BORDER, fg='white',
                             font=('Arial', 8, 'bold'))
        page_lbl.pack(side=tk.LEFT, pady=1)

        img_lbl = tk.Label(frame, image=photo, bg='white')
        img_lbl.pack(padx=2, pady=(0, 2))

        for widget in (frame, header, check_lbl, page_lbl, img_lbl):
            widget.bind("<Button-1>", lambda e, i=idx: self._toggle_page(i))

        self._thumb_frames[idx] = frame
        self._thumb_labels[idx] = img_lbl
        self._thumb_checks[idx] = check_lbl
        self._thumb_page_labels[idx] = page_lbl
        self._thumb_images[idx] = photo
        self._thumb_images_dim[idx] = dimmed_photo
        self._refresh_thumbnail_style(idx)

    def _toggle_page(self, idx: int):
        if idx in self._selected:
            self._selected.discard(idx)
        else:
            self._selected.add(idx)
        self._refresh_thumbnail_style(idx)
        self._update_selection_label()

    def _refresh_thumbnail_style(self, idx: int):
        frame = self._thumb_frames.get(idx)
        if not frame:
            return
        selected = idx in self._selected
        border = _SELECTED_BORDER if selected else _UNSELECTED_BORDER

        frame.config(bg=border, bd=4 if selected else 1)
        for child in frame.winfo_children():
            if isinstance(child, tk.Frame):
                child.config(bg=border)  # the header strip

        self._thumb_checks[idx].config(
            text=_CHECK_ON if selected else _CHECK_OFF,
            bg=border, fg='white' if selected else '#666666')
        self._thumb_page_labels[idx].config(bg=border, fg='white' if selected else '#666666')
        self._thumb_labels[idx].config(
            image=self._thumb_images[idx] if selected else self._thumb_images_dim[idx])

    def _update_selection_label(self):
        total = len(self._refs)
        count = len(self._selected)
        self.selection_label.config(text=f"{count} of {total} page(s) selected" if total else "")
        self.insert_button.config(state=tk.NORMAL if count else tk.DISABLED)

    def _select_all(self):
        self._selected = set(range(len(self._refs)))
        for idx in self._thumb_frames:
            self._refresh_thumbnail_style(idx)
        self._update_selection_label()

    def _select_none(self):
        self._selected = set()
        for idx in self._thumb_frames:
            self._refresh_thumbnail_style(idx)
        self._update_selection_label()

    def _apply_quick_range(self):
        if not self._refs:
            return
        try:
            selected = parse_page_range(self.range_var.get(), len(self._refs))
        except ValueError as e:
            messagebox.showerror("Insert Pages", str(e))
            return
        self._selected = {p - 1 for p in selected}
        for idx in self._thumb_frames:
            self._refresh_thumbnail_style(idx)
        self._update_selection_label()

    def _start_insert(self):
        if not self._selected or not self._refs:
            return
        chosen = [self._refs[i] for i in sorted(self._selected)]
        self.on_insert(chosen)
        self.destroy()

    def _fit_to_content(self, generation: int):
        """Once every thumbnail has finished loading, resize the window to
        actually match the page grid, both height AND width -- a 6-page
        source left most of the fixed 680px-tall window as dead empty
        space below the grid; keeping width fixed at an arbitrary 600px
        left an equally dead empty strip to the right of a 4-column grid
        that only needs ~450px (the canvas was stretching to fill that
        unused width, visible as blank gray space next to the thumbnails).
        A 60-page source should offer a comfortably-sized scrollable
        viewport rather than trying to show every row at once.
        """
        if generation != self._load_generation:
            return  # a newer load superseded this one

        self.update_idletasks()
        top_h = self._top_frame.winfo_reqheight()
        bottom_h = self._bottom_frame.winfo_reqheight()
        content_h = self.grid_frame.winfo_reqheight()
        content_w = self.grid_frame.winfo_reqwidth()

        min_grid_h, max_grid_h = 150, 420
        grid_h = max(min_grid_h, min(content_h, max_grid_h))

        # Width: match the grid's actual natural content width (however
        # many columns' worth of thumbnails that really is) plus a fixed
        # allowance for the vertical scrollbar and the grid's own border/
        # the dialog's outer padding -- not an arbitrary fixed value.
        scrollbar_and_border_overhead = 40
        min_w = 420
        width = max(min_w, content_w + scrollbar_and_border_overhead,
                    self._top_frame.winfo_reqwidth())

        height = top_h + grid_h + bottom_h + 40  # padding/border fudge between sections

        center_window(self, self.master, width, height)
