"""
Shared rotation / bounding-box geometry for image objects.

Used by BOTH the interactive canvas overlay (app/image_overlay.py) and the
PDF export/print renderer (pdf/pdf_handler.py) so the two never drift apart
-- whatever shape gets drawn on screen is exactly what ends up in the PDF.

Coordinate convention: PDF points, origin bottom-left, y increasing upward
(matches PageObject / models.PageObject). `rotation` is degrees, CLOCKWISE
as the page is normally viewed/printed (matches PageObject's own docstring).

All positions are expressed as (x, y, width, height, rotation) where
(x, y) is the object's LOCAL, UN-ROTATED bottom-left corner and
(width, height) is its LOCAL, UN-ROTATED size. Rotation is applied about
the rectangle's own center. This is the one and only place that maps that
local rectangle to world-space corners / bounding boxes -- nothing else in
the codebase should re-derive this math.
"""

import math
from typing import Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]

ANGLE_EPS = 1e-6


def rotate_cw(ox: float, oy: float, angle_deg: float) -> Point:
    """Rotate an (ox, oy) offset/point about the origin by `angle_deg`
    clockwise, as the point would appear to a viewer looking at the
    normally-oriented (y-up) page. This is the single rotation primitive
    every other helper in this module is built from.
    """
    if not angle_deg:
        return (ox, oy)
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    return (ox * c + oy * s, -ox * s + oy * c)


def object_center(x: float, y: float, width: float, height: float) -> Point:
    return (x + width / 2.0, y + height / 2.0)


def object_corners_world(x: float, y: float, width: float, height: float,
                          rotation: float) -> List[Point]:
    """World-space corners of the object's rotated rectangle, in order
    bottom-left, bottom-right, top-right, top-left.
    """
    cx, cy = object_center(x, y, width, height)
    half_w, half_h = width / 2.0, height / 2.0
    local_offsets = [(-half_w, -half_h), (half_w, -half_h),
                      (half_w, half_h), (-half_w, half_h)]
    corners = []
    for ox, oy in local_offsets:
        rx, ry = rotate_cw(ox, oy, rotation)
        corners.append((cx + rx, cy + ry))
    return corners


def rotated_bbox_size(width: float, height: float, rotation: float) -> Tuple[float, float]:
    """Axis-aligned bounding box size of a width x height rectangle after
    rotating it by `rotation` degrees about its center. Used to size the
    rasterized (expand=True) rotated image -- never to shrink it.
    """
    theta = math.radians(rotation)
    c, s = abs(math.cos(theta)), abs(math.sin(theta))
    return (width * c + height * s, width * s + height * c)


def point_in_object(px: float, py: float, x: float, y: float,
                     width: float, height: float, rotation: float,
                     tolerance: float = 0.0) -> bool:
    """True if world point (px, py) lies within the object's rotated rect."""
    cx, cy = object_center(x, y, width, height)
    lx, ly = rotate_cw(px - cx, py - cy, -rotation)
    return (abs(lx) <= width / 2.0 + tolerance and
            abs(ly) <= height / 2.0 + tolerance)


def world_to_frame(px: float, py: float, angle_deg: float) -> Point:
    """Rotate a world point into a frame that has been counter-rotated by
    `angle_deg` about the origin (i.e. un-rotate by angle_deg)."""
    return rotate_cw(px, py, -angle_deg)


def frame_to_world(fx: float, fy: float, angle_deg: float) -> Point:
    """Inverse of world_to_frame."""
    return rotate_cw(fx, fy, angle_deg)


def object_local_rect_in_frame(x: float, y: float, width: float, height: float,
                                rotation: float, angle_deg: float) -> Tuple[float, float, float, float]:
    """Represent this object's rectangle inside a common group frame that
    has been un-rotated by `angle_deg` about the origin.

    Only exact (produces a true axis-aligned rect in that frame) when the
    object's own rotation equals angle_deg -- callers must only use this
    for objects that share a uniform rotation (see group_rotation_angle).

    Returns (local_x, local_y, local_w, local_h) -- bottom-left + size.
    """
    cx, cy = object_center(x, y, width, height)
    lcx, lcy = world_to_frame(cx, cy, angle_deg)
    return (lcx - width / 2.0, lcy - height / 2.0, width, height)


