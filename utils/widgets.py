"""
Reusable, pre-styled widget factories built on top of ui_theme's design
tokens + icons/tooltip -- the single place that defines what a "primary
button" or "icon-only toolbar button" looks like, so every panel/dialog
that needs one gets the same visual language instead of hand-rolling
CTkButton(...) with slightly different colors/padding each time.

Button variants (see create_button's `variant` arg):
    primary      - filled accent, white text. The one standout action in
                   a given area (Export PDF, Open PDF).
    secondary    - filled neutral surface, normal text. Common actions
                   that aren't THE primary one (Save Project, Add Image).
    tertiary     - transparent until hovered ("ghost"). Compact utility
                   actions (Undo, Redo, zoom steps), usually icon-only
                   + tooltip. `ghost` is kept as an alias.
    destructive  - filled danger color. Anything that deletes/removes.
    danger_ghost - tertiary weight, danger color. Destructive actions
                   that shouldn't shout (inline "delete this draft").
    toolbar      - like tertiary, sized for a dense command-bar row.
"""

from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk
import customtkinter as ctk

from utils import ui_theme, icons as icon_lib, tooltip as tooltip_lib

_VARIANTS = {
    "primary": dict(fg_color=ui_theme.ACCENT, hover_color=ui_theme.ACCENT_HOVER,
                     text_color="white", icon_color="white"),
    "secondary": dict(fg_color=ui_theme.SECONDARY_BTN, hover_color=ui_theme.SECONDARY_BTN_HOVER,
                       text_color=ui_theme.TEXT_PRIMARY, icon_color=ui_theme.TEXT_PRIMARY),
    "ghost": dict(fg_color="transparent", hover_color=ui_theme.GHOST_HOVER,
                  text_color=ui_theme.TEXT_PRIMARY, icon_color=ui_theme.TEXT_SECONDARY),
    "tertiary": dict(fg_color="transparent", hover_color=ui_theme.GHOST_HOVER,
                      text_color=ui_theme.TEXT_PRIMARY, icon_color=ui_theme.TEXT_SECONDARY),
    "destructive": dict(fg_color=ui_theme.DANGER, hover_color=ui_theme.DANGER_HOVER,
                         text_color="white", icon_color="white"),
    "danger_ghost": dict(fg_color="transparent", hover_color=ui_theme.DANGER_SOFT,
                          text_color=ui_theme.DANGER, icon_color=ui_theme.DANGER),
    "toolbar": dict(fg_color="transparent", hover_color=ui_theme.GHOST_HOVER,
                     text_color=ui_theme.TEXT_PRIMARY, icon_color=ui_theme.TEXT_PRIMARY),
}


def create_button(parent, text: str = "", command: Optional[Callable] = None,
                   variant: str = "secondary", icon: Optional[str] = None,
                   icon_size: int = 15, width: int = 0, height: int = 32,
                   font_weight: Optional[str] = None, tooltip: Optional[str] = None,
                   **kwargs) -> ctk.CTkButton:
    """A single labeled (optionally icon+label) button in one of the
    standard variants. `disabled_state_aware` styling (dimmer on
    state='disabled') comes for free from customtkinter's own handling of
    fg_color/text_color once disabled -- callers just call
    .configure(state='disabled')."""
    style = _VARIANTS[variant]
    weight = font_weight or ("bold" if variant in ("primary", "destructive") else "normal")
    image = icon_lib.get(icon, size=icon_size, color=style["icon_color"]) if icon else None

    btn = ctk.CTkButton(
        parent, text=text, command=command, image=image, compound="left",
        width=width, height=height, corner_radius=ui_theme.RADIUS_SM,
        fg_color=style["fg_color"], hover_color=style["hover_color"],
        text_color=style["text_color"], font=ui_theme.font(12, weight),
        **kwargs,
    )
    if tooltip:
        # Kept on the widget so callers whose button changes meaning
        # (a show/hide toggle) can retarget the tooltip text later.
        btn.tooltip = tooltip_lib.attach(btn, tooltip)
    return btn


