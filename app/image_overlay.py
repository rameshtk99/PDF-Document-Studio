"""
Interactive image layer on the PDF canvas: select, move, resize, rotate,
group, copy/paste, duplicate-drag.

PageObject x/y are PDF points (origin bottom-left); canvas pixels are
top-left. `_pdf_to_canvas` / `_canvas_to_pdf` convert between them.
Rotation and bounding-box math lives in utils.geometry, shared with
pdf/pdf_handler.py so the selection box, preview and export agree.

Ctrl+G/Ctrl+Shift+G/Ctrl+C/Ctrl+V and Delete are bound globally in
editor_window.py, not here, so focus never matters.
"""

import math
import os
import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from utils import ui_theme
from utils.widgets import create_button
from app.image_editor import ImageEditor, SelectionBox
from app.undo_redo import UndoRedoManager
from app.document_commands import (
    MoveObjectCommand, ResizeObjectCommand, ChangeObjectPropertyCommand,
    AddObjectCommand, DeleteObjectCommand, DeleteManyCommand,
    GroupCommand, MoveManyCommand, TransformManyCommand,
    RotateManyCommand, PasteObjectsCommand, ChangeZIndexManyCommand,
)
from pdf.image_manager import ImageManager, ImagePlacement
from utils import geometry as geo