def group_rotation_angle(rotations: Iterable[float]) -> Optional[float]:
    """Common rotation angle shared by every object, or None if they differ."""
    rotations = list(rotations)
    if not rotations:
        return None
    first = rotations[0] % 360.0
    for r in rotations[1:]:
        diff = abs((r % 360.0) - first)
        diff = min(diff, 360.0 - diff)
        if diff > ANGLE_EPS:
            return None
    return first


def group_frame(objs: Sequence[Tuple[float, float, float, float, float]]):
    """objs: sequence of (x, y, width, height, rotation) tuples (world,
    local/un-rotated rect + own rotation).

    Returns (angle, local_bbox, corners_world):
      angle       -- the common rotation if uniform, else 0.0
      local_bbox  -- (lx0, ly0, lx1, ly1) union bbox in the group's local frame
      corners_world -- 4 world-space corners of the (possibly rotated)
                       selection rectangle, in BL, BR, TR, TL order
    """
    angle = group_rotation_angle(o[4] for o in objs)
    if angle is None:
        angle = 0.0

    rects = [object_local_rect_in_frame(x, y, w, h, rot, angle) for (x, y, w, h, rot) in objs]
    lx0 = min(r[0] for r in rects)
    ly0 = min(r[1] for r in rects)
    lx1 = max(r[0] + r[2] for r in rects)
    ly1 = max(r[1] + r[3] for r in rects)

    local_corners = [(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1)]
    corners_world = [frame_to_world(cx, cy, angle) for (cx, cy) in local_corners]
    return angle, (lx0, ly0, lx1, ly1), corners_world


def resize_in_frame(snapshots, angle: float, local_bbox0, handle: str,
                     dx_local: float, dy_local: float, shift_locked: bool,
                     min_size: float = 5.0):
    """Resize a set of objects, sharing rotation `angle`, by dragging
    `handle` of their group selection box by (dx_local, dy_local) -- a
    mouse delta already expressed in the group's local (un-rotated) frame.

    snapshots: dict id -> (x, y, width, height) world, at drag start.
    local_bbox0: (lx0, ly0, lx1, ly1) group local bbox at drag start.

    Returns dict id -> (new_x, new_y, new_width, new_height) world.
    """
    bx0, by0, bx1, by1 = local_bbox0
    bw0, bh0 = bx1 - bx0, by1 - by0

    new_x, new_y = bx0, by0
    new_w, new_h = bw0, bh0

    if 'L' in handle:
        new_x = bx0 + dx_local
        new_w = bw0 - dx_local
    elif 'R' in handle:
        new_w = bw0 + dx_local

    if 'T' in handle:
        new_y = by0 + dy_local
        new_h = bh0 - dy_local
    elif 'B' in handle:
        new_h = bh0 + dy_local

    new_w = max(min_size, new_w)
    new_h = max(min_size, new_h)

    if shift_locked and bw0 > 0 and bh0 > 0:
        ar = bw0 / bh0
        if handle in ('TL', 'TR', 'BR', 'BL'):
            sw = new_w / bw0
            sh = new_h / bh0
            s = (sw + sh) / 2.0
            new_w = max(min_size, bw0 * s)
            new_h = max(min_size, bh0 * s)
            if 'L' in handle:
                new_x = (bx0 + bw0) - new_w
            if 'T' in handle:
                new_y = (by0 + bh0) - new_h
        elif handle in ('L', 'R'):
            new_h = new_w / ar
        elif handle in ('T', 'B'):
            new_w = new_h * ar

    if new_w <= 0 or new_h <= 0:
        return {}

    sx = new_w / bw0 if bw0 > 0 else 1.0
    sy = new_h / bh0 if bh0 > 0 else 1.0

    ax = bx0 if 'R' in handle else bx0 + bw0
    ay = by0 if 'T' in handle else by0 + bh0

    results = {}
    for obj_id, (ox, oy, ow, oh) in snapshots.items():
        olx, oly, olw, olh = object_local_rect_in_frame(ox, oy, ow, oh, angle, angle)
        t_lx = ax + (olx - ax) * sx
        t_ly = ay + (oly - ay) * sy
        t_w = max(min_size, olw * sx)
        t_h = max(min_size, olh * sy)
        new_center = frame_to_world(t_lx + t_w / 2.0, t_ly + t_h / 2.0, angle)
        results[obj_id] = (new_center[0] - t_w / 2.0, new_center[1] - t_h / 2.0, t_w, t_h)
    return results