def create_icon_button(parent, icon: str, command: Optional[Callable] = None,
                        tooltip: Optional[str] = None, size: int = 16,
                        height: int = 30, width: int = 30,
                        variant: str = "ghost", **kwargs) -> ctk.CTkButton:
    """Icon-only square button -- every caller MUST pass `tooltip` (icon-
    only controls are otherwise unlabeled)."""
    style = _VARIANTS[variant]
    image = icon_lib.get(icon, size=size, color=style["icon_color"])
    btn = ctk.CTkButton(
        parent, text="", image=image, command=command, width=width, height=height,
        corner_radius=ui_theme.RADIUS_SM, fg_color=style["fg_color"],
        hover_color=style["hover_color"], **kwargs,
    )
    if tooltip:
        # Kept on the widget so callers whose button changes meaning
        # (a show/hide toggle) can retarget the tooltip text later.
        btn.tooltip = tooltip_lib.attach(btn, tooltip)
    return btn


def vertical_separator(parent, height: int = 22, pad: int = ui_theme.SPACE_8) -> ctk.CTkFrame:
    sep = ctk.CTkFrame(parent, width=1, height=height, fg_color=ui_theme.BORDER)
    sep.pack(side=tk.LEFT, padx=pad, pady=4)
    return sep


class SegmentedTabs(ctk.CTkFrame):
    """Editorial-style tab navigation -- text labels on a shared thin
    track, active tab marked with a 2px accent underline + bold text,
    inactive tabs are plain muted text. Deliberately NOT a pill/segmented
    button pair (that reads as two buttons, not tabs).

    API mirrors the subset of ctk.CTkTabview this app actually uses:
        tabs = SegmentedTabs(parent)
        page = tabs.add("Quick Footer")   # returns a frame -- pack content into it
        tabs.pack(fill="both", expand=True)
    """

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)

        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.pack(side=tk.TOP, fill="x")
        ctk.CTkFrame(self, height=1, fg_color=ui_theme.BORDER_SUBTLE, corner_radius=0
                     ).pack(side=tk.TOP, fill="x")
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(side=tk.TOP, fill="both", expand=True)

        self._tabs: dict = {}
        self._active: Optional[str] = None

    def add(self, name: str) -> ctk.CTkFrame:
        col = ctk.CTkFrame(self._header, fg_color="transparent")
        col.pack(side=tk.LEFT)

        label = ctk.CTkLabel(col, text=name, font=ui_theme.font(12), cursor="hand2",
                              text_color=ui_theme.TEXT_SECONDARY)
        label.pack(padx=ui_theme.SPACE_16, pady=(ui_theme.SPACE_8, ui_theme.SPACE_8 - 2))
        underline = ctk.CTkFrame(col, height=2, fg_color="transparent", corner_radius=0)
        underline.pack(fill="x")

        content = ctk.CTkFrame(self._body, fg_color="transparent")

        for w in (col, label):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda e, n=name: self.select(n))

        self._tabs[name] = dict(label=label, underline=underline, content=content)
        if self._active is None:
            self._active = name
            content.pack(fill="both", expand=True)
        self._restyle()
        return content

    def select(self, name: str):
        if name not in self._tabs or name == self._active:
            return
        self._tabs[self._active]["content"].pack_forget()
        self._active = name
        self._tabs[name]["content"].pack(fill="both", expand=True)
        self._restyle()

    def _restyle(self):
        for name, tab in self._tabs.items():
            active = name == self._active
            tab["label"].configure(
                text_color=ui_theme.ACCENT if active else ui_theme.TEXT_SECONDARY,
                font=ui_theme.font(12, "bold" if active else "normal"))
            tab["underline"].configure(fg_color=ui_theme.ACCENT if active else "transparent")


