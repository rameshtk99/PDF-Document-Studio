"""
Shared design tokens for the app's customtkinter UI (modern_dialogs.py,
compress_dialog.py, insert_pages_dialog.py, quick_footer_panel.py,
tools_panel.py, and editor_window.py's chrome). Centralized here so every
migrated widget stays visually consistent -- ported from the prototype
in mockup_ui/theme.py once that design was verified against real
screenshots.

Colors are given as (light, dark) tuples -- customtkinter widgets accept
that directly for any *_color argument and pick the right one based on
ctk.set_appearance_mode(). Pass a plain string only when a color is meant
to stay fixed across modes (e.g. the accent color).
"""

import customtkinter as ctk

# ---------------------------------------------------------------- palette


# Layered-surface ladder -- each step is a small, deliberate luminance
# step up from the one before (never pure black/white), so panels read as
# stacked depth rather than a wall of same-toned rectangles:
#   BG_APP (window) < BG_PANEL (toolbar/sidebar/inspector) < BG_SURFACE
#   (cards/dialogs) < BG_ELEVATED (hovered card) < BG_SUBTLE (inputs, which
#   sit visually "recessed" rather than elevated).
BG_APP = ("#F5F6F8", "#1A1B1E")
BG_PANEL = ("#EFF1F3", "#212226")
BG_SURFACE = ("#FFFFFF", "#26272B")
BG_ELEVATED = ("#FFFFFF", "#2E3035")
BG_SUBTLE = ("#F1F2F4", "#2A2B2F")          # input fields -- slightly recessed
BG_HOVER = ("#E9EBEE", "#333438")

BG_SIDEBAR = BG_PANEL                       # legacy alias, kept for call sites still using it

BORDER = ("#E4E6E9", "#333438")
BORDER_SUBTLE = ("#EDEEF0", "#2C2D31")      # barely-there divider, not a "boxed" border
BORDER_STRONG = ("#D3D6DA", "#46484D")

TEXT_PRIMARY = ("#181A1D", "#F2F3F5")
TEXT_SECONDARY = ("#62666D", "#9CA0A8")
TEXT_MUTED = ("#8A8E96", "#6D7178")
TEXT_DISABLED = ("#B3B7BD", "#54565B")

ACCENT = "#2F6FED"          # primary action color (buttons, selection, links)
ACCENT_HOVER = "#255BC7"
ACCENT_PRESSED = "#1E4AA3"
# Restrained tint -- a whisper of accent behind a selected row/card, not a
# saturated block of color; the light-mode value stays pale and the
# dark-mode value stays a desaturated near-neutral so it never reads as
# "the card got painted blue".
ACCENT_SOFT = ("#EAF1FF", "#1E2733")

WARNING = "#D97706"
WARNING_SOFT = ("#FEF3C7", "#332A14")

MULTI_SELECT_SOFT = WARNING_SOFT             # tinted bg for multi-selected thumbnails
MULTI_SELECT_BORDER = (WARNING, WARNING)     # distinct from the accent "current page" color

# Page drop-shadow gradient endpoints (nearest-the-page -> fades into
# workspace background) -- see viewer/pdf_viewer.py's _render_page_bitmap.
SHADOW_NEAR = ("#AEB2B8", "#000000")
SHADOW_FAR = BG_APP

DANGER = "#DC2626"
DANGER_HOVER = "#B91C1C"
DANGER_SOFT = ("#FCEBEB", "#2E1A1A")
SUCCESS = "#16A34A"
SUCCESS_HOVER = "#0F7A2E"

SECONDARY_BTN = ("#EDEEF1", "#313337")
SECONDARY_BTN_HOVER = ("#E2E4E8", "#3B3D42")
SECONDARY_BTN_TEXT = TEXT_PRIMARY

GHOST_HOVER = BG_HOVER

# ---------------------------------------------------------------- spacing / shape

SPACE_4 = 4
SPACE_8 = 8
SPACE_12 = 12
SPACE_16 = 16
SPACE_20 = 20
SPACE_24 = 24
SPACE_32 = 32

PAD = 12
PAD_LG = 16
RADIUS = 8
RADIUS_SM = 6

FONT_FAMILY = "Segoe UI"

_theme_applied = False


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """CTkFont must be created lazily (after a CTk root exists), so this
    is a function, not a module-level constant."""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def resolve(color):
    """Resolve a (light, dark) tuple to a plain color string for the
    CURRENT appearance mode -- needed for the handful of plain tkinter
    widgets (ThumbnailPanel's Canvas/drag-animation frames) that stay
    outside customtkinter's own dynamic light/dark switching, so they
    can still start out matching the app's palette. Returns `color`
    unchanged if it's already a plain string."""
    if isinstance(color, str):
        return color
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]


def lerp_hex(color_a: str, color_b: str, t: float) -> str:
    """Linear-interpolate between two '#RRGGBB' colors at t in [0, 1]."""
    a = tuple(int(color_a[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def apply_base_theme():
    """Call once, right after creating the CTk root. Safe to call more
    than once (e.g. from multiple dialog modules during the phased
    migration) -- only takes effect the first time."""
    global _theme_applied
    if _theme_applied:
        return
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    _theme_applied = True
