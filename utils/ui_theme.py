"""
Design tokens for the modern customtkinter UI -- colors, spacing, radius, fonts.

Colors are (light, dark) tuples, which customtkinter accepts directly for
any *_color argument. Use a plain string only where a color should stay
fixed across modes (the accent).
"""

import json
import os
import customtkinter as ctk

# ---------------------------------------------------------------- palette

# Layered surfaces:
# BG_CANVAS < BG_APP < BG_PANEL < BG_SURFACE < BG_ELEVATED
BG_CANVAS = ("#EBEEF2", "#0C0D12")          # Central PDF viewport (high contrast)
BG_APP = ("#F8F9FA", "#13141B")             # Overall window background
BG_PANEL = ("#FFFFFF", "#191A23")           # Top bar, sidebars, inspector
BG_SURFACE = ("#FFFFFF", "#20222D")         # Cards, panels, elevated sections
BG_ELEVATED = ("#FFFFFF", "#282A38")        # Floating dialogs, menus, tooltips
BG_SUBTLE = ("#F1F3F5", "#262835")          # Input fields (recessed)
BG_HOVER = ("#E9ECEF", "#2E3141")           # Subtle hover fill

BG_SIDEBAR = BG_PANEL                       # Alias for backwards compatibility

BORDER = ("#E2E6EA", "#2B2D3C")             # 1px border on cards and inputs
BORDER_SUBTLE = ("#EDF0F3", "#222430")      # Faint internal divider
BORDER_STRONG = ("#CBD2D9", "#3E4154")      # Active/focused border

TEXT_PRIMARY = ("#0F172A", "#F8FAFC")       # Main readable text
TEXT_SECONDARY = ("#64748B", "#94A3B8")     # Subtitles, labels, hints
TEXT_MUTED = ("#94A3B8", "#64748B")         # Tertiary hints
TEXT_DISABLED = ("#CBD5E1", "#475569")      # Disabled state

ACCENT = "#3B82F6"                          # Modern indigo blue (action color)
ACCENT_HOVER = "#2563EB"
ACCENT_PRESSED = "#1D4ED8"
ACCENT_SOFT = ("#EFF6FF", "#192846")        # Tinted background for active item

WARNING = "#F59E0B"
WARNING_SOFT = ("#FEF3C7", "#32230E")

MULTI_SELECT_SOFT = WARNING_SOFT
MULTI_SELECT_BORDER = (WARNING, WARNING)

# Page drop-shadow gradient endpoints
SHADOW_NEAR = ("#94A3B8", "#000000")
SHADOW_FAR = BG_CANVAS

DANGER = "#EF4444"
DANGER_HOVER = "#DC2626"
DANGER_SOFT = ("#FEE2E2", "#2F1515")
SUCCESS = "#10B981"
SUCCESS_HOVER = "#059669"

SECONDARY_BTN = ("#F1F5F9", "#242633")
SECONDARY_BTN_HOVER = ("#E2E8F0", "#303344")
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
_theme_change_listeners = []


def font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    """A function, not a constant: CTkFont needs a CTk root to exist."""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def header_font(size: int = 11) -> ctk.CTkFont:
    """Uppercase section headers (bold, compact)."""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight="bold")


def resolve(color):
    """Flatten a (light, dark) tuple for the current appearance mode.

    Needed by the plain-tkinter widgets that sit outside customtkinter's
    own light/dark switching. Plain strings pass through unchanged.
    """
    if isinstance(color, str):
        return color
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]


def lerp_hex(color_a: str, color_b: str, t: float) -> str:
    """Linear-interpolate between two '#RRGGBB' colors at t in [0, 1]."""
    a = tuple(int(color_a[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def add_theme_listener(callback):
    """Register a callback when appearance mode changes."""
    if callback not in _theme_change_listeners:
        _theme_change_listeners.append(callback)


def remove_theme_listener(callback):
    if callback in _theme_change_listeners:
        _theme_change_listeners.remove(callback)


def _notify_theme_listeners():
    for cb in list(_theme_change_listeners):
        try:
            cb()
        except Exception:
            pass


def set_appearance_mode(mode: str):
    """Set Dark or Light mode and notify listeners."""
    ctk.set_appearance_mode(mode)
    _save_theme_preference(mode)
    _notify_theme_listeners()


def toggle_appearance_mode() -> str:
    """Toggle between Dark and Light mode."""
    curr = ctk.get_appearance_mode()
    new_mode = "Light" if curr == "Dark" else "Dark"
    set_appearance_mode(new_mode)
    return new_mode


def _save_theme_preference(mode: str):
    try:
        from utils.constants import PROJECT_ROOT
        cfg_path = os.path.join(PROJECT_ROOT, "appsettings.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("app", {})["theme"] = mode.lower()
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass


def _load_theme_preference() -> str:
    try:
        from utils.constants import PROJECT_ROOT
        cfg_path = os.path.join(PROJECT_ROOT, "appsettings.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            t = data.get("app", {}).get("theme", "dark")
            return "Light" if t.lower() == "light" else "Dark"
    except Exception:
        pass
    return "Dark"


def apply_base_theme():
    """Call once after creating the CTk root."""
    global _theme_applied
    pref = _load_theme_preference()
    ctk.set_appearance_mode(pref)
    ctk.set_default_color_theme("blue")
    _theme_applied = True