class CollapsibleSection(ctk.CTkFrame):
    """One titled, click-to-collapse group of related controls -- the
    building block for a property inspector that shows a handful of
    section headers rather than every field in the panel at once.

    Content goes into `.body`; an optional small control (a count field,
    an "apply" tick) can be docked at the right end of the header row via
    `.header_slot`, and it stays clickable rather than toggling the
    section.

        sec = CollapsibleSection(parent, "Typography")
        sec.pack(fill="x")
        ctk.CTkLabel(sec.body, text="...").pack()
    """

    _CHEVRON_SIZE = 11

    def __init__(self, parent, title: str, expanded: bool = True,
                 on_toggle: Optional[Callable[[bool], None]] = None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        # CTkFrame carries a default height=200 that wins whenever its
        # children don't add up to more than that, so a content-hugging
        # wrapper silently reserves 200px -- which for a *collapsed*
        # section is 200px of nothing, shoving everything below it out of
        # the panel. Every frame here that should size to its content
        # says so explicitly.
        kwargs.setdefault("height", 1)
        super().__init__(parent, **kwargs)
        self._expanded = expanded
        self._on_toggle = on_toggle

        header = ctk.CTkFrame(self, fg_color="transparent", height=22)
        header.pack(fill="x")

        self._chevron = ctk.CTkLabel(header, text="", width=14,
                                      image=self._chevron_icon(expanded))
        self._chevron.pack(side=tk.LEFT)
        self._title = ctk.CTkLabel(header, text=title.upper(), font=ui_theme.font(10, "bold"),
                                    text_color=ui_theme.TEXT_SECONDARY, anchor="w")
        self._title.pack(side=tk.LEFT)

        # Docked to the right of the header for per-section controls.
        # Packed before nothing else claims the row, and deliberately NOT
        # wired to the toggle click so its own widgets stay usable.
        self.header_slot = ctk.CTkFrame(header, fg_color="transparent", height=22)
        self.header_slot.pack(side=tk.RIGHT)

        self.body = ctk.CTkFrame(self, fg_color="transparent", height=1)
        if expanded:
            self.body.pack(fill="x", pady=(ui_theme.SPACE_4, 0))

        for w in (header, self._chevron, self._title):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda _e: self.toggle())

    def _chevron_icon(self, expanded: bool):
        return icon_lib.get("chevron_down" if expanded else "chevron_right",
                             size=self._CHEVRON_SIZE, color=ui_theme.TEXT_SECONDARY)

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool):
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._chevron.configure(image=self._chevron_icon(expanded))
        if expanded:
            self.body.pack(fill="x", pady=(ui_theme.SPACE_4, 0))
        else:
            self.body.pack_forget()
        if self._on_toggle:
            self._on_toggle(expanded)

    @property
    def expanded(self) -> bool:
        return self._expanded


