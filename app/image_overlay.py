"""
Interactive image layer: binds app/image_editor.py's pure geometry/state
(ImageEditor, SelectionBox, ResizeHandle) to real mouse events on a
PDFViewerWidget's canvas, plus an Image Properties side panel.

Coordinate convention (matches PageObject/ImagePlacement usage elsewhere
in the codebase, e.g. ImageManager.validate_image_placement and
FooterGenerator._draw_image_object): object x/y are standard PDF points,
origin at the page's bottom-left, y increasing upward. The canvas, like
any Tkinter/image surface, has its origin at the top-left with y
increasing downward. All conversion between the two happens in this
module via `_canvas_to_pdf` / `_pdf_to_canvas`, using the page height and
the viewer's current render scale.
"""

import os
import tkinter as tk
from typing import Callable, Optional

from PIL import Image, ImageTk

from app.image_editor import ImageEditor, SelectionBox
from app.undo_redo import UndoRedoManager
from app.document_commands import (
    MoveObjectCommand, ResizeObjectCommand, ChangeObjectPropertyCommand,
    AddObjectCommand, DeleteObjectCommand,
)
from pdf.image_manager import ImageManager, ImagePlacement

HANDLE_PIXEL_SIZE = 8


class ImageOverlayController:
    """Draws image objects on top of a PDFViewerWidget's canvas and wires
    mouse drag/resize to a real ImageManager + UndoRedoManager.
    """

    def __init__(self, pdf_viewer, manager: ImageManager, editor: ImageEditor,
                 undo_manager: UndoRedoManager,
                 on_selection_changed: Optional[Callable[[Optional[str]], None]] = None):
        self.pdf_viewer = pdf_viewer
        self.manager = manager
        self.editor = editor
        self.undo_manager = undo_manager
        self.on_selection_changed = on_selection_changed

        self.selected_id: Optional[str] = None
        self._photo_refs = {}
        self._drag_before = None

        canvas = self.pdf_viewer.canvas
        canvas.bind("<Button-1>", self._on_press, add="+")
        canvas.bind("<B1-Motion>", self._on_motion, add="+")
        canvas.bind("<ButtonRelease-1>", self._on_release, add="+")

    # -- page/selection lifecycle -------------------------------------

    def on_page_changed(self, page_num: int):
        """Call when the viewer's current page changes"""
        self.select(None)

    def select(self, image_id: Optional[str]):
        self.selected_id = image_id
        if self.on_selection_changed:
            self.on_selection_changed(image_id)
        self.redraw()

    # -- drawing ---------------------------------------------------------

    def redraw(self):
        canvas = self.pdf_viewer.canvas
        canvas.delete("obj_overlay")
        self._photo_refs.clear()

        if not self.pdf_viewer.document:
            return

        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        if not scale or not page_h:
            return

        page_num = self.pdf_viewer.current_page
        for obj in self.manager.get_page_images(page_num):
            if not obj.visible:
                continue
            self._draw_object(canvas, obj, scale, page_h)

    def _draw_object(self, canvas, obj, scale, page_h):
        left, top = self._pdf_to_canvas(obj.x, obj.y + obj.height, scale, page_h)
        right, bottom = self._pdf_to_canvas(obj.x + obj.width, obj.y, scale, page_h)
        w_px = max(1, int(round(right - left)))
        h_px = max(1, int(round(bottom - top)))

        photo = self._build_thumbnail(obj, w_px, h_px)
        if photo:
            canvas.create_image(left, top, anchor=tk.NW, image=photo, tags="obj_overlay")
            self._photo_refs[obj.id] = photo
        else:
            canvas.create_rectangle(left, top, right, bottom, outline='gray',
                                     dash=(3, 2), tags="obj_overlay")

        if obj.locked:
            canvas.create_text(left + 4, top + 4, anchor=tk.NW, text="🔒",
                                font=('Arial', 8), tags="obj_overlay")

        if obj.id == self.selected_id:
            canvas.create_rectangle(left, top, right, bottom, outline='#0080FF',
                                     width=2, dash=(4, 2), tags="obj_overlay")
            box = SelectionBox(obj.x, obj.y, obj.width, obj.height)
            self.editor.selection_boxes[obj.id] = box
            if obj.id not in self.editor.selected_objects:
                self.editor.selected_objects = [obj.id]
            for handle in box.get_resize_handles():
                hx, hy = self._pdf_to_canvas(handle.x, handle.y, scale, page_h)
                s = HANDLE_PIXEL_SIZE / 2
                canvas.create_rectangle(hx - s, hy - s, hx + s, hy + s,
                                         fill='white', outline='#0080FF', tags="obj_overlay")

    def _build_thumbnail(self, obj, w_px, h_px):
        path = (obj.properties or {}).get('image_path')
        if not path or not os.path.exists(path) or w_px <= 0 or h_px <= 0:
            return None
        try:
            img = Image.open(path).convert('RGBA')
            img = img.resize((w_px, h_px), Image.Resampling.LANCZOS)
            if obj.rotation:
                img = img.rotate(-obj.rotation, expand=False, resample=Image.BICUBIC)
            opacity = max(0.0, min(100.0, obj.opacity))
            if opacity < 100.0:
                alpha = img.split()[3].point(lambda p: int(p * opacity / 100.0))
                img.putalpha(alpha)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    # -- coordinate conversion -------------------------------------------

    def _pdf_to_canvas(self, x, y, scale, page_h):
        """PDF point (bottom-left origin, y up) -> canvas pixel (top-left origin, y down)"""
        off_x, off_y = self.pdf_viewer.get_render_offset()
        return (x * scale + off_x, (page_h - y) * scale + off_y)

    def _canvas_to_pdf(self, cx, cy):
        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        if not scale or not page_h:
            return (0.0, 0.0)
        off_x, off_y = self.pdf_viewer.get_render_offset()
        return ((cx - off_x) / scale, page_h - (cy - off_y) / scale)

    # -- mouse handling ----------------------------------------------------

    def _on_press(self, event):
        if not self.pdf_viewer.document:
            return
        canvas = self.pdf_viewer.canvas
        cx, cy = canvas.canvasx(event.x), canvas.canvasy(event.y)
        px, py = self._canvas_to_pdf(cx, cy)
        page_num = self.pdf_viewer.current_page

        # Resize handles of the current selection take priority
        if self.selected_id:
            box = self.editor.selection_boxes.get(self.selected_id)
            if box:
                for handle in box.get_resize_handles():
                    if handle.contains_point(px, py):
                        obj = self.manager.get_image_object(self.selected_id)
                        if obj and not obj.locked:
                            self.editor.start_resize(handle, self.selected_id)
                            self._drag_before = self._snapshot(obj)
                        return

        images = self.manager.get_page_images(page_num)
        ids = [o.id for o in images if o.visible and not o.locked]
        hit_id = self.editor.get_hit_target(px, py, ids, self.manager)

        if hit_id:
            self.select(hit_id)
            obj = self.manager.get_image_object(hit_id)
            self.editor.start_drag(px, py, hit_id)
            self._drag_before = self._snapshot(obj)
        else:
            self.select(None)

    def _on_motion(self, event):
        if not (self.editor.dragging_object or self.editor.resizing_object):
            return
        canvas = self.pdf_viewer.canvas
        cx, cy = canvas.canvasx(event.x), canvas.canvasy(event.y)
        px, py = self._canvas_to_pdf(cx, cy)
        self.editor.drag_to(px, py)
        self.redraw()

    def _on_release(self, event):
        target = self.editor.dragging_object or self.editor.resizing_object
        was_resize = self.editor.resizing_object is not None
        self.editor.end_drag()

        if target and self._drag_before:
            obj = self.manager.get_image_object(target)
            before = self._drag_before
            if obj:
                if was_resize:
                    if (before['x'], before['y'], before['width'], before['height']) != \
                       (obj.x, obj.y, obj.width, obj.height):
                        self.undo_manager.execute(ResizeObjectCommand(
                            self.manager, target,
                            before['x'], before['y'], before['width'], before['height'],
                            obj.x, obj.y, obj.width, obj.height,
                        ))
                else:
                    if (before['x'], before['y']) != (obj.x, obj.y):
                        self.undo_manager.execute(MoveObjectCommand(
                            self.manager, target, before['x'], before['y'], obj.x, obj.y,
                        ))
            self.redraw()

        self._drag_before = None

    @staticmethod
    def _snapshot(obj):
        return {'x': obj.x, 'y': obj.y, 'width': obj.width, 'height': obj.height}


