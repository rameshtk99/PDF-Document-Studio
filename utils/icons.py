"""
Monochrome vector icon set, drawn procedurally with PIL at 4x and
downscaled -- no icon font or asset files, so nothing depends on a
particular font being installed.

`get()` returns a cached ctk.CTkImage (light/dark baked in). Caching also
keeps a live reference, without which Tk garbage-collects the image and
the button renders blank.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

from PIL import Image, ImageDraw
import customtkinter as ctk

from utils import ui_theme

_SCALE = 4
_CACHE: Dict[tuple, "ctk.CTkImage"] = {}
_RENDER_CACHE: Dict[tuple, Image.Image] = {}


def _canvas(size: int):
    s = size * _SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), s


def _lw(s: int) -> int:
    """Stroke width in supersampled px -- ~1.8px once downscaled."""
    return max(2, round(s * 0.092))


def _finish(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def _pt(frac_x: float, frac_y: float, s: int) -> Tuple[float, float]:
    return (frac_x * s, frac_y * s)


# ---------------------------------------------------------------- icon recipes
# Each draws into a 0..1 fractional coordinate space (mapped to the
# supersampled canvas by the caller) with a rounded stroke join, so every
# icon reads at the same visual weight regardless of shape complexity.

def _line(draw, s, pts, w, color):
    scaled = [_pt(x, y, s) for x, y in pts]
    draw.line(scaled, fill=color, width=w, joint="curve")
    r = w / 2
    for x, y in scaled:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def _icon_open(draw, s, w, color):
    # Folder outline with a small tab
    _line(draw, s, [(0.10, 0.32), (0.10, 0.80), (0.90, 0.80), (0.90, 0.32),
                     (0.52, 0.32), (0.44, 0.20), (0.18, 0.20), (0.10, 0.32)], w, color)


def _icon_save(draw, s, w, color):
    # Floppy disk: outer square with folded corner + inner label rect
    _line(draw, s, [(0.16, 0.14), (0.72, 0.14), (0.86, 0.28), (0.86, 0.86),
                     (0.16, 0.86), (0.16, 0.14)], w, color)
    _line(draw, s, [(0.30, 0.14), (0.30, 0.38), (0.66, 0.38), (0.66, 0.14)], w, color)
    _line(draw, s, [(0.30, 0.86), (0.30, 0.58), (0.70, 0.58), (0.70, 0.86)], w, color)


def _icon_export(draw, s, w, color):
    # Tray (open box) with an arrow exiting upward
    _line(draw, s, [(0.18, 0.55), (0.18, 0.84), (0.82, 0.84), (0.82, 0.55)], w, color)
    _line(draw, s, [(0.50, 0.78), (0.50, 0.16)], w, color)
    _line(draw, s, [(0.30, 0.36), (0.50, 0.16), (0.70, 0.36)], w, color)


def _icon_import(draw, s, w, color):
    _line(draw, s, [(0.18, 0.55), (0.18, 0.84), (0.82, 0.84), (0.82, 0.55)], w, color)
    _line(draw, s, [(0.50, 0.18), (0.50, 0.68)], w, color)
    _line(draw, s, [(0.30, 0.48), (0.50, 0.68), (0.70, 0.48)], w, color)


def _icon_undo(draw, s, w, color):
    box = [0.20 * s, 0.20 * s, 0.86 * s, 0.86 * s]
    draw.arc(box, start=140, end=360, fill=color, width=w)
    _line(draw, s, [(0.40, 0.16), (0.19, 0.34), (0.40, 0.50)], w, color)


def _icon_redo(draw, s, w, color):
    box = [0.14 * s, 0.20 * s, 0.80 * s, 0.86 * s]
    draw.arc(box, start=180, end=400, fill=color, width=w)
    _line(draw, s, [(0.60, 0.16), (0.81, 0.34), (0.60, 0.50)], w, color)


def _icon_add_image(draw, s, w, color):
    _line(draw, s, [(0.12, 0.20), (0.12, 0.80), (0.72, 0.80), (0.72, 0.20), (0.12, 0.20)], w, color)
    _line(draw, s, [(0.12, 0.66), (0.32, 0.46), (0.46, 0.60), (0.58, 0.48), (0.72, 0.62)], w, color)
    cx, cy, r = 0.27 * s, 0.35 * s, 0.06 * s
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
    _line(draw, s, [(0.80, 0.62), (0.80, 0.86)], w, color)
    _line(draw, s, [(0.68, 0.74), (0.92, 0.74)], w, color)


def _icon_delete(draw, s, w, color):
    _line(draw, s, [(0.24, 0.30), (0.76, 0.30)], w, color)
    _line(draw, s, [(0.40, 0.30), (0.40, 0.20), (0.60, 0.20), (0.60, 0.30)], w, color)
    _line(draw, s, [(0.30, 0.30), (0.33, 0.84), (0.67, 0.84), (0.70, 0.30)], w, color)
    _line(draw, s, [(0.43, 0.42), (0.44, 0.72)], w, color)
    _line(draw, s, [(0.57, 0.42), (0.56, 0.72)], w, color)


def _icon_move_up(draw, s, w, color):
    _line(draw, s, [(0.20, 0.46), (0.50, 0.16), (0.80, 0.46)], w, color)
    _line(draw, s, [(0.50, 0.20), (0.50, 0.84)], w, color)


def _icon_move_down(draw, s, w, color):
    _line(draw, s, [(0.20, 0.54), (0.50, 0.84), (0.80, 0.54)], w, color)
    _line(draw, s, [(0.50, 0.16), (0.50, 0.80)], w, color)


def _icon_chevron_left(draw, s, w, color):
    _line(draw, s, [(0.60, 0.18), (0.32, 0.50), (0.60, 0.82)], w, color)


def _icon_chevron_right(draw, s, w, color):
    _line(draw, s, [(0.40, 0.18), (0.68, 0.50), (0.40, 0.82)], w, color)


def _icon_chevron_down(draw, s, w, color):
    _line(draw, s, [(0.20, 0.40), (0.50, 0.68), (0.80, 0.40)], w, color)


def _icon_chevron_up(draw, s, w, color):
    _line(draw, s, [(0.20, 0.62), (0.50, 0.34), (0.80, 0.62)], w, color)


def _icon_panel_left(draw, s, w, color):
    """Sidebar-toggle glyph: a panel outline with its left column marked."""
    _line(draw, s, [(0.14, 0.20), (0.14, 0.80), (0.86, 0.80), (0.86, 0.20), (0.14, 0.20)], w, color)
    _line(draw, s, [(0.40, 0.20), (0.40, 0.80)], w, color)
    for y in (0.36, 0.50, 0.64):
        _line(draw, s, [(0.21, y), (0.33, y)], w, color)


def _icon_panel_right(draw, s, w, color):
    _line(draw, s, [(0.14, 0.20), (0.14, 0.80), (0.86, 0.80), (0.86, 0.20), (0.14, 0.20)], w, color)
    _line(draw, s, [(0.60, 0.20), (0.60, 0.80)], w, color)
    for y in (0.36, 0.50, 0.64):
        _line(draw, s, [(0.67, y), (0.79, y)], w, color)


def _icon_zoom_in(draw, s, w, color):
    cx, cy, r = 0.42 * s, 0.42 * s, 0.26 * s
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
    _line(draw, s, [(0.62, 0.62), (0.86, 0.86)], w, color)
    _line(draw, s, [(0.30, 0.42), (0.54, 0.42)], w, color)
    _line(draw, s, [(0.42, 0.30), (0.42, 0.54)], w, color)


def _icon_zoom_out(draw, s, w, color):
    cx, cy, r = 0.42 * s, 0.42 * s, 0.26 * s
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
    _line(draw, s, [(0.62, 0.62), (0.86, 0.86)], w, color)
    _line(draw, s, [(0.30, 0.42), (0.54, 0.42)], w, color)


def _icon_fit_page(draw, s, w, color):
    corner = 0.16
    for x0, y0, dx, dy in ((0.14, 0.14, 1, 1), (0.86, 0.14, -1, 1),
                            (0.14, 0.86, 1, -1), (0.86, 0.86, -1, -1)):
        _line(draw, s, [(x0, y0 + corner * dy), (x0, y0), (x0 + corner * dx, y0)], w, color)
    _line(draw, s, [(0.32, 0.32), (0.32, 0.68), (0.68, 0.68), (0.68, 0.32), (0.32, 0.32)], w, color)


def _icon_fit_width(draw, s, w, color):
    _line(draw, s, [(0.14, 0.50), (0.30, 0.34)], w, color)
    _line(draw, s, [(0.14, 0.50), (0.30, 0.66)], w, color)
    _line(draw, s, [(0.86, 0.50), (0.70, 0.34)], w, color)
    _line(draw, s, [(0.86, 0.50), (0.70, 0.66)], w, color)
    _line(draw, s, [(0.14, 0.50), (0.86, 0.50)], w, color)
    _line(draw, s, [(0.30, 0.18), (0.30, 0.82)], w, color)
    _line(draw, s, [(0.70, 0.18), (0.70, 0.82)], w, color)


def _icon_settings(draw, s, w, color):
    for i, y in enumerate((0.28, 0.52, 0.76)):
        _line(draw, s, [(0.14, y), (0.86, y)], w, color)
        knob_x = (0.34, 0.62, 0.46)[i]
        r = 0.075 * s
        draw.ellipse([knob_x * s - r, y * s - r, knob_x * s + r, y * s + r],
                     outline=color, width=w, fill=ui_theme.resolve(ui_theme.BG_SURFACE))


def _icon_close(draw, s, w, color):
    _line(draw, s, [(0.24, 0.24), (0.76, 0.76)], w, color)
    _line(draw, s, [(0.76, 0.24), (0.24, 0.76)], w, color)


def _icon_more(draw, s, w, color):
    r = 0.06 * s
    for cx in (0.24, 0.50, 0.76):
        cy = 0.50
        draw.ellipse([cx * s - r, cy * s - r, cx * s + r, cy * s + r], fill=color)


def _icon_plus(draw, s, w, color):
    _line(draw, s, [(0.50, 0.18), (0.50, 0.82)], w, color)
    _line(draw, s, [(0.18, 0.50), (0.82, 0.50)], w, color)


def _icon_duplicate(draw, s, w, color):
    _line(draw, s, [(0.14, 0.30), (0.14, 0.70), (0.54, 0.70), (0.54, 0.30), (0.14, 0.30)], w, color)
    _line(draw, s, [(0.34, 0.30), (0.34, 0.16), (0.86, 0.16), (0.86, 0.56), (0.70, 0.56)], w, color)


def _icon_edit(draw, s, w, color):
    _line(draw, s, [(0.20, 0.68), (0.62, 0.26), (0.76, 0.40), (0.34, 0.82), (0.18, 0.84), (0.20, 0.68)], w, color)
    _line(draw, s, [(0.62, 0.26), (0.76, 0.40)], w, color)


def _icon_compress(draw, s, w, color):
    _line(draw, s, [(0.16, 0.16), (0.38, 0.16), (0.38, 0.38), (0.16, 0.38)], w, color)
    _line(draw, s, [(0.16, 0.16), (0.34, 0.34)], w, color)
    _line(draw, s, [(0.84, 0.84), (0.62, 0.84), (0.62, 0.62), (0.84, 0.62)], w, color)
    _line(draw, s, [(0.84, 0.84), (0.66, 0.66)], w, color)


def _icon_insert_pages(draw, s, w, color):
    _line(draw, s, [(0.20, 0.14), (0.20, 0.62), (0.58, 0.62), (0.58, 0.14), (0.20, 0.14)], w, color)
    _line(draw, s, [(0.34, 0.30), (0.44, 0.30)], w, color)
    _line(draw, s, [(0.34, 0.42), (0.50, 0.42)], w, color)
    _line(draw, s, [(0.74, 0.52), (0.74, 0.86)], w, color)
    _line(draw, s, [(0.62, 0.68), (0.74, 0.52), (0.86, 0.68)], w, color)


def _icon_check(draw, s, w, color):
    _line(draw, s, [(0.18, 0.52), (0.40, 0.74), (0.84, 0.26)], w, color)


def _icon_lock(draw, s, w, color):
    _line(draw, s, [(0.28, 0.46), (0.28, 0.30), (0.50, 0.14), (0.72, 0.30), (0.72, 0.46)], w, color)
    _line(draw, s, [(0.22, 0.46), (0.22, 0.84), (0.78, 0.84), (0.78, 0.46), (0.22, 0.46)], w, color)


def _icon_collapse(draw, s, w, color):
    _line(draw, s, [(0.30, 0.16), (0.30, 0.84)], w, color)
    _line(draw, s, [(0.70, 0.34), (0.48, 0.50), (0.70, 0.66)], w, color)


def _icon_expand(draw, s, w, color):
    _line(draw, s, [(0.30, 0.16), (0.30, 0.84)], w, color)
    _line(draw, s, [(0.48, 0.34), (0.70, 0.50), (0.48, 0.66)], w, color)


def _icon_document(draw, s, w, color):
    _line(draw, s, [(0.24, 0.12), (0.60, 0.12), (0.76, 0.28), (0.76, 0.88), (0.24, 0.88), (0.24, 0.12)], w, color)
    _line(draw, s, [(0.60, 0.12), (0.60, 0.28), (0.76, 0.28)], w, color)
    for y in (0.46, 0.58, 0.70):
        _line(draw, s, [(0.36, y), (0.64, y)], w, color)


def _icon_sun(draw, s, w, color):
    cx, cy, r = 0.50 * s, 0.50 * s, 0.20 * s
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
    for angle_pts in [
        ((0.50, 0.10), (0.50, 0.22)),
        ((0.50, 0.78), (0.50, 0.90)),
        ((0.10, 0.50), (0.22, 0.50)),
        ((0.78, 0.50), (0.90, 0.50)),
        ((0.22, 0.22), (0.30, 0.30)),
        ((0.70, 0.70), (0.78, 0.78)),
        ((0.22, 0.78), (0.30, 0.70)),
        ((0.70, 0.30), (0.78, 0.22)),
    ]:
        _line(draw, s, angle_pts, w, color)


def _icon_moon(draw, s, w, color):
    cx, cy, r = 0.52 * s, 0.50 * s, 0.30 * s
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=60, end=300, fill=color, width=w)
    cx2, cy2, r2 = 0.64 * s, 0.50 * s, 0.25 * s
    draw.arc([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2], start=85, end=275, fill=color, width=w)


def _icon_power(draw, s, w, color):
    # Ring broken at the top, with a stem rising through the gap
    box = [0.20 * s, 0.20 * s, 0.80 * s, 0.80 * s]
    draw.arc(box, start=300, end=240, fill=color, width=w)
    _line(draw, s, [(0.50, 0.14), (0.50, 0.46)], w, color)


def _icon_footer(draw, s, w, color):
    _line(draw, s, [(0.20, 0.14), (0.80, 0.14), (0.80, 0.86), (0.20, 0.86), (0.20, 0.14)], w, color)
    _line(draw, s, [(0.20, 0.66), (0.80, 0.66)], w, color)
    _line(draw, s, [(0.32, 0.76), (0.68, 0.76)], w, color)


_RECIPES: Dict[str, Callable] = {
    "open": _icon_open,
    "save": _icon_save,
    "export": _icon_export,
    "import": _icon_import,
    "undo": _icon_undo,
    "redo": _icon_redo,
    "add_image": _icon_add_image,
    "delete": _icon_delete,
    "move_up": _icon_move_up,
    "move_down": _icon_move_down,
    "chevron_left": _icon_chevron_left,
    "chevron_right": _icon_chevron_right,
    "chevron_down": _icon_chevron_down,
    "chevron_up": _icon_chevron_up,
    "panel_left": _icon_panel_left,
    "panel_right": _icon_panel_right,
    "zoom_in": _icon_zoom_in,
    "zoom_out": _icon_zoom_out,
    "fit_page": _icon_fit_page,
    "fit_width": _icon_fit_width,
    "settings": _icon_settings,
    "close": _icon_close,
    "more": _icon_more,
    "plus": _icon_plus,
    "duplicate": _icon_duplicate,
    "edit": _icon_edit,
    "compress": _icon_compress,
    "insert_pages": _icon_insert_pages,
    "check": _icon_check,
    "lock": _icon_lock,
    "collapse": _icon_collapse,
    "expand": _icon_expand,
    "document": _icon_document,
    "sun": _icon_sun,
    "moon": _icon_moon,
    "power": _icon_power,
    "footer": _icon_footer,
}


def _render(name: str, size: int, color: str) -> Image.Image:
    key = (name, size, color)
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        return cached
    recipe = _RECIPES.get(name)
    if recipe is None:
        raise KeyError(f"Unknown icon: {name!r}")
    img, draw, s = _canvas(size)
    recipe(draw, s, _lw(s), color)
    result = _finish(img, size)
    _RENDER_CACHE[key] = result
    return result


def get(name: str, size: int = 16, color=None) -> "ctk.CTkImage":
    """Return a cached CTkImage for `name` at `size` px, colored with
    `color` -- a plain hex string, or a (light, dark) tuple like the ones
    in ui_theme (defaults to ui_theme.TEXT_PRIMARY)."""
    if color is None:
        color = ui_theme.TEXT_PRIMARY
    key = (name, size, color if isinstance(color, str) else tuple(color))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    if isinstance(color, str):
        light_color = dark_color = color
    else:
        light_color, dark_color = color[0], color[1]

    image = ctk.CTkImage(
        light_image=_render(name, size, light_color),
        dark_image=_render(name, size, dark_color),
        size=(size, size),
    )
    _CACHE[key] = image
    return image


def available() -> Tuple[str, ...]:
    return tuple(_RECIPES.keys())
