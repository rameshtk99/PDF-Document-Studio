"""
VS Code-style stacked panel column: sections share the vertical space,
collapse to their header, and the whole column collapses to a narrow rail
of rotated titles.

Space rules, in order:
  - only one section expanded  -> it takes the full height
  - several expanded           -> they share it, the active one weighted
                                  heavier so it stays workable
  - not enough height          -> every section shrinks toward MIN_BODY
                                  and its own body scrolls

Bodies are expected to scroll themselves (a CTkScrollableFrame or
similar); this only decides how much height each one gets.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from utils import ui_theme, icons as icon_lib

HEADER_H = 28
MIN_SECTION = 92       # header + enough body to stay usable when squeezed
OTHER_TARGET = 168     # what a non-active open section gets when there's room
RAIL_W = 26


class AccordionSection(ctk.CTkFrame):
    """One titled section: a clickable header over a body frame."""

    def __init__(self, parent, name: str, title: str,
                 on_header_click: Callable[[str], None],
                 expanded: bool = True, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("height", 1)
        super().__init__(parent, **kwargs)
        self.name = name
        self._expanded = expanded
        self._on_header_click = on_header_click

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.header = ctk.CTkFrame(self, fg_color=ui_theme.BG_PANEL,
                                    corner_radius=0, height=HEADER_H)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_propagate(False)

        self._chevron = ctk.CTkLabel(self.header, text="", width=14,
                                      image=self._chevron_icon())
        self._chevron.pack(side=tk.LEFT, padx=(6, 2))
        self._title = ctk.CTkLabel(self.header, text=title.upper(),
                                    font=ui_theme.font(10, "bold"),
                                    text_color=ui_theme.TEXT_SECONDARY, anchor="w")
        self._title.pack(side=tk.LEFT)

        self.header_slot = ctk.CTkFrame(self.header, fg_color="transparent", height=HEADER_H)
        self.header_slot.pack(side=tk.RIGHT, padx=(0, 4))

        self.body = ctk.CTkFrame(self, fg_color="transparent", height=1)
        if expanded:
            self.body.grid(row=1, column=0, sticky="nsew")

        for w in (self.header, self._chevron, self._title):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda _e: self._on_header_click(self.name))

    def _chevron_icon(self):
        return icon_lib.get("chevron_down" if self._expanded else "chevron_right",
                             size=11, color=ui_theme.TEXT_SECONDARY)

    def set_expanded(self, expanded: bool):
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._chevron.configure(image=self._chevron_icon())
        if expanded:
            self.body.grid(row=1, column=0, sticky="nsew")
        else:
            self.body.grid_forget()

    def set_active(self, active: bool):
        """Highlight the section that currently owns the most space."""
        self._title.configure(
            text_color=ui_theme.TEXT_PRIMARY if active else ui_theme.TEXT_SECONDARY)

    @property
    def expanded(self) -> bool:
        return self._expanded


class _CollapsedRail(ctk.CTkFrame):
    """Narrow strip of rotated panel names shown when the column is hidden."""

    def __init__(self, parent, on_click: Callable[[str], None], **kwargs):
        kwargs.setdefault("fg_color", ui_theme.BG_PANEL)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("width", RAIL_W)
        super().__init__(parent, **kwargs)
        self.pack_propagate(False)
        self._on_click = on_click
        self._canvases: List[tk.Canvas] = []

    def set_titles(self, titles: List[tuple]):
        for c in self._canvases:
            c.destroy()
        self._canvases = []

        bg = ui_theme.resolve(ui_theme.BG_PANEL)
        fg = ui_theme.resolve(ui_theme.TEXT_SECONDARY)
        for name, title in titles:
            text = title.upper()
            # 7px per char is a close enough advance for 9pt Segoe UI; the
            # canvas only needs to be long enough not to clip the label.
            height = max(60, 12 + 7 * len(text))
            canvas = tk.Canvas(self, width=RAIL_W, height=height, bg=bg,
                                highlightthickness=0, bd=0, cursor="hand2")
            canvas.pack(side=tk.TOP, pady=(8, 0))
            # angle=90 reads bottom-to-top, matching how IDEs label a
            # collapsed tool column.
            canvas.create_text(RAIL_W // 2, height - 6, text=text, angle=90,
                                anchor="w", fill=fg,
                                font=(ui_theme.FONT_FAMILY, 9, "bold"))
            canvas.bind("<Button-1>", lambda _e, n=name: self._on_click(n))
            self._canvases.append(canvas)


class AccordionPanel(ctk.CTkFrame):
    """A column of AccordionSections plus its collapsed rail.

    The rail and the section stack are separate children; exactly one is
    gridded at a time so the column's width collapses with it.
    """

    def __init__(self, parent, on_collapsed_change: Optional[Callable[[bool], None]] = None,
                 **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._sections: Dict[str, AccordionSection] = {}
        self._order: List[str] = []
        self._active: Optional[str] = None
        self._collapsed = False
        self._on_collapsed_change = on_collapsed_change

        self._stack = ctk.CTkFrame(self, fg_color="transparent")
        self._stack.grid(row=0, column=0, sticky="nsew")
        self._stack.columnconfigure(0, weight=1)
        self._stack_h = 0
        self._stack.bind("<Configure>", self._on_stack_resized, add="+")

        self._rail = _CollapsedRail(self, on_click=self._expand_from_rail)

    # ---------------------------------------------------------------- sections

    def add(self, name: str, title: Optional[str] = None,
            expanded: bool = True) -> ctk.CTkFrame:
        section = AccordionSection(self._stack, name, title or name,
                                    on_header_click=self.toggle, expanded=expanded)
        section.grid(row=len(self._order), column=0, sticky="nsew")
        self._sections[name] = section
        self._order.append(name)
        if expanded and self._active is None:
            self._active = name
        self._relayout()
        return section.body

    def section(self, name: str) -> AccordionSection:
        return self._sections[name]

    def toggle(self, name: str):
        section = self._sections.get(name)
        if not section:
            return
        if section.expanded:
            section.set_expanded(False)
            if self._active == name:
                self._active = next((n for n in self._order
                                      if self._sections[n].expanded), None)
        else:
            section.set_expanded(True)
            self._active = name
        self._relayout()

    def set_expanded(self, name: str, expanded: bool):
        section = self._sections.get(name)
        if section and section.expanded != expanded:
            self.toggle(name)

    def focus_section(self, name: str, expand: bool = True):
        """Make `name` the active (space-favoured) section."""
        section = self._sections.get(name)
        if not section:
            return
        if expand and not section.expanded:
            section.set_expanded(True)
        if section.expanded:
            self._active = name
            self._relayout()

    def set_section_visible(self, name: str, visible: bool):
        """Show/hide a section entirely -- for panels that only apply in
        some states (Image Properties with nothing selected)."""
        section = self._sections.get(name)
        if not section:
            return
        if visible:
            section.grid(row=self._order.index(name), column=0, sticky="nsew")
        else:
            section.grid_remove()
            if self._active == name:
                self._active = next((n for n in self._order
                                      if self._sections[n].expanded
                                      and self._sections[n].winfo_manager()), None)
        self._relayout()

    # ---------------------------------------------------------------- layout

    def _relayout(self):
        """Reassign row sizes and refresh the rail's labels."""
        multiple = self._expanded_count() > 1
        for name in self._order:
            self._sections[name].set_active(name == self._active and multiple)

        self._apply_sizes()
        self._rail.set_titles([(n, self._sections[n]._title.cget("text"))
                                for n in self._order if self._sections[n].winfo_manager()])

    def _apply_sizes(self):
        """Give each row an explicit height rather than leaning on weights.

        Tk's grid uses weight for shrinking as well as growing, so once
        the open sections want more height than the column has -- the
        normal case, since the bodies scroll -- a heavier weight makes a
        row *smaller*. Sizing the rows directly is the only way to say
        "the active panel keeps the most room" and have it hold at every
        window height.
        """
        rows = [(row, name, self._sections[name]) for row, name in enumerate(self._order)]
        visible = [(r, n, s) for r, n, s in rows if s.winfo_manager()]
        expanded = [(r, n, s) for r, n, s in visible if s.expanded]

        for row, _name, _section in rows:
            self._stack.rowconfigure(row, weight=0, minsize=0)
        for row, _name, _section in visible:
            self._stack.rowconfigure(row, weight=0, minsize=HEADER_H)

        if not expanded:
            return

        stack_h = self._stack.winfo_height()
        if stack_h <= 1:                     # not laid out yet; retry once mapped
            self.after(50, self._apply_sizes)
            return

        collapsed_count = len(visible) - len(expanded)
        budget = stack_h - collapsed_count * HEADER_H
        count = len(expanded)

        if count == 1 or budget <= count * MIN_SECTION:
            # One open section takes everything; too little room means an
            # even split, which keeps every header reachable.
            share = max(MIN_SECTION, budget // count) if count else budget
            sizes = {name: share for _r, name, _s in expanded}
        else:
            other = min(OTHER_TARGET, max(MIN_SECTION, budget // count))
            active_name = self._active if any(n == self._active for _r, n, _s in expanded) \
                else expanded[0][1]
            sizes = {name: other for _r, name, _s in expanded}
            sizes[active_name] = budget - other * (count - 1)

        for row, name, _section in expanded:
            # weight on the active row absorbs rounding slack.
            self._stack.rowconfigure(
                row, weight=1 if name == self._active else 0, minsize=sizes[name])

    def _on_stack_resized(self, event):
        """Re-share the height when the column grows or shrinks."""
        if event.height == self._stack_h:
            return
        self._stack_h = event.height
        self._apply_sizes()

    def _expanded_count(self) -> int:
        return sum(1 for n in self._order
                   if self._sections[n].expanded and self._sections[n].winfo_manager())

    # ---------------------------------------------------------------- collapse

    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        if collapsed:
            self._stack.grid_remove()
            self._rail.grid(row=0, column=0, sticky="ns")
        else:
            self._rail.grid_remove()
            self._stack.grid(row=0, column=0, sticky="nsew")
        if self._on_collapsed_change:
            self._on_collapsed_change(collapsed)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def _expand_from_rail(self, name: str):
        self.set_collapsed(False)
        self.focus_section(name)
