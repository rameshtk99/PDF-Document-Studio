"""
Interactive image layer: multi-select, group, rotate, Shift-resize, copy/paste.

Coordinate convention: PageObject x/y are PDF points, origin bottom-left,
y increasing upward.  Canvas pixels have origin top-left, y increasing
downward.  All conversion between the two is done by `_pdf_to_canvas` /
`_canvas_to_pdf` using the page height and the viewer's current render scale.

Interaction modes
-----------------
MOVE       -- drag any selected object; all selected objects move together
RESIZE     -- drag a corner/edge handle; all selected objects scale from
              the anchor corner.  Hold Shift → aspect ratio locked.
ROTATE     -- drag the rotation handle (circle above selection box);
              all selected objects orbit the group center and spin by
              the same delta.  Completely free (any angle, no snapping).

Selection
---------
Click               → select single object (auto-expands to whole group)
Ctrl+Click          → add/remove object from selection (whole group added)
Click empty space   → deselect all

Keyboard
--------
Ctrl+G          → group selected images
Ctrl+Shift+G    → ungroup selected images
Ctrl+C          → copy selected images to clipboard
Ctrl+V          → paste clipboard to current page (offset +15pt)
Delete          → handled by editor_window; no change needed here
"""

import math
import os
import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageTk

from app.image_editor import ImageEditor, SelectionBox
from app.undo_redo import UndoRedoManager
from app.document_commands import (
    MoveObjectCommand, ResizeObjectCommand, ChangeObjectPropertyCommand,
    AddObjectCommand, DeleteObjectCommand,
    GroupCommand, MoveManyCommand, TransformManyCommand,
    RotateManyCommand, PasteObjectsCommand,
)
from pdf.image_manager import ImageManager, ImagePlacement

HANDLE_SIZE = 8          # half-size of a resize handle in pixels
ROT_HANDLE_OFFSET = 28   # pixels above selection box top-center
ROT_HANDLE_RADIUS = 7    # pixel radius of the rotation handle circle
MIN_OBJ_SIZE = 5.0       # minimum PDF-point dimension after resize
PASTE_OFFSET = 15.0      # PDF-point offset for pasted copies


def _group_bounds(objs) -> Optional[Tuple[float, float, float, float]]:
    """Union bounding box of a list of PageObjects. Returns (x, y, w, h) PDF."""
    objs = [o for o in objs if o]
    if not objs:
        return None
    min_x = min(o.x for o in objs)
    min_y = min(o.y for o in objs)
    max_x = max(o.x + o.width for o in objs)
    max_y = max(o.y + o.height for o in objs)
    return (min_x, min_y, max_x - min_x, max_y - min_y)


def _snapshot_obj(obj) -> dict:
    return {
        'x': obj.x, 'y': obj.y,
        'width': obj.width, 'height': obj.height,
        'rotation': obj.rotation, 'opacity': obj.opacity,
        'z_index': obj.z_index,
        'group_id': obj.group_id,
        'image_path': (obj.properties or {}).get('image_path', ''),
    }