class ImagePropertiesPanel(tk.Frame):
    """Numeric X/Y/Width/Height/Rotation/Opacity editor for the currently
    selected image object, plus Lock/Delete/Duplicate.
    """

    FIELDS = [('x', 'X'), ('y', 'Y'), ('width', 'Width'), ('height', 'Height'),
              ('rotation', 'Rotation'), ('opacity', 'Opacity')]

    def __init__(self, parent, undo_manager: UndoRedoManager,
                 on_applied: Optional[Callable] = None,
                 on_selection_changed: Optional[Callable[[Optional[str]], None]] = None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.undo_manager = undo_manager
        self.on_applied = on_applied
        self.on_selection_changed = on_selection_changed

        self.manager: Optional[ImageManager] = None
        self.page_number: Optional[int] = None
        self.image_id: Optional[str] = None
        self._aspect_ratio: Optional[float] = None
        self._suspend = False

        self.vars = {}
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg='darkgray')
        header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(header, text="Image Properties", bg='darkgray', fg='white',
                 font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=4, pady=2)

        self.body = tk.Frame(self)
        self.body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        for i, (key, label) in enumerate(self.FIELDS):
            tk.Label(self.body, text=f"{label}:").grid(row=i, column=0, sticky='e', pady=2)
            var = tk.StringVar()
            entry = tk.Entry(self.body, textvariable=var, width=10)
            entry.grid(row=i, column=1, sticky='w', pady=2)
            entry.bind('<Return>', lambda e, k=key: self._apply_field(k))
            entry.bind('<FocusOut>', lambda e, k=key: self._apply_field(k))
            self.vars[key] = var

        row = len(self.FIELDS)
        self.lock_aspect_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.body, text="Lock aspect ratio",
                        variable=self.lock_aspect_var).grid(row=row, column=0, columnspan=2, sticky='w')

        self.locked_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.body, text="Locked", variable=self.locked_var,
                        command=self._apply_locked).grid(row=row + 1, column=0, columnspan=2, sticky='w')

        btns = tk.Frame(self.body)
        btns.grid(row=row + 2, column=0, columnspan=2, pady=6)
        tk.Button(btns, text="Duplicate", command=self._duplicate).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text="Delete", command=self._delete, bg='salmon').pack(side=tk.LEFT, padx=2)

        self.set_enabled(False)

    def set_manager_context(self, manager: ImageManager, page_number: int):
        self.manager = manager
        self.page_number = page_number

    def load_object(self, image_id: str):
        if not self.manager:
            self.clear()
            return
        obj = self.manager.get_image_object(image_id)
        if not obj:
            self.clear()
            return

        self.image_id = image_id
        self._suspend = True
        self.vars['x'].set(f"{obj.x:.1f}")
        self.vars['y'].set(f"{obj.y:.1f}")
        self.vars['width'].set(f"{obj.width:.1f}")
        self.vars['height'].set(f"{obj.height:.1f}")
        self.vars['rotation'].set(f"{obj.rotation:.1f}")
        self.vars['opacity'].set(f"{obj.opacity:.1f}")
        self.locked_var.set(bool(obj.locked))
        self._aspect_ratio = (obj.width / obj.height) if obj.height else None
        self._suspend = False
        self.set_enabled(True)

    def clear(self):
        self.image_id = None
        for var in self.vars.values():
            var.set("")
        self.set_enabled(False)

    def set_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for child in self.body.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass

    def _apply_field(self, key):
        if self._suspend or not self.image_id or not self.manager:
            return
        obj = self.manager.get_image_object(self.image_id)
        if not obj:
            return
        try:
            value = float(self.vars[key].get())
        except ValueError:
            self.load_object(self.image_id)
            return

        if key in ('x', 'y'):
            to_x = value if key == 'x' else obj.x
            to_y = value if key == 'y' else obj.y
            if (obj.x, obj.y) != (to_x, to_y):
                self.undo_manager.execute(MoveObjectCommand(
                    self.manager, self.image_id, obj.x, obj.y, to_x, to_y))
        elif key in ('width', 'height'):
            to_w, to_h = obj.width, obj.height
            if key == 'width':
                to_w = max(5.0, value)
                if self.lock_aspect_var.get() and self._aspect_ratio:
                    to_h = to_w / self._aspect_ratio
            else:
                to_h = max(5.0, value)
                if self.lock_aspect_var.get() and self._aspect_ratio:
                    to_w = to_h * self._aspect_ratio
            if (obj.width, obj.height) != (to_w, to_h):
                self.undo_manager.execute(ResizeObjectCommand(
                    self.manager, self.image_id, obj.x, obj.y, obj.width, obj.height,
                    obj.x, obj.y, to_w, to_h))
        elif key == 'rotation':
            to_v = value % 360
            if obj.rotation != to_v:
                self.undo_manager.execute(ChangeObjectPropertyCommand(
                    self.manager, self.image_id, 'rotation', obj.rotation, to_v))
        elif key == 'opacity':
            to_v = max(0.0, min(100.0, value))
            if obj.opacity != to_v:
                self.undo_manager.execute(ChangeObjectPropertyCommand(
                    self.manager, self.image_id, 'opacity', obj.opacity, to_v))

        self.load_object(self.image_id)
        if self.on_applied:
            self.on_applied()

    def _apply_locked(self):
        if not self.image_id or not self.manager:
            return
        obj = self.manager.get_image_object(self.image_id)
        if not obj:
            return
        to_v = self.locked_var.get()
        if obj.locked != to_v:
            self.undo_manager.execute(ChangeObjectPropertyCommand(
                self.manager, self.image_id, 'locked', obj.locked, to_v))
        if self.on_applied:
            self.on_applied()

    def _duplicate(self):
        if not self.image_id or not self.manager or self.page_number is None:
            return
        obj = self.manager.get_image_object(self.image_id)
        if not obj:
            return
        placement = ImagePlacement(
            page_number=self.page_number, x=obj.x + 10, y=max(0.0, obj.y - 10),
            width=obj.width, height=obj.height, rotation=obj.rotation,
            opacity=obj.opacity, z_index=obj.z_index + 1,
        )
        image_path = (obj.properties or {}).get('image_path')
        cmd = AddObjectCommand(self.manager, self.page_number, placement, image_path)
        self.undo_manager.execute(cmd)
        if cmd.image_id:
            self.load_object(cmd.image_id)
            if self.on_selection_changed:
                self.on_selection_changed(cmd.image_id)
        if self.on_applied:
            self.on_applied()

    def _delete(self):
        if not self.image_id or not self.manager or self.page_number is None:
            return
        obj = self.manager.get_image_object(self.image_id)
        if not obj:
            return
        self.undo_manager.execute(DeleteObjectCommand(self.manager, self.page_number, obj))
        self.clear()
        if self.on_selection_changed:
            self.on_selection_changed(None)
        if self.on_applied:
            self.on_applied()
