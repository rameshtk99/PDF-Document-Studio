"""
PDF Viewer widget for Tkinter

Provides an embedded PDF viewer with:
- Page display
- Zoom controls (fit page, fit width, 100%, zoom in/out)
- Page navigation (next, previous, go to page)
- Smooth scrolling
- Page indicator
- Thumbnail panel for quick page navigation
"""

import bisect
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable, List, Dict, Set, Tuple
import threading
import PIL.Image
import PIL.ImageTk
from viewer.pdf_renderer import PDFRenderer
from models import Document


class ThumbnailPanel(tk.Frame):
    """Left-side thumbnail navigation panel for PDF viewer
    
    Features:
    - Displays mini previews of all PDF pages
    - Click to navigate to page
    - Visual indicator of current page
    - Multi-select support (Ctrl+Click)
    - Page range selection (Shift+Click)
    - Scrollable frame for PDFs with many pages
    """
    
    def __init__(self, parent, document: Optional[Document] = None,
                 on_page_selected: Optional[Callable] = None,
                 on_scroll_page_changed: Optional[Callable[[int], None]] = None, **kwargs):
        """
        Initialize thumbnail panel

        Args:
            parent: Parent widget
            document: Document object
            on_page_selected: Callback function(page_num) when page clicked
            on_scroll_page_changed: Callback function(page_num) fired when
                scrolling (wheel or scrollbar drag) brings a different page's
                thumbnail to the top -- lets the main view follow along, the
                same way the main view scrolls this panel's list.
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)

        self.document = document
        self.on_page_selected = on_page_selected
        self.on_scroll_page_changed = on_scroll_page_changed
        self.current_page = 1
        self.selected_pages: Set[int] = set()
        self.thumbnail_buttons: Dict[int, tk.Button] = {}
        self.thumbnail_frames: Dict[int, tk.Frame] = {}
        self.thumbnail_images: Dict[int, PIL.ImageTk.PhotoImage] = {}
        self.last_selected_page = 1
        
        self.config(bg='lightgray', width=150)
        self.pack_propagate(False)
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the thumbnail panel UI"""
        # Header
        header = tk.Frame(self, bg='darkgray')
        header.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        
        tk.Label(header, text="Pages", bg='darkgray', fg='white',
                font=('Arial', 9, 'bold')).pack(side=tk.LEFT)

        # Scrollbar
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Canvas for scrolling
        self.canvas = tk.Canvas(self, bg='lightgray', highlightthickness=0,
                               yscrollcommand=scrollbar.set, width=150)
        # command=self._on_scrollbar_scroll rather than plain
        # self.canvas.yview -- dragging the thumb (not just wheel
        # scrolling) must also notify the main view to follow along.
        scrollbar.config(command=self._on_scrollbar_scroll)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Frame inside canvas to hold thumbnails
        self.thumbnails_frame = tk.Frame(self.canvas, bg='lightgray')
        self.canvas.create_window((0, 0), window=self.thumbnails_frame, anchor=tk.NW)
        
        # Update scroll region
        self.thumbnails_frame.bind("<Configure>", self._on_frame_configure)
        
        # Bind mouse wheel
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
    
    def load_document(self, document: Document):
        """Load document and create thumbnails
        
        Args:
            document: Document object
        """
        self.document = document
        self.selected_pages.clear()
        self.thumbnail_buttons.clear()
        self.thumbnail_frames.clear()
        self.thumbnail_images.clear()
        
        # Clear existing thumbnails
        for widget in self.thumbnails_frame.winfo_children():
            widget.destroy()
        
        if not document:
            return
        
        # Create thumbnails for each page (in background thread)
        threading.Thread(target=self._render_thumbnails, daemon=True).start()
    
    def _render_thumbnails(self):
        """Render thumbnails for all pages (threaded)"""
        if not self.document:
            return
        
        for page_num in range(1, self.document.page_count + 1):
            # Render thumbnail
            img = PDFRenderer.render_page(
                self.document.pdf_path,
                page_num,
                dpi=24,  # Low DPI for thumbnails
                zoom=0.15  # Small size
            )
            
            if img is None:
                # Use placeholder
                img = PDFRenderer.create_placeholder_image(
                    width=100, height=140,
                    text=f"P{page_num}"
                )
            
            # Resize to fit thumbnail panel (max 120x160)
            img.thumbnail((120, 160), PIL.Image.Resampling.LANCZOS)

            # Hand the plain PIL image to the main thread -- PhotoImage
            # itself must be constructed there. Tkinter/Tcl is not
            # thread-safe, so building a tkinter.PhotoImage() from this
            # background thread is unreliable (it can raise "main thread
            # is not in main loop" depending on Tcl's threaded build).
            self.after(0, self._create_thumbnail_button, page_num, img)

    def _create_thumbnail_button(self, page_num: int, pil_image: PIL.Image.Image):
        """Create a thumbnail button (must be called from main thread)

        Args:
            page_num: Page number (1-indexed)
            pil_image: Rendered/resized PIL Image for the thumbnail
        """
        photo = PIL.ImageTk.PhotoImage(pil_image)

        frame = tk.Frame(self.thumbnails_frame, bg='lightgray',
                        relief=tk.SUNKEN, borderwidth=1)
        frame.pack(fill=tk.X, padx=2, pady=2)
        
        btn = tk.Button(
            frame,
            image=photo,
            bg='white',
            relief=tk.RAISED,
            borderwidth=2,
            command=lambda: self._on_thumbnail_click(page_num, None),
            height=140,
            width=120
        )
        btn.pack(padx=2, pady=2)
        
        # Bind Ctrl+Click and Shift+Click
        btn.bind("<Control-Button-1>", lambda e: self._on_thumbnail_click(page_num, 'ctrl'))
        btn.bind("<Shift-Button-1>", lambda e: self._on_thumbnail_click(page_num, 'shift'))
        
        # Label
        label = tk.Label(frame, text=f"Page {page_num}", bg='lightgray', 
                        font=('Arial', 8))
        label.pack(fill=tk.X)
        
        # Store reference
        self.thumbnail_buttons[page_num] = btn
        self.thumbnail_frames[page_num] = frame
        self.thumbnail_images[page_num] = photo  # Keep reference to prevent garbage collection
    
    def _on_thumbnail_click(self, page_num: int, modifier: Optional[str]):
        """Handle thumbnail click
        
        Args:
            page_num: Clicked page number
            modifier: 'ctrl' for multi-select, 'shift' for range, None for single
        """
        if modifier == 'ctrl':
            # Multi-select: toggle page
            if page_num in self.selected_pages:
                self.selected_pages.discard(page_num)
            else:
                self.selected_pages.add(page_num)
        elif modifier == 'shift':
            # Range select
            if self.last_selected_page < page_num:
                range_pages = range(self.last_selected_page, page_num + 1)
            else:
                range_pages = range(page_num, self.last_selected_page + 1)
            self.selected_pages.update(range_pages)
        else:
            # Single select
            self.selected_pages.clear()
            self.selected_pages.add(page_num)
        
        self.last_selected_page = page_num
        self.set_current_page(page_num)
        
        if self.on_page_selected:
            self.on_page_selected(page_num)
        
        self._update_thumbnail_highlights()
    
    def _update_thumbnail_highlights(self):
        """Update visual highlighting of selected/current pages"""
        for page_num, btn in self.thumbnail_buttons.items():
            if page_num == self.current_page:
                btn.config(relief=tk.SUNKEN, bg='lightblue')
            elif page_num in self.selected_pages:
                btn.config(relief=tk.RAISED, bg='lightyellow')
            else:
                btn.config(relief=tk.RAISED, bg='white')
    
    def set_current_page(self, page_num: int):
        """Set the current page
        
        Args:
            page_num: Page number (1-indexed)
        """
        if 1 <= page_num <= (self.document.page_count if self.document else 0):
            self.current_page = page_num
            self._update_thumbnail_highlights()
            self._scroll_to_page(page_num)
    
    def _scroll_to_page(self, page_num: int):
        """Scroll thumbnail panel to show page

        tk.Canvas has no .see() (that's a Text/Listbox method) -- compute
        the target thumbnail's position within the scrollable frame
        ourselves and move the view just enough to bring it fully into
        view, the same way .see() would for a Listbox.

        Args:
            page_num: Page number to scroll to
        """
        frame = self.thumbnail_frames.get(page_num)
        if not frame:
            return

        self.canvas.update_idletasks()
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        total_height = bbox[3] - bbox[1]
        if total_height <= 0:
            return

        item_top = frame.winfo_y()
        item_bottom = item_top + frame.winfo_height()
        item_top_frac = item_top / total_height
        item_bottom_frac = item_bottom / total_height

        view_top, view_bottom = self.canvas.yview()
        if item_top_frac < view_top:
            self.canvas.yview_moveto(max(0.0, item_top_frac))
        elif item_bottom_frac > view_bottom:
            visible_frac = view_bottom - view_top
            self.canvas.yview_moveto(max(0.0, item_bottom_frac - visible_frac))
    
    def _on_frame_configure(self, event=None):
        """Update scroll region when frame changes"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        if event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(3, "units")
        else:
            self.canvas.yview_scroll(-3, "units")
        self._notify_scroll_page_changed()

    def _on_scrollbar_scroll(self, *args):
        """Scrollbar command callback -- fires on thumb drag, track click,
        and arrow clicks (bypasses _on_mousewheel entirely).
        """
        self.canvas.yview(*args)
        self._notify_scroll_page_changed()

    def _topmost_visible_page(self) -> Optional[int]:
        """Page number whose thumbnail is closest to the current top of the
        scrollable view -- used to figure out what to report to the main
        viewer as "the page you scrolled to" (as opposed to clicked).
        """
        if not self.thumbnail_frames:
            return None
        bbox = self.canvas.bbox("all")
        if not bbox:
            return None
        total_height = bbox[3] - bbox[1]
        if total_height <= 0:
            return None
        view_top_px = self.canvas.yview()[0] * total_height
        return min(self.thumbnail_frames.items(),
                   key=lambda kv: abs(kv[1].winfo_y() - view_top_px))[0]

    def _notify_scroll_page_changed(self):
        """After a user-driven scroll of the thumbnail list, update the
        highlight and tell the main viewer to follow -- but without calling
        set_current_page()/its _scroll_to_page(), which would fight the
        scroll position the user is actively setting.
        """
        page_num = self._topmost_visible_page()
        if page_num is None or page_num == self.current_page:
            return
        self.current_page = page_num
        self._update_thumbnail_highlights()
        if self.on_scroll_page_changed:
            self.on_scroll_page_changed(page_num)

    def get_selected_pages(self) -> List[int]:
        """Get list of selected pages
        
        Returns:
            List of selected page numbers (1-indexed)
        """
        return sorted(list(self.selected_pages))


class PDFViewerWidget(tk.Frame):
    """Embedded PDF viewer widget"""

    PAGE_GAP = 14  # px gray divider between stacked pages in the scroll buffer

    def __init__(self, parent, document: Optional[Document] = None,
                 on_page_changed: Optional[Callable[[int], None]] = None,
                 on_after_render: Optional[Callable] = None, **kwargs):
        """
        Initialize PDF viewer widget

        Args:
            parent: Parent widget
            document: Document object to display
            on_page_changed: Optional callback(page_num) fired whenever the
                current page changes (next/prev/goto/thumbnail click)
            on_after_render: Optional callback() fired after the canvas has
                just redrawn the current page (lets callers overlay extra
                items on top of the freshly-drawn page image)
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)

        self.document = document
        self.current_page = 1
        self.zoom_level = 1.0
        self.zoom_mode = "fit_page"  # fit_page, fit_width, 100, custom

        # Continuous-scroll layout: every page's (x, y_top, w, h, zoom) is
        # precomputed up front from document metadata alone (cheap -- no
        # rendering), so the canvas scrollregion -- and therefore the
        # scrollbar -- always represents the WHOLE document, not just
        # whichever pages happen to be rendered right now. Only a window of
        # pages near the viewport actually gets a rendered bitmap; that
        # window slides (rendering newly-approached pages, evicting distant
        # ones) as the user scrolls, so memory stays bounded on long PDFs.
        self._full_layout: Dict[int, dict] = {}     # page_num -> {x, y_top, w, h, zoom}
        self._page_order: List[int] = []            # page numbers in y_top order (== numeric order)
        self._sorted_y_tops: List[float] = []        # parallel to _page_order, for bisect lookup
        self._total_height = 0
        self._content_width = 0
        self._rendered_pages: Dict[int, dict] = {}   # page_num -> {'photo', 'img_id', 'div_id'}

        self.on_page_changed = on_page_changed
        self.on_after_render = on_after_render
        
        # Check rendering backend
        self.rendering_backend = PDFRenderer.get_rendering_backend()
        if self.rendering_backend == 'none':
            print("Warning: No PDF rendering backend available")
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI"""
        # Toolbar
        toolbar = tk.Frame(self, bg='lightgray')
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        
        # Navigation buttons
        tk.Button(toolbar, text="◄", command=self.prev_page, width=3).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="►", command=self.next_page, width=3).pack(side=tk.LEFT, padx=2)
        
        self.page_label = tk.Label(toolbar, text="Page 1 of 1")
        self.page_label.pack(side=tk.LEFT, padx=10)
        
        tk.Label(toolbar, text="|").pack(side=tk.LEFT)
        
        # Zoom controls
        tk.Button(toolbar, text="−", command=self.zoom_out, width=3).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="+", command=self.zoom_in, width=3).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Fit Page", command=self.fit_page).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Fit Width", command=self.fit_width).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="100%", command=self.zoom_100).pack(side=tk.LEFT, padx=2)
        
        self.zoom_label = tk.Label(toolbar, text="100%", width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=5)
        
        # Main content area: [Thumbnails] | [Canvas + Scrollbar]
        content_area = tk.Frame(self)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Thumbnail panel on left side
        self.thumbnail_panel = ThumbnailPanel(
            content_area,
            on_page_selected=self._on_thumbnail_page_selected,
            on_scroll_page_changed=self._on_thumbnail_scrolled
        )
        self.thumbnail_panel.pack(side=tk.LEFT, fill=tk.Y)
        
        # Canvas for PDF display on right side
        canvas_frame = tk.Frame(content_area)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg='gray')

        # Scrollbar must be packed before the canvas -- pack() hands out
        # space in packing order, and the canvas's fill=BOTH/expand=True
        # would otherwise claim the whole frame first, leaving the
        # scrollbar zero width (same fix already applied in ThumbnailPanel).
        #
        # command=self._on_scrollbar_scroll rather than plain
        # self.canvas.yview -- dragging the thumb (or clicking the track/
        # arrows) must trigger the same render-window sync the wheel
        # handler does, otherwise pages you scroll to directly via the
        # scrollbar never get rendered (only wheel-driven scrolling did).
        scrollbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._on_scrollbar_scroll)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.config(yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Bind mouse wheel to scroll
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
    
    def load_document(self, document: Document):
        """
        Load a document for viewing
        
        Args:
            document: Document object
        """
        self.document = document
        self.current_page = 1
        self.zoom_level = 1.0
        self.zoom_mode = "fit_page"
        
        # Load thumbnails
        self.thumbnail_panel.load_document(document)
        
        self._update_display()
    
    def _update_display(self):
        """Update the canvas display"""
        if not self.document or self.document.page_count == 0:
            # Show placeholder
            self.canvas.delete("all")
            self.canvas.create_text(300, 400, text="No PDF loaded", font=("Arial", 14))
            self.page_label.config(text="No pages")
            self._full_layout = {}
            self._page_order = []
            self._sorted_y_tops = []
            self._rendered_pages = {}
            self._total_height = 0
            self._content_width = 0
            self.canvas.config(scrollregion=(0, 0, 0, 0))
            return

        self._rebuild_layout_and_render(self.current_page)

    def _update_page_label(self):
        if self.document:
            self.page_label.config(text=f"Page {self.current_page} of {self.document.page_count}")

    def _page_pixel_size(self, page_num: int, zoom_factor: float) -> Tuple[int, int]:
        """Estimate a page's rendered pixel size from its PDF-point
        dimensions alone (no rendering), using the same
        points * zoom * dpi/72 scale PDFRenderer uses -- so the estimate
        matches the eventual bitmap almost exactly.
        """
        pages = self.document.metadata.get('pages', []) if self.document.metadata else []
        if 1 <= page_num <= len(pages):
            page_info = pages[page_num - 1]
            width_pt, height_pt = page_info['width'], page_info['height']
        else:
            width_pt, height_pt = 612, 792  # Letter-size fallback
        scale = zoom_factor * 150 / 72
        return max(1, round(width_pt * scale)), max(1, round(height_pt * scale))

    def _compute_full_layout(self):
        """Precompute (x, y_top, w, h, zoom) for every page in the document
        from metadata alone, and size the canvas scrollregion to the full
        stacked height. This is what makes the scrollbar represent the
        whole document -- like the page-thumbnail panel's -- rather than
        just whatever window of pages is currently rendered.
        """
        self._full_layout = {}
        self._page_order = []
        self._sorted_y_tops = []

        if not self.document:
            self._total_height = 0
            self._content_width = 0
            return

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        page_count = self.document.page_count

        y_cursor = 0
        max_w = canvas_w
        for page_num in range(1, page_count + 1):
            zoom_factor = self._calculate_zoom_factor(page_num)
            w_px, h_px = self._page_pixel_size(page_num, zoom_factor)
            x = max(0, (canvas_w - w_px) // 2) if canvas_w > 1 else 0

            self._full_layout[page_num] = {'x': x, 'y_top': y_cursor, 'w': w_px, 'h': h_px,
                                            'zoom': zoom_factor}
            self._page_order.append(page_num)
            self._sorted_y_tops.append(y_cursor)
            max_w = max(max_w, w_px)
            y_cursor += h_px + self.PAGE_GAP

        self._total_height = max(canvas_h, y_cursor - self.PAGE_GAP if page_count else canvas_h)
        self._content_width = max_w
        self.canvas.config(scrollregion=(0, 0, self._content_width, self._total_height))

    def _page_at_pixel(self, y_px: float) -> Optional[int]:
        """The page whose layout span contains (or immediately precedes)
        the given absolute canvas y pixel. O(log n) via bisect since
        _sorted_y_tops is built in increasing page-number/y_top order.
        """
        if not self._page_order:
            return None
        idx = bisect.bisect_right(self._sorted_y_tops, y_px) - 1
        idx = max(0, min(idx, len(self._page_order) - 1))
        return self._page_order[idx]

    def _render_page_bitmap(self, page_num: int):
        """Render and draw a single page's bitmap (plus its trailing
        divider bar) at its already-known absolute position. No-op if
        already rendered.
        """
        if page_num in self._rendered_pages or page_num not in self._full_layout:
            return
        layout = self._full_layout[page_num]

        img = PDFRenderer.render_page(
            self.document.pdf_path, page_num, zoom=layout['zoom'], dpi=150
        )
        if img is None:
            img = PDFRenderer.create_placeholder_image(
                text=f"Could not render page {page_num}\n(Install PyMuPDF for best results)"
            )
        photo = PIL.ImageTk.PhotoImage(img)
        img_id = self.canvas.create_image(layout['x'], layout['y_top'],
                                           image=photo, anchor=tk.NW)

        # Divider bar in the gap below this page, so page boundaries stay
        # visually clear while scrolling continuously through them (like
        # Word's page view) -- skip after the last page (no gap follows it).
        div_id = None
        if page_num < self.document.page_count:
            gap_top = layout['y_top'] + layout['h']
            div_id = self.canvas.create_rectangle(
                0, gap_top, self._content_width, gap_top + self.PAGE_GAP,
                fill='#595959', width=0)

        self._rendered_pages[page_num] = {'photo': photo, 'img_id': img_id, 'div_id': div_id}

    def _evict_page_bitmap(self, page_num: int):
        """Drop a rendered page's canvas items/bitmap once it's scrolled
        far enough out of view, so memory stays bounded on long documents.
        """
        entry = self._rendered_pages.pop(page_num, None)
        if not entry:
            return
        self.canvas.delete(entry['img_id'])
        if entry['div_id'] is not None:
            self.canvas.delete(entry['div_id'])

    def _sync_render_window(self):
        """Ensure pages within ~1 viewport-height of the visible area are
        rendered, and evict pages more than ~2 viewport-heights away.
        Layout positions are stable (precomputed), so this never needs to
        touch scrollregion/yview -- only which bitmaps exist on screen.
        """
        if not self.document or not self._full_layout:
            return

        viewport_h = max(1, self.canvas.winfo_height())
        view_top_frac, view_bottom_frac = self.canvas.yview()
        view_top_px = view_top_frac * self._total_height
        view_bottom_px = view_bottom_frac * self._total_height

        render_lo = view_top_px - viewport_h
        render_hi = view_bottom_px + viewport_h
        evict_lo = view_top_px - 2 * viewport_h
        evict_hi = view_bottom_px + 2 * viewport_h

        for page_num, layout in self._full_layout.items():
            p_top, p_bottom = layout['y_top'], layout['y_top'] + layout['h']
            if p_bottom >= render_lo and p_top <= render_hi:
                self._render_page_bitmap(page_num)

        for page_num in list(self._rendered_pages.keys()):
            layout = self._full_layout[page_num]
            p_top, p_bottom = layout['y_top'], layout['y_top'] + layout['h']
            if p_bottom < evict_lo or p_top > evict_hi:
                self._evict_page_bitmap(page_num)

    def _jump_to_page(self, page_num: int):
        """Scroll so the top of page_num is at the top of the viewport
        (explicit navigation/thumbnail click), then render whatever's now
        visible.
        """
        layout = self._full_layout.get(page_num)
        if not layout or not self._total_height:
            return
        frac = layout['y_top'] / self._total_height
        self.canvas.yview_moveto(max(0.0, frac))
        self._sync_render_window()
        self._update_page_label()
        if self.on_after_render:
            self.on_after_render()

    def _rebuild_layout_and_render(self, center_page: int):
        """Full rebuild: recompute the whole-document layout (document
        load, or zoom mode/level change -- anything that changes every
        page's pixel size) and redraw the render window around
        center_page.
        """
        self.canvas.delete("all")
        self._rendered_pages = {}
        self._compute_full_layout()
        center_page = max(1, min(center_page, self.document.page_count))
        self._jump_to_page(center_page)

    def get_render_offset(self) -> tuple:
        """Current (x, y) pixel offset of the current page's top-left
        corner within the canvas. Needed by anything that overlays items
        on top of the page (e.g. image objects) to convert between canvas
        pixels and PDF points correctly.
        """
        layout = self._full_layout.get(self.current_page)
        if not layout:
            return (0, 0)
        return (layout['x'], layout['y_top'])

    def get_page_to_screen_scale(self) -> float:
        """Current pixels-per-PDF-point scale factor for the current page.

        Combines that page's active zoom factor with the fixed 150 DPI
        render resolution used when rendering page bitmaps, so canvas
        pixel coordinates can be converted to/from PDF points.
        """
        layout = self._full_layout.get(self.current_page)
        if not layout:
            return 0.0
        return layout['zoom'] * 150 / 72

    def get_current_page_height_pt(self) -> Optional[float]:
        """Height of the currently displayed page, in PDF points."""
        if not self.document or not self.document.metadata:
            return None
        pages = self.document.metadata.get('pages', [])
        if 1 <= self.current_page <= len(pages):
            return pages[self.current_page - 1]['height']
        return None

    def _notify_page_changed(self):
        """Notify listeners that the current page has changed"""
        if self.on_page_changed:
            self.on_page_changed(self.current_page)
    
    def _calculate_zoom_factor(self, page_num: Optional[int] = None) -> float:
        """Calculate zoom factor based on zoom mode, for the given page
        (defaults to the current page). Fit-page/fit-width depend on that
        specific page's dimensions, which can differ page to page.
        """
        page_num = page_num if page_num is not None else self.current_page

        if self.zoom_mode == "100":
            return 1.0
        elif self.zoom_mode == "fit_page":
            # Calculate zoom to fit entire page in canvas
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width < 100 or canvas_height < 100:
                return 1.0  # Canvas not yet initialized

            # Get page dimensions
            if self.document and self.document.metadata:
                pages = self.document.metadata.get('pages', [])
                if 1 <= page_num <= len(pages):
                    page_info = pages[page_num - 1]
                    page_width = page_info['width']
                    page_height = page_info['height']

                    # Convert points to pixels (at 150 DPI)
                    page_width_px = page_width * 150 / 72
                    page_height_px = page_height * 150 / 72

                    zoom_w = (canvas_width - 20) / page_width_px
                    zoom_h = (canvas_height - 20) / page_height_px

                    return min(zoom_w, zoom_h, 2.0)  # Cap at 2.0

            return 1.0
        elif self.zoom_mode == "fit_width":
            # Calculate zoom to fit page width in canvas
            canvas_width = self.canvas.winfo_width()
            if canvas_width < 100:
                return 1.0

            if self.document and self.document.metadata:
                pages = self.document.metadata.get('pages', [])
                if 1 <= page_num <= len(pages):
                    page_info = pages[page_num - 1]
                    page_width = page_info['width']
                    page_width_px = page_width * 150 / 72

                    return (canvas_width - 20) / page_width_px

            return 1.0
        else:
            return self.zoom_level
    
    def next_page(self):
        """Go to next page"""
        if self.document and self.current_page < self.document.page_count:
            self.current_page += 1
            self.thumbnail_panel.set_current_page(self.current_page)
            self._jump_to_page(self.current_page)
            self._notify_page_changed()

    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            self.thumbnail_panel.set_current_page(self.current_page)
            self._jump_to_page(self.current_page)
            self._notify_page_changed()

    def goto_page(self, page_num: int):
        """Go to specific page

        Args:
            page_num: Page number (1-indexed)
        """
        if self.document and 1 <= page_num <= self.document.page_count:
            self.current_page = page_num
            self.thumbnail_panel.set_current_page(page_num)
            self._jump_to_page(page_num)
            self._notify_page_changed()

    def zoom_in(self):
        """Zoom in"""
        self.zoom_mode = "custom"
        self.zoom_level = min(self.zoom_level * 1.2, 4.0)
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self._rebuild_layout_and_render(self.current_page)

    def zoom_out(self):
        """Zoom out"""
        self.zoom_mode = "custom"
        self.zoom_level = max(self.zoom_level / 1.2, 0.25)
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self._rebuild_layout_and_render(self.current_page)

    def fit_page(self):
        """Fit entire page in canvas"""
        self.zoom_mode = "fit_page"
        self.zoom_label.config(text="Fit")
        self._rebuild_layout_and_render(self.current_page)

    def fit_width(self):
        """Fit page width to canvas"""
        self.zoom_mode = "fit_width"
        self.zoom_label.config(text="Width")
        self._rebuild_layout_and_render(self.current_page)

    def zoom_100(self):
        """Zoom to 100%"""
        self.zoom_mode = "100"
        self.zoom_level = 1.0
        self.zoom_label.config(text="100%")
        self._rebuild_layout_and_render(self.current_page)

    def _on_mousewheel(self, event):
        """Handle mouse wheel scroll -- glides continuously across page
        boundaries since page layout is precomputed for the whole document
        (see _compute_full_layout), instead of jumping straight from one
        whole page to the next.
        """
        scrolling_down = event.num == 5 or event.delta < 0
        self.canvas.yview_scroll(3 if scrolling_down else -3, "units")
        self._sync_render_window()
        self._sync_current_page_from_scroll()

    def _on_scrollbar_scroll(self, *args):
        """Scrollbar command callback -- fires on thumb drag, track click,
        and arrow clicks. Must do the same work as the wheel handler
        (render the pages now in view, sync current_page/thumbnail
        highlight) since this bypasses _on_mousewheel entirely.
        """
        self.canvas.yview(*args)
        self._sync_render_window()
        self._sync_current_page_from_scroll()

    def _sync_current_page_from_scroll(self):
        """After a wheel-driven scroll, figure out which page is now the
        'current' one -- whichever page's vertical span holds the
        viewport's vertical midpoint -- and update dependent UI (page
        label, thumbnail highlight, overlay/footer position) if it changed.
        """
        if not self.document or not self._page_order or not self._total_height:
            return

        viewport_h = self.canvas.winfo_height()
        view_top_px = self.canvas.yview()[0] * self._total_height
        view_mid_px = view_top_px + viewport_h / 2

        new_current = self._page_at_pixel(view_mid_px) or self.current_page

        if new_current != self.current_page:
            self.current_page = new_current
            self.thumbnail_panel.set_current_page(new_current)
            self._update_page_label()
            self._notify_page_changed()
            if self.on_after_render:
                self.on_after_render()

    def _on_thumbnail_page_selected(self, page_num: int):
        """Callback when a page is selected via thumbnail

        Args:
            page_num: Selected page number (1-indexed)
        """
        self.current_page = page_num
        self._jump_to_page(page_num)
        self._notify_page_changed()

    def _on_thumbnail_scrolled(self, page_num: int):
        """Callback when the user scrolls the thumbnail list (not a click)
        -- keep the main view following along, the same way scrolling the
        main view keeps the thumbnail list following (see
        _sync_current_page_from_scroll). Does NOT call
        thumbnail_panel.set_current_page(), which would fight the scroll
        position the user is actively setting there.
        """
        if not self.document or not (1 <= page_num <= self.document.page_count):
            return
        self.current_page = page_num
        self._jump_to_page(page_num)
        self._notify_page_changed()