class ImageOverlayController:
    """Draws image objects on a PDFViewerWidget's canvas and handles all
    interactive manipulation (select, move, resize, rotate, group, copy/paste).
    """

    def __init__(self, pdf_viewer, manager: ImageManager, editor: ImageEditor,
                 undo_manager: UndoRedoManager,
                 on_selection_changed: Optional[Callable[[Optional[str]], None]] = None):
        self.pdf_viewer = pdf_viewer
        self.manager = manager
        self.editor = editor
        self.undo_manager = undo_manager
        self.on_selection_changed = on_selection_changed

        # Multi-selection; selected_id kept for backward compat with properties panel
        self.selected_ids: List[str] = []
        self.selected_id: Optional[str] = None   # first of selected_ids (or None)

        self._photo_refs: Dict[str, object] = {}
        self._clipboard: Optional[List[dict]] = None

        # Drag state
        self._mode = 'idle'          # 'idle' | 'move' | 'resize' | 'rotate'
        self._drag_start_canvas: Tuple[float, float] = (0.0, 0.0)
        self._drag_start_pdf: Tuple[float, float] = (0.0, 0.0)
        self._resize_handle: Optional[str] = None
        self._initial_states: Dict[str, dict] = {}   # id -> snapshot at drag start
        self._initial_bounds: Optional[Tuple] = None  # (x,y,w,h) at drag start
        self._rotate_center_canvas: Tuple[float, float] = (0.0, 0.0)
        self._rotate_start_angle: float = 0.0        # canvas angle at drag start

        # Cached rotation handle position in canvas coords (set during redraw)
        self._rot_handle_canvas: Optional[Tuple[float, float]] = None

        canvas = self.pdf_viewer.canvas
        canvas.bind("<Button-1>",        self._on_press,   add="+")
        canvas.bind("<B1-Motion>",       self._on_motion,  add="+")
        canvas.bind("<ButtonRelease-1>", self._on_release, add="+")
        canvas.bind("<Control-c>",       self._on_copy)
        canvas.bind("<Control-v>",       self._on_paste)
        canvas.bind("<Control-g>",       self._on_group)
        canvas.bind("<Control-G>",       self._on_ungroup)

    # ------------------------------------------------------------------ lifecycle

    def on_page_changed(self, page_num: int):
        self._select([])

    def select(self, image_id: Optional[str]):
        """Select a single image by ID (used externally, e.g. after add/duplicate)."""
        if image_id:
            ids = self._expand_group([image_id])
            self._select(ids)
        else:
            self._select([])

    def _select(self, ids: List[str]):
        self.selected_ids = list(ids)
        self.selected_id = ids[0] if ids else None
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_id)
        self.redraw()

    # ------------------------------------------------------------------ drawing

    def redraw(self):
        canvas = self.pdf_viewer.canvas
        canvas.delete("obj_overlay")
        self._photo_refs.clear()
        self._rot_handle_canvas = None

        if not self.pdf_viewer.document:
            return
        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        if not scale or not page_h:
            return

        page_num = self.pdf_viewer.current_page
        for obj in self.manager.get_page_images(page_num):
            if obj.visible:
                self._draw_object(canvas, obj, scale, page_h)

        if self.selected_ids:
            objs = [self.manager.get_image_object(i) for i in self.selected_ids]
            bounds = _group_bounds(objs)
            if bounds:
                self._draw_selection(canvas, bounds, scale, page_h)

    def _draw_object(self, canvas, obj, scale, page_h):
        left, top    = self._pdf_to_canvas(obj.x,              obj.y + obj.height, scale, page_h)
        right, bottom = self._pdf_to_canvas(obj.x + obj.width, obj.y,              scale, page_h)
        w_px = max(1, int(round(right - left)))
        h_px = max(1, int(round(bottom - top)))

        photo = self._build_thumbnail(obj, w_px, h_px)
        if photo:
            canvas.create_image(left, top, anchor=tk.NW, image=photo, tags="obj_overlay")
            self._photo_refs[obj.id] = photo
        else:
            canvas.create_rectangle(left, top, right, bottom,
                                     outline='gray', dash=(3, 2), tags="obj_overlay")
        if obj.locked:
            canvas.create_text(left + 4, top + 4, anchor=tk.NW, text="🔒",
                                font=('Arial', 8), tags="obj_overlay")

        # Per-object selection highlight (thin dotted border when part of multi-select)
        if obj.id in self.selected_ids and len(self.selected_ids) > 1:
            canvas.create_rectangle(left, top, right, bottom,
                                     outline='#60B0FF', width=1, dash=(2, 2),
                                     tags="obj_overlay")

    def _draw_selection(self, canvas, bounds, scale, page_h):
        """Draw the unified selection box, resize handles, and rotation handle."""
        bx, by, bw, bh = bounds
        left,  top    = self._pdf_to_canvas(bx,      by + bh, scale, page_h)
        right, bottom = self._pdf_to_canvas(bx + bw, by,      scale, page_h)

        # Selection rectangle
        canvas.create_rectangle(left, top, right, bottom,
                                 outline='#0080FF', width=2, dash=(4, 2),
                                 tags="obj_overlay")

        # Resize handles
        cx = (left + right) / 2
        cy = (top + bottom) / 2
        for hx, hy in [
            (left, top), (cx, top), (right, top),
            (right, cy),
            (right, bottom), (cx, bottom), (left, bottom),
            (left, cy),
        ]:
            s = HANDLE_SIZE / 2
            canvas.create_rectangle(hx - s, hy - s, hx + s, hy + s,
                                     fill='white', outline='#0080FF', width=2,
                                     tags="obj_overlay")

        # Rotation handle: circle above top-center, connected by a line
        rcx = cx
        rcy = top - ROT_HANDLE_OFFSET
        canvas.create_line(cx, top, rcx, rcy + ROT_HANDLE_RADIUS,
                            fill='#0080FF', width=1, tags="obj_overlay")
        canvas.create_oval(rcx - ROT_HANDLE_RADIUS, rcy - ROT_HANDLE_RADIUS,
                            rcx + ROT_HANDLE_RADIUS, rcy + ROT_HANDLE_RADIUS,
                            fill='white', outline='#0080FF', width=2,
                            tags="obj_overlay")
        self._rot_handle_canvas = (rcx, rcy)

    @staticmethod
    def _build_thumbnail(obj, w_px, h_px):
        path = (obj.properties or {}).get('image_path')
        if not path or not os.path.exists(path) or w_px <= 0 or h_px <= 0:
            return None
        try:
            img = Image.open(path).convert('RGBA')
            if obj.rotation:
                # expand=True gives the full rotated image without clipping any corners.
                # Then fit within (w_px, h_px) preserving aspect ratio and center it.
                img = img.rotate(-obj.rotation, expand=True, resample=Image.BICUBIC)
                img.thumbnail((w_px, h_px), Image.Resampling.LANCZOS)
                canvas_img = Image.new('RGBA', (w_px, h_px), (0, 0, 0, 0))
                px = (w_px - img.width) // 2
                py = (h_px - img.height) // 2
                canvas_img.paste(img, (px, py), img)
                img = canvas_img
            else:
                img = img.resize((w_px, h_px), Image.Resampling.LANCZOS)
            opacity = max(0.0, min(100.0, obj.opacity))
            if opacity < 100.0:
                alpha = img.split()[3].point(lambda p: int(p * opacity / 100.0))
                img.putalpha(alpha)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    # ------------------------------------------------------------------ coordinates

    def _pdf_to_canvas(self, x, y, scale, page_h):
        off_x, off_y = self.pdf_viewer.get_render_offset()
        return (x * scale + off_x, (page_h - y) * scale + off_y)

    def _canvas_to_pdf(self, cx, cy):
        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        if not scale or not page_h:
            return (0.0, 0.0)
        off_x, off_y = self.pdf_viewer.get_render_offset()
        return ((cx - off_x) / scale, page_h - (cy - off_y) / scale)

    # ------------------------------------------------------------------ hit detection

    def _hit_resize_handle(self, cx, cy) -> Optional[str]:
        """Return resize handle name ('TL','T','TR','R','BR','B','BL','L') or None."""
        if not self.selected_ids:
            return None
        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        if not scale or not page_h:
            return None
        objs = [self.manager.get_image_object(i) for i in self.selected_ids]
        bounds = _group_bounds(objs)
        if not bounds:
            return None
        bx, by, bw, bh = bounds
        left,  top    = self._pdf_to_canvas(bx,      by + bh, scale, page_h)
        right, bottom = self._pdf_to_canvas(bx + bw, by,      scale, page_h)
        mcx = (left + right) / 2
        mcy = (top + bottom) / 2
        handle_positions = {
            'TL': (left,  top),    'T':  (mcx, top),  'TR': (right, top),
            'R':  (right, mcy),    'BR': (right, bottom),
            'B':  (mcx, bottom),   'BL': (left, bottom), 'L': (left, mcy),
        }
        for name, (hx, hy) in handle_positions.items():
            if abs(cx - hx) <= HANDLE_SIZE and abs(cy - hy) <= HANDLE_SIZE:
                return name
        return None

    def _hit_rotation_handle(self, cx, cy) -> bool:
        if self._rot_handle_canvas is None:
            return False
        rcx, rcy = self._rot_handle_canvas
        return math.hypot(cx - rcx, cy - rcy) <= ROT_HANDLE_RADIUS + 4

    def _expand_group(self, image_ids: List[str]) -> List[str]:
        """If any id belongs to a group, expand to all members of that group."""
        expanded = set(image_ids)
        for image_id in image_ids:
            gid = self.manager.get_group_id(image_id)
            if gid:
                for mid in self.manager.get_group_member_ids(gid):
                    expanded.add(mid)
        return list(expanded)

    # ------------------------------------------------------------------ mouse events

    def _on_press(self, event):
        if not self.pdf_viewer.document:
            return
        canvas = self.pdf_viewer.canvas
        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        ctrl = bool(event.state & 0x0004)

        # Rotation handle takes priority when something is selected
        if self.selected_ids and self._hit_rotation_handle(cx, cy):
            self._begin_rotate(cx, cy)
            return

        # Resize handles of current selection
        if self.selected_ids:
            ht = self._hit_resize_handle(cx, cy)
            if ht:
                self._begin_resize(cx, cy, ht)
                return

        # Hit test images on current page
        page_num = self.pdf_viewer.current_page
        images = self.manager.get_page_images(page_num)
        ids = [o.id for o in images if o.visible and not o.locked]
        px, py = self._canvas_to_pdf(cx, cy)
        hit_id = self.editor.get_hit_target(px, py, ids, self.manager)

        if hit_id:
            if ctrl:
                # Toggle group membership in selection
                group_ids = self._expand_group([hit_id])
                existing = set(self.selected_ids)
                if hit_id in existing:
                    for gid in group_ids:
                        existing.discard(gid)
                else:
                    for gid in group_ids:
                        existing.add(gid)
                self._select(list(existing))
            else:
                # Auto-expand to full group
                ids_to_select = self._expand_group([hit_id])
                self._select(ids_to_select)

            self._begin_move(cx, cy)
        else:
            if not ctrl:
                self._select([])

    def _on_motion(self, event):
        if self._mode == 'idle':
            return
        canvas = self.pdf_viewer.canvas
        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        shift = bool(event.state & 0x0001)

        if self._mode == 'move':
            self._do_move(cx, cy)
        elif self._mode == 'resize':
            self._do_resize(cx, cy, shift)
        elif self._mode == 'rotate':
            self._do_rotate(cx, cy)

        self.redraw()

    def _on_release(self, event):
        if self._mode == 'idle' or not self.selected_ids:
            self._mode = 'idle'
            return

        if self._mode == 'move':
            self._commit_move()
        elif self._mode == 'resize':
            self._commit_transform()
        elif self._mode == 'rotate':
            self._commit_rotate()

        self._mode = 'idle'
        self._initial_states.clear()
        self._initial_bounds = None
        self.redraw()

    # ------------------------------------------------------------------ begin operations

    def _snapshot_selected(self):
        snap = {}
        for image_id in self.selected_ids:
            obj = self.manager.get_image_object(image_id)
            if obj:
                snap[image_id] = _snapshot_obj(obj)
        return snap

    def _begin_move(self, cx, cy):
        self._mode = 'move'
        self._drag_start_canvas = (cx, cy)
        self._drag_start_pdf = self._canvas_to_pdf(cx, cy)
        self._initial_states = self._snapshot_selected()

    def _begin_resize(self, cx, cy, handle_type: str):
        self._mode = 'resize'
        self._resize_handle = handle_type
        self._drag_start_canvas = (cx, cy)
        self._drag_start_pdf = self._canvas_to_pdf(cx, cy)
        self._initial_states = self._snapshot_selected()
        objs = [self.manager.get_image_object(i) for i in self.selected_ids]
        self._initial_bounds = _group_bounds(objs)

    def _begin_rotate(self, cx, cy):
        self._mode = 'rotate'
        self._drag_start_canvas = (cx, cy)
        self._initial_states = self._snapshot_selected()

        # Group center in canvas coords
        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        objs = [self.manager.get_image_object(i) for i in self.selected_ids]
        bounds = _group_bounds(objs)
        if bounds:
            bx, by, bw, bh = bounds
            gcx_pdf = bx + bw / 2
            gcy_pdf = by + bh / 2
            self._rotate_center_canvas = self._pdf_to_canvas(gcx_pdf, gcy_pdf, scale, page_h)
        else:
            self._rotate_center_canvas = (cx, cy)

        gcx, gcy = self._rotate_center_canvas
        self._rotate_start_angle = math.atan2(cy - gcy, cx - gcx)

    # ------------------------------------------------------------------ live operations

    def _do_move(self, cx, cy):
        scx, scy = self._drag_start_canvas
        dx_canvas = cx - scx
        dy_canvas = cy - scy
        scale = self.pdf_viewer.get_page_to_screen_scale()
        if not scale:
            return
        dx_pdf = dx_canvas / scale
        dy_pdf = -dy_canvas / scale   # canvas y down → PDF y up
        for image_id, snap in self._initial_states.items():
            self.manager.set_image_position(
                image_id, snap['x'] + dx_pdf, snap['y'] + dy_pdf)

    def _do_resize(self, cx, cy, shift_locked: bool):
        if not self._initial_bounds:
            return
        bx0, by0, bw0, bh0 = self._initial_bounds
        scale = self.pdf_viewer.get_page_to_screen_scale()
        if not scale:
            return

        # Current mouse in PDF coords
        mpx, mpy = self._canvas_to_pdf(cx, cy)
        # Start mouse in PDF coords
        spx, spy = self._drag_start_pdf
        dx = mpx - spx
        dy = mpy - spy   # PDF coords: positive = up

        ht = self._resize_handle
        new_x, new_y = bx0, by0
        new_w, new_h = bw0, bh0

        # Compute new bounds from handle type
        if 'L' in ht:
            new_x = bx0 + dx
            new_w = bw0 - dx
        elif 'R' in ht:
            new_w = bw0 + dx

        if 'T' in ht:
            # top handle: in PDF coords, top = by+bh; dragging up = larger y = larger height
            new_y = by0 + dy
            new_h = bh0 - dy
        elif 'B' in ht:
            # bottom handle: dragging down = smaller y = larger height
            new_h = bh0 + dy

        new_w = max(MIN_OBJ_SIZE, new_w)
        new_h = max(MIN_OBJ_SIZE, new_h)

        # Shift → aspect ratio lock
        if shift_locked and bw0 > 0 and bh0 > 0:
            ar = bw0 / bh0
            if ht in ('TL', 'TR', 'BR', 'BL'):
                sw = new_w / bw0
                sh = new_h / bh0
                s = (sw + sh) / 2.0
                new_w = max(MIN_OBJ_SIZE, bw0 * s)
                new_h = max(MIN_OBJ_SIZE, bh0 * s)
                # Recompute anchor-side position
                if 'L' in ht:
                    new_x = (bx0 + bw0) - new_w
                if 'T' in ht:
                    new_y = (by0 + bh0) - new_h
            elif ht in ('L', 'R'):
                new_h = new_w / ar
            elif ht in ('T', 'B'):
                new_w = new_h * ar

        if new_w <= 0 or new_h <= 0:
            return

        sx = new_w / bw0 if bw0 > 0 else 1.0
        sy = new_h / bh0 if bh0 > 0 else 1.0

        # Anchor point (opposite corner/edge) in PDF coords
        ax = bx0 if 'R' in ht else bx0 + bw0
        ay = by0 if 'T' in ht else by0 + bh0

        for image_id, snap in self._initial_states.items():
            ox, oy, ow, oh = snap['x'], snap['y'], snap['width'], snap['height']
            t_x = ax + (ox - ax) * sx
            t_y = ay + (oy - ay) * sy
            t_w = max(MIN_OBJ_SIZE, ow * sx)
            t_h = max(MIN_OBJ_SIZE, oh * sy)
            self.manager.set_image_position(image_id, t_x, t_y)
            self.manager.set_image_size(image_id, t_w, t_h)

    def _do_rotate(self, cx, cy):
        gcx, gcy = self._rotate_center_canvas
        cur_angle = math.atan2(cy - gcy, cx - gcx)
        delta_canvas = cur_angle - self._rotate_start_angle  # radians, clockwise in canvas

        # Canvas: y-down → clockwise delta → increase rotation value (clockwise in PDF display)
        delta_deg = math.degrees(delta_canvas)

        # PDF math convention (y-up): clockwise canvas = counterclockwise PDF
        delta_pdf_math = -delta_deg

        cos_d = math.cos(math.radians(delta_pdf_math))
        sin_d = math.sin(math.radians(delta_pdf_math))

        # Group center in PDF coords
        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        if not scale or not page_h:
            return
        off_x, off_y = self.pdf_viewer.get_render_offset()
        gcx_pdf = (gcx - off_x) / scale
        gcy_pdf = page_h - (gcy - off_y) / scale

        for image_id, snap in self._initial_states.items():
            ox, oy, ow, oh = snap['x'], snap['y'], snap['width'], snap['height']
            ocx = ox + ow / 2 - gcx_pdf
            ocy = oy + oh / 2 - gcy_pdf
            new_cx = gcx_pdf + ocx * cos_d - ocy * sin_d
            new_cy = gcy_pdf + ocx * sin_d + ocy * cos_d
            new_x = new_cx - ow / 2
            new_y = new_cy - oh / 2
            new_rot = (snap['rotation'] + delta_deg) % 360
            self.manager.set_image_position(image_id, new_x, new_y)
            self.manager.set_image_property(image_id, 'rotation', new_rot)

    # ------------------------------------------------------------------ commit to undo stack

    def _commit_move(self):
        moves = {}
        for image_id, snap in self._initial_states.items():
            obj = self.manager.get_image_object(image_id)
            if obj and (snap['x'], snap['y']) != (obj.x, obj.y):
                moves[image_id] = (snap['x'], snap['y'], obj.x, obj.y)
        if not moves:
            return
        if len(moves) == 1:
            image_id = next(iter(moves))
            fx, fy, tx, ty = moves[image_id]
            self.undo_manager.execute(MoveObjectCommand(self.manager, image_id, fx, fy, tx, ty))
        else:
            self.undo_manager.execute(MoveManyCommand(self.manager, moves))

    def _commit_transform(self):
        before, after = {}, {}
        for image_id, snap in self._initial_states.items():
            obj = self.manager.get_image_object(image_id)
            if not obj:
                continue
            b = (snap['x'], snap['y'], snap['width'], snap['height'])
            a = (obj.x, obj.y, obj.width, obj.height)
            if b != a:
                before[image_id] = b
                after[image_id] = a
        if not before:
            return
        if len(before) == 1:
            image_id = next(iter(before))
            bx, by, bw, bh = before[image_id]
            ax, ay, aw, ah = after[image_id]
            self.undo_manager.execute(ResizeObjectCommand(
                self.manager, image_id, bx, by, bw, bh, ax, ay, aw, ah))
        else:
            self.undo_manager.execute(TransformManyCommand(self.manager, before, after))

    def _commit_rotate(self):
        before, after = {}, {}
        for image_id, snap in self._initial_states.items():
            obj = self.manager.get_image_object(image_id)
            if not obj:
                continue
            b = (snap['x'], snap['y'], snap['width'], snap['height'], snap['rotation'])
            a = (obj.x, obj.y, obj.width, obj.height, obj.rotation)
            if b != a:
                before[image_id] = b
                after[image_id] = a
        if not before:
            return
        self.undo_manager.execute(RotateManyCommand(self.manager, before, after))

    # ------------------------------------------------------------------ copy / paste

    def _on_copy(self, event=None):
        if not self.selected_ids:
            return
        self._clipboard = []
        for image_id in self.selected_ids:
            obj = self.manager.get_image_object(image_id)
            if obj:
                self._clipboard.append(_snapshot_obj(obj))

    def _on_paste(self, event=None):
        if not self._clipboard or not self.pdf_viewer.document:
            return
        page_num = self.pdf_viewer.current_page
        # Offset pasted copies so they're visually distinguishable
        shifted = []
        for snap in self._clipboard:
            s = dict(snap)
            s['x'] = s['x'] + PASTE_OFFSET
            s['y'] = s['y'] - PASTE_OFFSET
            shifted.append(s)
        cmd = PasteObjectsCommand(self.manager, page_num, shifted)
        self.undo_manager.execute(cmd)
        # Select the newly pasted objects
        if cmd.added_ids:
            self._select(cmd.added_ids)
        self.redraw()

    # ------------------------------------------------------------------ group / ungroup

    def _on_group(self, event=None):
        if len(self.selected_ids) < 2:
            return
        import uuid
        new_gid = str(uuid.uuid4())
        cmd = GroupCommand(self.manager, self.selected_ids, new_gid)
        self.undo_manager.execute(cmd)
        self.redraw()

    def _on_ungroup(self, event=None):
        if not self.selected_ids:
            return
        cmd = GroupCommand(self.manager, self.selected_ids, None)
        self.undo_manager.execute(cmd)
        self.redraw()

    # ------------------------------------------------------------------ static helper

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
            entry.bind('<Return>',   lambda e, k=key: self._apply_field(k))
            entry.bind('<FocusOut>', lambda e, k=key: self._apply_field(k))
            self.vars[key] = var

        row = len(self.FIELDS)
        self.lock_aspect_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.body, text="Lock aspect ratio",
                        variable=self.lock_aspect_var).grid(
            row=row, column=0, columnspan=2, sticky='w')

        self.locked_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.body, text="Locked", variable=self.locked_var,
                        command=self._apply_locked).grid(
            row=row + 1, column=0, columnspan=2, sticky='w')

        btns = tk.Frame(self.body)
        btns.grid(row=row + 2, column=0, columnspan=2, pady=6)
        tk.Button(btns, text="Duplicate", command=self._duplicate).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text="Delete",    command=self._delete,
                  bg='salmon').pack(side=tk.LEFT, padx=2)

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
            width=obj.width, height=obj.height,
            rotation=obj.rotation, opacity=obj.opacity, z_index=obj.z_index + 1,
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