HANDLE_SIZE = 8          # half-size of a resize handle in pixels
ROT_HANDLE_OFFSET = 28   # pixels above selection box top-center
ROT_HANDLE_RADIUS = 7    # pixel radius of the rotation handle circle
MIN_OBJ_SIZE = 5.0       # minimum PDF-point dimension after resize
PASTE_OFFSET = 15.0      # PDF-point offset for pasted copies


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

        # Set only during a Ctrl+Shift+drag, so _commit_move() can patch
        # that command instead of pushing a second one -- one gesture,
        # one undo step.
        self._duplicate_drag_cmd: Optional[PasteObjectsCommand] = None

        # Resize/rotate operate in the selection's own (possibly rotated)
        # local frame -- these are captured at drag-start by
        # _selection_geometry() so every intermediate frame reuses them.
        self._resize_angle: float = 0.0
        self._resize_local_bbox0: Optional[Tuple[float, float, float, float]] = None
        self._resize_local_start: Tuple[float, float] = (0.0, 0.0)
        self._rotate_center_canvas: Tuple[float, float] = (0.0, 0.0)
        self._rotate_start_angle: float = 0.0        # canvas angle at drag start

        # Cached canvas-space handle positions, refreshed every redraw() so
        # hit-testing always matches what's actually on screen.
        self._rot_handle_canvas: Optional[Tuple[float, float]] = None
        self._handle_canvas_positions: Dict[str, Tuple[float, float]] = {}

        canvas = self.pdf_viewer.canvas
        canvas.bind("<Button-1>",        self._on_press,   add="+")
        canvas.bind("<B1-Motion>",       self._on_motion,  add="+")
        canvas.bind("<ButtonRelease-1>", self._on_release, add="+")
        canvas.bind("<Button-3>",        self._on_right_click, add="+")
        # Ctrl+C/V/G are bound globally in editor_window; binding them
        # here too would fire each one twice.

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
        self._handle_canvas_positions = {}

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
            self._draw_selection(canvas, scale, page_h)

    def _draw_object(self, canvas, obj, scale, page_h):
        corners_world = geo.object_corners_world(obj.x, obj.y, obj.width, obj.height, obj.rotation)
        corners_canvas = [self._pdf_to_canvas(x, y, scale, page_h) for (x, y) in corners_world]
        tl_c = corners_canvas[3]

        photo = self._build_thumbnail(obj, scale)
        if photo:
            cx_world, cy_world = geo.object_center(obj.x, obj.y, obj.width, obj.height)
            ccx, ccy = self._pdf_to_canvas(cx_world, cy_world, scale, page_h)
            canvas.create_image(ccx, ccy, anchor=tk.CENTER, image=photo, tags="obj_overlay")
            self._photo_refs[obj.id] = photo
        else:
            flat = [c for pt in corners_canvas for c in pt]
            canvas.create_polygon(*flat, outline='gray', dash=(3, 2), fill='',
                                   tags="obj_overlay")
        if obj.locked:
            canvas.create_text(tl_c[0] + 4, tl_c[1] + 4, anchor=tk.NW, text="\U0001F512",
                                font=('Arial', 8), tags="obj_overlay")

        # Per-object selection highlight (thin dotted border when part of multi-select)
        if obj.id in self.selected_ids and len(self.selected_ids) > 1:
            flat = [c for pt in corners_canvas for c in pt]
            canvas.create_polygon(*flat, outline='#60B0FF', width=1, dash=(2, 2), fill='',
                                   tags="obj_overlay")

    def _selected_objs_tuples(self) -> List[Tuple[float, float, float, float, float]]:
        objs = []
        for image_id in self.selected_ids:
            obj = self.manager.get_image_object(image_id)
            if obj:
                objs.append((obj.x, obj.y, obj.width, obj.height, obj.rotation))
        return objs

    def _selection_geometry(self):
        """(angle, local_bbox, corners_world, handle_world) for the current
        selection, or None if nothing is selected. `angle` is the selection's
        shared rotation (0.0 if the selected objects don't all share one)."""
        objs = self._selected_objs_tuples()
        if not objs:
            return None
        angle, local_bbox, corners_world = geo.group_frame(objs)
        bl, br, tr, tl = corners_world
        mid = lambda a, b: ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        handle_world = {
            'TL': tl, 'T': mid(tl, tr), 'TR': tr,
            'R': mid(tr, br), 'BR': br,
            'B': mid(bl, br), 'BL': bl, 'L': mid(tl, bl),
        }
        return angle, local_bbox, corners_world, handle_world

    def _draw_selection(self, canvas, scale, page_h):
        """Draw the (possibly rotated) selection box, resize handles, and
        rotation handle -- a true rotated polygon, not always axis-aligned."""
        geom = self._selection_geometry()
        if not geom:
            return
        angle, _local_bbox, corners_world, handle_world = geom

        corners_canvas = [self._pdf_to_canvas(x, y, scale, page_h) for (x, y) in corners_world]
        flat = [c for pt in corners_canvas for c in pt]
        canvas.create_polygon(*flat, outline='#0080FF', width=2, dash=(4, 2), fill='',
                               tags="obj_overlay")

        handle_canvas = {name: self._pdf_to_canvas(x, y, scale, page_h)
                          for name, (x, y) in handle_world.items()}
        self._handle_canvas_positions = handle_canvas
        for hx, hy in handle_canvas.values():
            s = HANDLE_SIZE / 2
            canvas.create_rectangle(hx - s, hy - s, hx + s, hy + s,
                                     fill='white', outline='#0080FF', width=2,
                                     tags="obj_overlay")

        # Rotation handle: offset from top-center, along the box's own
        # (rotated) "up" direction so it visually rotates with the box.
        tl_c, bl_c, t_c = handle_canvas['TL'], handle_canvas['BL'], handle_canvas['T']
        up_x, up_y = tl_c[0] - bl_c[0], tl_c[1] - bl_c[1]
        up_len = math.hypot(up_x, up_y) or 1.0
        up_x, up_y = up_x / up_len, up_y / up_len
        rcx = t_c[0] + up_x * ROT_HANDLE_OFFSET
        rcy = t_c[1] + up_y * ROT_HANDLE_OFFSET
        canvas.create_line(t_c[0], t_c[1], rcx, rcy, fill='#0080FF', width=1, tags="obj_overlay")
        canvas.create_oval(rcx - ROT_HANDLE_RADIUS, rcy - ROT_HANDLE_RADIUS,
                            rcx + ROT_HANDLE_RADIUS, rcy + ROT_HANDLE_RADIUS,
                            fill='white', outline='#0080FF', width=2,
                            tags="obj_overlay")
        self._rot_handle_canvas = (rcx, rcy)

    @staticmethod
    def _build_thumbnail(obj, scale):
        """Build the on-canvas preview bitmap for `obj`.

        Resizes the source image to its true LOCAL (un-rotated) pixel size
        first, then -- only if rotated -- rotates with expand=True, which
        enlarges the canvas to fit the full rotated image losslessly.
        There is deliberately no "fit the rotated result back into the
        original box" step: that shrink-to-fit was the bug. The caller
        places the returned bitmap centered on the object's center, so its
        (now larger) rotated footprint is what actually appears on screen,
        matching pdf/pdf_handler.py's export rendering exactly.
        """
        path = (obj.properties or {}).get('image_path')
        if not path or not os.path.exists(path):
            return None
        w_px = max(1, int(round(obj.width * scale)))
        h_px = max(1, int(round(obj.height * scale)))
        try:
            img = Image.open(path).convert('RGBA')
            img = img.resize((w_px, h_px), Image.Resampling.LANCZOS)
            if obj.rotation:
                img = img.rotate(-obj.rotation, expand=True, resample=Image.BICUBIC)
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
        if not self.selected_ids or not self._handle_canvas_positions:
            return None
        for name, (hx, hy) in self._handle_canvas_positions.items():
            if abs(cx - hx) <= HANDLE_SIZE and abs(cy - hy) <= HANDLE_SIZE:
                return name
        return None

    def _hit_rotation_handle(self, cx, cy) -> bool:
        if self._rot_handle_canvas is None:
            return False
        rcx, rcy = self._rot_handle_canvas
        return math.hypot(cx - rcx, cy - rcy) <= ROT_HANDLE_RADIUS + 4

    def _hit_object(self, px, py) -> Optional[str]:
        page_num = self.pdf_viewer.current_page
        images = self.manager.get_page_images(page_num)
        ids = [o.id for o in images if o.visible and not o.locked]
        return self.editor.get_hit_target(px, py, ids, self.manager)

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
        shift = bool(event.state & 0x0001)

        # Any earlier Ctrl+Shift+drag is fully resolved by the time a new
        # press starts (either consumed by _commit_move or never fired) --
        # reset defensively so a stray value never leaks into an unrelated
        # plain move.
        self._duplicate_drag_cmd = None

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
        px, py = self._canvas_to_pdf(cx, cy)
        hit_id = self._hit_object(px, py)

        if hit_id:
            if ctrl and shift:
                # Ctrl+Shift+drag: duplicate the (auto-expanded) selection
                # and drag the duplicate; the original never moves.
                target_ids = self._expand_group([hit_id])
                if not (set(target_ids) & set(self.selected_ids)):
                    self._select(target_ids)
                self._begin_duplicate_drag(cx, cy)
                return

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
        self._resize_local_bbox0 = None
        self.redraw()

    def _on_right_click(self, event):
        if not self.pdf_viewer.document:
            self._show_context_menu(event)
            return
        canvas = self.pdf_viewer.canvas
        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        px, py = self._canvas_to_pdf(cx, cy)
        hit_id = self._hit_object(px, py)

        if hit_id and hit_id not in self.selected_ids:
            self._select(self._expand_group([hit_id]))
        elif not hit_id and not self.selected_ids:
            # Truly empty canvas, nothing selected -- leave selection as-is
            # (empty) so the menu just offers Paste.
            pass

        self._show_context_menu(event)

    def _show_context_menu(self, event):
        has_sel = bool(self.selected_ids)
        has_clip = bool(self._clipboard)
        can_group = len(self.selected_ids) >= 2
        can_ungroup = any(self.manager.get_group_id(i) for i in self.selected_ids)

        menu = tk.Menu(self.pdf_viewer.canvas, tearoff=0)
        menu.add_command(label="Copy", command=self._on_copy,
                          state=tk.NORMAL if has_sel else tk.DISABLED)
        menu.add_command(label="Paste", command=self._on_paste,
                          state=tk.NORMAL if has_clip else tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Group", command=self._on_group,
                          state=tk.NORMAL if can_group else tk.DISABLED)
        menu.add_command(label="Ungroup", command=self._on_ungroup,
                          state=tk.NORMAL if can_ungroup else tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Bring to Front", command=self._bring_selection_to_front,
                          state=tk.NORMAL if has_sel else tk.DISABLED)
        menu.add_command(label="Send to Back", command=self._send_selection_to_back,
                          state=tk.NORMAL if has_sel else tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Delete", command=self.delete_selection,
                          state=tk.NORMAL if has_sel else tk.DISABLED)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

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

    def _begin_duplicate_drag(self, cx, cy):
        """Create an undoable duplicate of the current selection (retaining
        position/size/rotation/opacity/image/group), select the duplicate,
        and start moving it -- the originals are never touched."""
        if not self.selected_ids or not self.pdf_viewer.document:
            return
        page_num = self.pdf_viewer.current_page
        snapshots = []
        for image_id in self.selected_ids:
            obj = self.manager.get_image_object(image_id)
            if obj:
                snapshots.append(_snapshot_obj(obj))
        if not snapshots:
            return
        cmd = PasteObjectsCommand(self.manager, page_num, snapshots)
        self.undo_manager.execute(cmd)
        if not cmd.added_ids:
            return
        self._select(cmd.added_ids)
        self._begin_move(cx, cy)
        self._duplicate_drag_cmd = cmd

    def _begin_resize(self, cx, cy, handle_type: str):
        self._mode = 'resize'
        self._resize_handle = handle_type
        self._drag_start_canvas = (cx, cy)
        self._drag_start_pdf = self._canvas_to_pdf(cx, cy)
        self._initial_states = self._snapshot_selected()

        geom = self._selection_geometry()
        angle = geom[0] if geom else 0.0
        local_bbox = geom[1] if geom else None
        self._resize_angle = angle
        self._resize_local_bbox0 = local_bbox
        self._resize_local_start = geo.world_to_frame(
            self._drag_start_pdf[0], self._drag_start_pdf[1], angle)

    def _begin_rotate(self, cx, cy):
        self._mode = 'rotate'
        self._drag_start_canvas = (cx, cy)
        self._initial_states = self._snapshot_selected()

        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        geom = self._selection_geometry()
        if geom and scale and page_h:
            angle, local_bbox, _corners, _handles = geom
            lx0, ly0, lx1, ly1 = local_bbox
            lcx, lcy = (lx0 + lx1) / 2.0, (ly0 + ly1) / 2.0
            pivot_world = geo.frame_to_world(lcx, lcy, angle)
            self._rotate_center_canvas = self._pdf_to_canvas(
                pivot_world[0], pivot_world[1], scale, page_h)
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
        dy_pdf = -dy_canvas / scale   # canvas y down -> PDF y up
        for image_id, snap in self._initial_states.items():
            self.manager.set_image_position(
                image_id, snap['x'] + dx_pdf, snap['y'] + dy_pdf)

    def _do_resize(self, cx, cy, shift_locked: bool):
        if self._resize_local_bbox0 is None:
            return

        mpx, mpy = self._canvas_to_pdf(cx, cy)
        lx, ly = geo.world_to_frame(mpx, mpy, self._resize_angle)
        slx, sly = self._resize_local_start
        dx_local = lx - slx
        dy_local = ly - sly

        snapshots = {image_id: (s['x'], s['y'], s['width'], s['height'])
                     for image_id, s in self._initial_states.items()}
        results = geo.resize_in_frame(
            snapshots, self._resize_angle, self._resize_local_bbox0,
            self._resize_handle, dx_local, dy_local, shift_locked, MIN_OBJ_SIZE)

        for image_id, (nx, ny, nw, nh) in results.items():
            self.manager.set_image_position(image_id, nx, ny)
            self.manager.set_image_size(image_id, nw, nh)

    def _do_rotate(self, cx, cy):
        gcx, gcy = self._rotate_center_canvas
        cur_angle = math.atan2(cy - gcy, cx - gcx)
        delta_canvas = cur_angle - self._rotate_start_angle  # radians, clockwise in canvas

        # Canvas: y-down -> clockwise delta -> increase rotation value (clockwise in PDF display)
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

        if self._duplicate_drag_cmd is not None:
            # Ctrl+Shift+drag: patch the existing PasteObjectsCommand's
            # snapshots instead of pushing a second Move, so the whole
            # duplicate-and-drag gesture is one undo step.
            cmd = self._duplicate_drag_cmd
            self._duplicate_drag_cmd = None
            if moves:
                id_to_snap = dict(zip(cmd.added_ids, cmd.snapshots))
                for image_id in moves:
                    snap = id_to_snap.get(image_id)
                    obj = self.manager.get_image_object(image_id)
                    if snap is not None and obj:
                        snap['x'] = obj.x
                        snap['y'] = obj.y
            return

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

    # ------------------------------------------------------------------ delete / z-order

    def delete_selection(self):
        """Delete every currently-selected object as a single undo step."""
        if not self.selected_ids or not self.pdf_viewer.document:
            return
        page_num = self.pdf_viewer.current_page
        objs = [self.manager.get_image_object(i) for i in self.selected_ids]
        objs = [o for o in objs if o]
        if not objs:
            return
        cmd = DeleteManyCommand(self.manager, page_num, objs)
        self.undo_manager.execute(cmd)
        self._select([])

    def _bring_selection_to_front(self):
        if not self.selected_ids or not self.pdf_viewer.document:
            return
        page_num = self.pdf_viewer.current_page
        page_images = self.manager.get_page_images(page_num)
        if not page_images:
            return
        max_z = max(o.z_index for o in page_images)
        selected_sorted = sorted(
            (o for o in (self.manager.get_image_object(i) for i in self.selected_ids) if o),
            key=lambda o: o.z_index)
        changes = {}
        next_z = max_z + 1
        for obj in selected_sorted:
            changes[obj.id] = (obj.z_index, next_z)
            next_z += 1
        if changes:
            self.undo_manager.execute(ChangeZIndexManyCommand(self.manager, changes))
            self.redraw()

    def _send_selection_to_back(self):
        if not self.selected_ids or not self.pdf_viewer.document:
            return
        page_num = self.pdf_viewer.current_page
        page_images = self.manager.get_page_images(page_num)
        if not page_images:
            return
        selected_set = set(self.selected_ids)
        others = [o for o in page_images if o.id not in selected_set]
        selected_sorted = sorted(
            (o for o in (self.manager.get_image_object(i) for i in self.selected_ids) if o),
            key=lambda o: o.z_index)
        changes = {}
        next_z = 0
        for obj in selected_sorted:
            changes[obj.id] = (obj.z_index, next_z)
            next_z += 1
        for obj in others:
            changes[obj.id] = (obj.z_index, next_z)
            next_z += 1
        if changes:
            self.undo_manager.execute(ChangeZIndexManyCommand(self.manager, changes))
            self.redraw()


