"""
Compact footer preview -- a small always-visible thumbnail of the footer
band as it will actually be laid out on the page, shown right next to the
fields that drive it.

The live on-canvas preview (FooterPreviewController) is the accurate,
to-scale one, but it only shows the page currently scrolled into view and
is easy to lose track of while typing in the side panel. This widget is
the at-a-glance companion: it mirrors the real column math from
FooterGenerator.create_footer_overlay (equal-share columns between the
left/right margins, text centered per column, line 1 stacked above line 2
with the configured gap, {page}/{total} substituted) so the column
structure and balance read correctly -- but it clamps the font to a
legible minimum instead of scaling the page's real point size down to the
handful of pixels a 300px-wide panel would give it. Relative column
positions are true; absolute text size is not.
"""

import tkinter as tk
import tkinter.font as tkFont
from typing import List, Optional, Sequence, Tuple

import customtkinter as ctk

from utils import ui_theme

# The preview stands in for the bottom band of a Letter page.
_PAGE_W_PT = 612.0
_SIDE_MARGIN_PT = 36.0
_MIN_TEXT_PX = 7
_MAX_TEXT_PX = 11


class FooterMiniPreview(ctk.CTkFrame):
    """Draws the footer band; call update_preview() whenever the fields change."""

    HEIGHT = 78

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)

        self.canvas = tk.Canvas(self, height=self.HEIGHT, highlightthickness=0,
                                 bg=ui_theme.resolve(ui_theme.BG_SUBTLE), bd=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

        self._columns: List[Tuple[str, str]] = []
        self._font_name = "Helvetica"
        self._font_size = 13
        self._line_gap = 4.0
        self._page_num = 1
        self._total_pages = 1

    # ---------------------------------------------------------------- API

    def update_preview(self, columns: Sequence[Tuple[str, str]], font_name: str,
                        font_size: int, line_gap: float,
                        page_num: int = 1, total_pages: int = 1):
        self._columns = [(l1 or "", l2 or "") for l1, l2 in columns]
        self._font_name = font_name or "Helvetica"
        self._font_size = max(1, int(font_size or 1))
        self._line_gap = float(line_gap or 0)
        self._page_num = page_num
        self._total_pages = max(1, total_pages)
        self._redraw()

    # ---------------------------------------------------------------- drawing

    def _resolve(self, text: str) -> str:
        return (text.replace("{page}", str(self._page_num))
                     .replace("{total}", str(self._total_pages)))

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        width = c.winfo_width()
        if width <= 1:
            return
        height = self.HEIGHT

        # The page surface itself stays white in both themes -- it stands
        # in for paper, not for app chrome.
        pad = 6
        page_x0, page_x1 = pad, width - pad
        page_y0, page_y1 = 4, height - 4
        c.create_rectangle(page_x0, page_y0, page_x1, page_y1,
                            fill="#FFFFFF", outline=ui_theme.resolve(ui_theme.BORDER_STRONG))

        page_w = page_x1 - page_x0
        scale = page_w / _PAGE_W_PT
        margin_px = _SIDE_MARGIN_PT * scale

        # "Page content ends here" rule -- the footer sits below it.
        rule_y = page_y0 + 16
        c.create_line(page_x0 + margin_px, rule_y, page_x1 - margin_px, rule_y,
                       fill="#C9CDD3", dash=(3, 3))
        c.create_text(page_x0 + margin_px, rule_y - 6, anchor="w", text="page content",
                       fill="#B0B5BC", font=(ui_theme.FONT_FAMILY, 7))

        resolved = [(self._resolve(l1), self._resolve(l2)) for l1, l2 in self._columns]
        has_text = any(l1.strip() or l2.strip() for l1, l2 in resolved)
        if not has_text:
            c.create_text((page_x0 + page_x1) / 2, (rule_y + page_y1) / 2,
                           text="Footer text you enter below appears here",
                           fill="#A8ADB4", font=(ui_theme.FONT_FAMILY, 8))
            return

        ncols = len(resolved)
        col_w = (page_w - 2 * margin_px) / ncols

        # Legible stand-in size: scale the real point size, then clamp --
        # and shrink further if a column's text still overruns its share.
        text_px = max(_MIN_TEXT_PX, min(_MAX_TEXT_PX, round(self._font_size * scale * 1.7)))
        family = self._font_name if self._font_name in tkFont.families() else ui_theme.FONT_FAMILY
        text_px = self._fit_to_columns(resolved, family, text_px, col_w)
        gap_px = max(1, round(self._line_gap * scale * 1.7))

        line1_y = page_y1 - 8 - text_px - gap_px
        line2_y = page_y1 - 8

        for i, (line1, line2) in enumerate(resolved):
            x_center = page_x0 + margin_px + i * col_w + col_w / 2.0
            if i:  # faint guide between columns, so the structure reads
                divider_x = page_x0 + margin_px + i * col_w
                c.create_line(divider_x, rule_y + 6, divider_x, page_y1 - 4,
                               fill="#EDEFF2")
            if line1:
                c.create_text(x_center, line1_y, text=line1, fill="#1A1D21",
                               font=(family, text_px), anchor="s")
            if line2:
                c.create_text(x_center, line2_y, text=line2, fill="#1A1D21",
                               font=(family, text_px), anchor="s")

    def _fit_to_columns(self, items, family: str, start_px: int, col_w: float) -> int:
        """Shrink uniformly until the widest column's text fits its share
        -- the same "no overlapping neighbours" rule the real footer
        generator applies, so the preview doesn't promise a layout that
        export would silently shrink."""
        limit = max(8.0, col_w - 6)
        size = start_px
        while size > _MIN_TEXT_PX:
            try:
                measure = tkFont.Font(family=family, size=size).measure
            except tk.TclError:
                return size
            if all(measure(t) <= limit for pair in items for t in pair if t):
                return size
            size -= 1
        return _MIN_TEXT_PX