class NumberSpinner(ctk.CTkFrame):
    """Compact numeric field with stacked up/down steppers -- a classic
    spinbox, for small bounded numeric settings (gaps, spacing, sizes)
    where a bare text entry gives no affordance for "nudge this value"
    and a side-by-side [-][value][+] would need more width than a
    two-column settings grid has to spare.

    Reads/writes a tk DoubleVar/IntVar in place, so existing code that
    already binds one of those to other logic keeps working unchanged.
    """

    def __init__(self, parent, variable, step: float = 0.1,
                 minval: Optional[float] = None, maxval: Optional[float] = None,
                 decimals: int = 1, height: int = 28,
                 on_change: Optional[Callable] = None, **kwargs):
        kwargs.setdefault("fg_color", ui_theme.BG_SUBTLE)
        kwargs.setdefault("corner_radius", ui_theme.RADIUS_SM)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", ui_theme.BORDER)
        super().__init__(parent, height=height, **kwargs)
        self.pack_propagate(False)
        self.variable = variable
        self.step = step
        self.minval = minval
        self.maxval = maxval
        self.decimals = decimals
        self.on_change = on_change

        # Stepper (fixed-width, side=RIGHT) MUST be packed before the
        # expanding entry -- pack() allocates cavity space in packing
        # order, so an expand=True widget packed first would claim the
        # whole frame and leave nothing for a fixed-width one packed
        # after it.
        stepper = ctk.CTkFrame(self, width=18, fg_color="transparent")
        stepper.pack(side=tk.RIGHT, fill="y")
        stepper.pack_propagate(False)

        self.entry = ctk.CTkEntry(
            self, textvariable=variable, height=height, corner_radius=0,
            border_width=0, fg_color="transparent", font=ui_theme.font(12))
        self.entry.pack(side=tk.LEFT, fill="both", expand=True, padx=(8, 0))
        self.entry.bind("<KeyRelease>", lambda e: self._notify())
        self.entry.bind("<FocusOut>", lambda e: self._clamp())
        self.entry.bind("<MouseWheel>", self._on_wheel)

        half_h = max(10, height // 2 - 1)
        up = ctk.CTkButton(
            stepper, text="", image=icon_lib.get("move_up", size=8, color=ui_theme.TEXT_SECONDARY),
            width=18, height=half_h, corner_radius=0, fg_color="transparent",
            hover_color=ui_theme.GHOST_HOVER, command=lambda: self._step(1))
        up.pack(side=tk.TOP, fill="both", expand=True)
        down = ctk.CTkButton(
            stepper, text="", image=icon_lib.get("move_down", size=8, color=ui_theme.TEXT_SECONDARY),
            width=18, height=half_h, corner_radius=0, fg_color="transparent",
            hover_color=ui_theme.GHOST_HOVER, command=lambda: self._step(-1))
        down.pack(side=tk.BOTTOM, fill="both", expand=True)
        for w in (up, down):
            w.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event):
        self._step(1 if event.delta > 0 else -1)
        return "break"

    def _step(self, sign: int):
        try:
            value = float(self.variable.get())
        except (tk.TclError, ValueError):
            value = 0.0
        value = self._clamp_value(round(value + sign * self.step, self.decimals))
        self.variable.set(value)
        self._notify()

    def _clamp_value(self, value: float) -> float:
        if self.minval is not None:
            value = max(self.minval, value)
        if self.maxval is not None:
            value = min(self.maxval, value)
        return round(value, self.decimals)

    def _clamp(self):
        try:
            value = float(self.variable.get())
        except (tk.TclError, ValueError):
            return
        clamped = self._clamp_value(value)
        if clamped != value:
            self.variable.set(clamped)
        self._notify()

    def _notify(self):
        if self.on_change:
            self.on_change()


def empty_state(parent, icon: str, title: str, subtitle: str = "",
                 button_text: Optional[str] = None,
                 button_command: Optional[Callable] = None) -> ctk.CTkFrame:
    """A centered "nothing here yet" placeholder -- icon + title +
    optional subtitle + optional call-to-action button. Used wherever a
    panel would otherwise show a wall of disabled/empty fields."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")

    icon_lbl = ctk.CTkLabel(frame, image=icon_lib.get(icon, size=32, color=ui_theme.TEXT_DISABLED), text="")
    icon_lbl.pack(pady=(0, ui_theme.SPACE_12))
    ctk.CTkLabel(frame, text=title, font=ui_theme.font(12, "bold"),
                 text_color=ui_theme.TEXT_SECONDARY).pack()
    if subtitle:
        ctk.CTkLabel(frame, text=subtitle, font=ui_theme.font(11), text_color=ui_theme.TEXT_DISABLED,
                     wraplength=220, justify=tk.CENTER).pack(pady=(4, 0))
    if button_text and button_command:
        create_button(frame, text=button_text, command=button_command, variant="primary",
                      height=32).pack(pady=(ui_theme.SPACE_16, 0))
    return frame
