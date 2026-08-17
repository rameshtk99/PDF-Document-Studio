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

import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable, List, Dict, Set
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
                 on_page_selected: Optional[Callable] = None, **kwargs):
        """
        Initialize thumbnail panel
        
        Args:
            parent: Parent widget
            document: Document object
            on_page_selected: Callback function(page_num) when page clicked
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, **kwargs)
        
        self.document = document
        self.on_page_selected = on_page_selected
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
        scrollbar.config(command=self.canvas.yview)
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
    
    def get_selected_pages(self) -> List[int]:
        """Get list of selected pages
        
        Returns:
            List of selected page numbers (1-indexed)
        """
        return sorted(list(self.selected_pages))


class PDFViewerWidget(tk.Frame):
    """Embedded PDF viewer widget"""
    
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
        self.rendered_image = None
        self.photo_image = None
        self.render_offset_x = 0
        self.render_offset_y = 0
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
            on_page_selected=self._on_thumbnail_page_selected
        )
        self.thumbnail_panel.pack(side=tk.LEFT, fill=tk.Y)
        
        # Canvas for PDF display on right side
        canvas_frame = tk.Frame(content_area)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg='gray')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.config(yscrollcommand=scrollbar.set)
        
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
            return
        
        # Render current page
        self._render_and_display_page()
        
        # Update page label
        self.page_label.config(text=f"Page {self.current_page} of {self.document.page_count}")
    
    def _render_and_display_page(self):
        """Render current page and display on canvas"""
        if not self.document:
            return
        
        # Determine zoom
        zoom_factor = self._calculate_zoom_factor()
        
        # Render page
        img = PDFRenderer.render_page(
            self.document.pdf_path,
            self.current_page,
            zoom=zoom_factor,
            dpi=150
        )
        
        if img is None:
            # Fallback: show placeholder
            img = PDFRenderer.create_placeholder_image(
                text=f"Could not render page {self.current_page}\n(Install PyMuPDF for best results)"
            )
        
        self.rendered_image = img

        # Convert to PhotoImage and display
        self.photo_image = PIL.ImageTk.PhotoImage(img)

        # Center the page in the canvas when it's smaller than the visible
        # viewport (e.g. Fit Page on a page whose aspect ratio doesn't match
        # the canvas) instead of pinning it to the top-left corner, which
        # otherwise dumps all the leftover space as a single dead-looking
        # gray block on the right/bottom.
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_w, img_h = self.photo_image.width(), self.photo_image.height()
        self.render_offset_x = max(0, (canvas_w - img_w) // 2) if canvas_w > 1 else 0
        self.render_offset_y = max(0, (canvas_h - img_h) // 2) if canvas_h > 1 else 0

        self.canvas.delete("all")
        self.canvas.create_image(self.render_offset_x, self.render_offset_y,
                                  image=self.photo_image, anchor=tk.NW)

        # Update scroll region -- include the full viewport so the centering
        # padding isn't clipped when the page is smaller than the canvas.
        scroll_w = max(canvas_w, img_w + self.render_offset_x)
        scroll_h = max(canvas_h, img_h + self.render_offset_y)
        self.canvas.config(scrollregion=(0, 0, scroll_w, scroll_h))

        if self.on_after_render:
            self.on_after_render()

    def get_render_offset(self) -> tuple:
        """Current (x, y) pixel offset of the rendered page's top-left
        corner within the canvas, from centering. Needed by anything that
        overlays items on top of the page (e.g. image objects) to convert
        between canvas pixels and PDF points correctly.
        """
        return (self.render_offset_x, self.render_offset_y)

    def get_page_to_screen_scale(self) -> float:
        """Current pixels-per-PDF-point scale factor for the rendered page.

        Combines the active zoom factor with the fixed 150 DPI render
        resolution used by `_render_and_display_page`, so canvas pixel
        coordinates can be converted to/from PDF points.
        """
        return self._calculate_zoom_factor() * 150 / 72

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
    
    def _calculate_zoom_factor(self) -> float:
        """Calculate zoom factor based on zoom mode"""
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
                if self.current_page <= len(pages):
                    page_info = pages[self.current_page - 1]
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
                if self.current_page <= len(pages):
                    page_info = pages[self.current_page - 1]
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
            self._update_display()
            self._notify_page_changed()

    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            self.thumbnail_panel.set_current_page(self.current_page)
            self._update_display()
            self._notify_page_changed()

    def goto_page(self, page_num: int):
        """Go to specific page

        Args:
            page_num: Page number (1-indexed)
        """
        if self.document and 1 <= page_num <= self.document.page_count:
            self.current_page = page_num
            self.thumbnail_panel.set_current_page(page_num)
            self._update_display()
            self._notify_page_changed()
    
    def zoom_in(self):
        """Zoom in"""
        self.zoom_mode = "custom"
        self.zoom_level = min(self.zoom_level * 1.2, 4.0)
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self._update_display()
    
    def zoom_out(self):
        """Zoom out"""
        self.zoom_mode = "custom"
        self.zoom_level = max(self.zoom_level / 1.2, 0.25)
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self._update_display()
    
    def fit_page(self):
        """Fit entire page in canvas"""
        self.zoom_mode = "fit_page"
        self.zoom_label.config(text="Fit")
        self._update_display()
    
    def fit_width(self):
        """Fit page width to canvas"""
        self.zoom_mode = "fit_width"
        self.zoom_label.config(text="Width")
        self._update_display()
    
    def zoom_100(self):
        """Zoom to 100%"""
        self.zoom_mode = "100"
        self.zoom_level = 1.0
        self.zoom_label.config(text="100%")
        self._update_display()
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scroll -- continuous-scroll mode: scrolling
        past the bottom/top edge of the current page advances to the
        next/previous page instead of stopping dead at the page boundary.
        """
        scrolling_down = event.num == 5 or event.delta < 0
        top, bottom = self.canvas.yview()

        if scrolling_down and bottom >= 0.999:
            if self.document and self.current_page < self.document.page_count:
                self.next_page()
                self.canvas.yview_moveto(0)
            return

        if not scrolling_down and top <= 0.001:
            if self.current_page > 1:
                self.prev_page()
                self.canvas.yview_moveto(1)
            return

        self.canvas.yview_scroll(3 if scrolling_down else -3, "units")
    
    def _on_thumbnail_page_selected(self, page_num: int):
        """Callback when a page is selected via thumbnail
        
        Args:
            page_num: Selected page number (1-indexed)
        """
        self.current_page = page_num
        self._update_display()
        self._notify_page_changed()