class ImagePropertiesPanel(ctk.CTkFrame):
    """Numeric X/Y/Width/Height/Rotation/Opacity editor for the currently
    selected image object, plus Lock/Delete/Duplicate.
    """

    FIELDS = [('x', 'X'), ('y', 'Y'), ('width', 'Width'), ('height', 'Height'),
              ('rotation', 'Rotation'), ('opacity', 'Opacity')]

    def __init__(self, parent, undo_manager: UndoRedoManager,
                 on_applied: Optional[Callable] = None,
                 on_selection_changed: Optional[Callable[[Optional[str]], None]] = None,
                 **kwargs):
        kwargs.setdefault('fg_color', ui_theme.BG_APP)
        kwargs.setdefault('corner_radius', 0)
        # CTkFrame defaults to height=200; with no packed children
        # (collapsed state) nothing shrink-wraps it, so it would reserve
        # 200px while "hidden".
        kwargs.setdefault('height', 1)
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
        # Nothing here is packed yet -- set_enabled() controls visibility.
        # This whole panel takes essentially zero space until an image is
        # actually selected, instead of permanently reserving a slot in
        # the side panel for a "nothing selected" placeholder.
        self.divider = ctk.CTkFrame(self, height=1, fg_color=ui_theme.BORDER, corner_radius=0)
        self.header = ctk.CTkFrame(self, fg_color=ui_theme.BG_SURFACE, corner_radius=0)
        ctk.CTkLabel(self.header, text="Image Properties", font=ui_theme.font(11, "bold"),
                     text_color=ui_theme.TEXT_PRIMARY).pack(side=tk.LEFT, padx=8, pady=4)

        self.content_area = ctk.CTkFrame(self, fg_color="transparent")

        # Two fields per row (X/Y, Width/Height, Rotation/Opacity) instead
        # of one long vertical stack -- halves the height this form needs
        # without cramming any single field.
        self.body = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.body.columnconfigure(1, weight=1)
        self.body.columnconfigure(3, weight=1)

        field_pairs = [self.FIELDS[i:i + 2] for i in range(0, len(self.FIELDS), 2)]
        for row, pair in enumerate(field_pairs):
            for slot, (key, label) in enumerate(pair):
                col = slot * 2
                ctk.CTkLabel(self.body, text=label, font=ui_theme.font(11),
                             text_color=ui_theme.TEXT_SECONDARY, anchor='w'
                             ).grid(row=row, column=col, sticky='w', pady=3, padx=(0 if col == 0 else 10, 6))
                var = tk.StringVar()
                entry = ctk.CTkEntry(self.body, textvariable=var, height=26,
                                      corner_radius=ui_theme.RADIUS_SM, border_color=ui_theme.BORDER,
                                      fg_color=ui_theme.BG_SUBTLE, font=ui_theme.font(11))
                entry.grid(row=row, column=col + 1, sticky='ew', pady=3)
                entry.bind('<Return>',   lambda e, k=key: self._apply_field(k))
                entry.bind('<FocusOut>', lambda e, k=key: self._apply_field(k))
                self.vars[key] = var

        row = len(field_pairs)
        self.lock_aspect_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.body, text="Lock aspect ratio", variable=self.lock_aspect_var,
                         font=ui_theme.font(11), fg_color=ui_theme.ACCENT,
                         hover_color=ui_theme.ACCENT_HOVER, checkbox_width=16, checkbox_height=16
                         ).grid(row=row, column=0, columnspan=2, sticky='w', pady=(6, 2))

        self.locked_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.body, text="Locked", variable=self.locked_var,
                         command=self._apply_locked, font=ui_theme.font(11),
                         fg_color=ui_theme.ACCENT, hover_color=ui_theme.ACCENT_HOVER,
                         checkbox_width=16, checkbox_height=16
                         ).grid(row=row, column=2, columnspan=2, sticky='w', pady=(6, 2))

        btns = ctk.CTkFrame(self.body, fg_color="transparent")
        btns.grid(row=row + 1, column=0, columnspan=4, pady=(8, 0), sticky='ew')
        create_button(btns, text="Duplicate", icon="duplicate", command=self._duplicate,
                      variant="secondary", height=28).pack(side=tk.LEFT, padx=(0, 6))
        create_button(btns, text="Delete", icon="delete", command=self._delete,
                      variant="destructive", height=28).pack(side=tk.LEFT)

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
        """Show or fully collapse this panel -- with nothing selected it
        takes ~0 space (not a permanently-reserved "nothing selected"
        block), so Quick Footer/Tools above it get that room back until
        there's actually something to show properties for."""
        if enabled:
            self.divider.pack(side=tk.TOP, fill=tk.X)
            self.header.pack(side=tk.TOP, fill=tk.X)
            self.content_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.body.pack(fill=tk.BOTH, expand=True, padx=ui_theme.PAD, pady=ui_theme.PAD)
        else:
            self.body.pack_forget()
            self.content_area.pack_forget()
            self.header.pack_forget()
            self.divider.pack_forget()
            # Unpacking every child isn't enough to shrink the frame back:
            # with no slaves left, pack propagation has nothing to measure
            # and the frame just keeps whatever height it last grew to,
            # leaving a dead band where the panel used to be. Ask for the
            # collapsed height explicitly.
            self.configure(height=1)

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
