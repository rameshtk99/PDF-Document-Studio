"""
Live footer preview overlay -- draws the footer text on top of the PDF
canvas using the exact same column-layout math as
FooterGenerator.create_footer_overlay (left/right margin, line gap,
per-column centering, {page}/{total} substitution) plus the same
content-relative bottom-margin logic as DocumentExporter
(compute_content_relative_bottom_margin), so what's shown here matches
what export would actually produce -- without writing anything to disk.

By default (no active "draft"), redraw() shows whatever footer is
already committed to the Document for the visible page
(document.get_page_config(page).footer_config). While the user is
actively typing in a footer panel, that panel pushes a temporary
"draft" override via set_draft() so they see their in-progress edit
live; clearing the draft (on Apply, on page change, or after an
undo/redo) falls back to showing the real, currently-committed state
again.
"""

import tkinter as tk
import tkinter.font as tkFont
from typing import Optional

from models import FooterConfig
from pdf.white_space_detector import WhiteSpaceDetector
from pdf.document_exporter import (compute_content_relative_bottom_margin,
                                    SAFETY_GAP_PT, FOOTER_PHYSICAL_MARGIN_PT)


class FooterPreviewController:
    def __init__(self, pdf_viewer):
        self.pdf_viewer = pdf_viewer
        self.draft_config: Optional[FooterConfig] = None
        self.draft_page: Optional[int] = None
        self._detector: Optional[WhiteSpaceDetector] = None
        self._detector_path: Optional[str] = None

    def set_draft(self, footer_config: FooterConfig, page_number: int):
        self.draft_config = footer_config
        self.draft_page = page_number
        self.redraw()

    def clear_draft(self):
        self.draft_config = None
        self.draft_page = None
        self.redraw()

    def redraw(self):
        canvas = self.pdf_viewer.canvas
        canvas.delete("footer_preview")

        doc = self.pdf_viewer.document
        if not doc:
            return

        current_page = self.pdf_viewer.current_page
        if self.draft_config is not None and self.draft_page == current_page:
            cfg = self.draft_config
        else:
            cfg = doc.get_page_config(current_page).footer_config

        if not cfg or not cfg.enabled:
            return

        scale = self.pdf_viewer.get_page_to_screen_scale()
        page_h = self.pdf_viewer.get_current_page_height_pt()
        page_w = self._current_page_width_pt()
        if not scale or not page_h or not page_w:
            return

        footer_items = [(l1, l2) for (l1, l2) in cfg.text_columns if (l1 or l2)]
        if not footer_items:
            return

        ncols = len(footer_items)
        avail_w = page_w - cfg.left_margin - cfg.right_margin
        if avail_w <= 0:
            return
        col_w = avail_w / ncols

        total_pages = doc.page_count
        resolved_items = [
            (l1.replace("{page}", str(current_page)).replace("{total}", str(total_pages)),
             l2.replace("{page}", str(current_page)).replace("{total}", str(total_pages)))
            for l1, l2 in footer_items
        ]

        # Match FooterGenerator.create_footer_overlay's auto-shrink: a
        # column's word (e.g. a long Devanagari committee title) can
        # easily be wider than its equal-share column at the configured
        # size, so find the largest size that actually fits before
        # drawing -- otherwise adjacent columns' text visibly overlaps.
        configured_size_px = max(6, round(cfg.font_size * scale))
        col_w_px = col_w * scale
        fitted_size_px = self._fit_font_size_px(resolved_items, cfg.font_name,
                                                 configured_size_px, col_w_px)
        fitted_size_pt = (fitted_size_px / scale) if scale else cfg.font_size

        bottom_margin, will_compress = self._effective_bottom_margin(
            doc, current_page, page_h, cfg, fitted_size_pt)
        y_line2 = bottom_margin + fitted_size_pt
        y_line1 = y_line2 + fitted_size_pt + cfg.line_gap

        off_x, off_y = self.pdf_viewer.get_render_offset()
        font_obj = self._resolve_font(cfg.font_name, fitted_size_px)

        for i, (line1, line2) in enumerate(resolved_items):
            x_center_pt = cfg.left_margin + (i * col_w) + col_w / 2.0

            cx = x_center_pt * scale + off_x
            cy1 = (page_h - y_line1) * scale + off_y
            cy2 = (page_h - y_line2) * scale + off_y

            # Black -- this is meant to be a WYSIWYG preview of the actual
            # (black) exported text, not a "this is a preview" color cue.
            if line1:
                canvas.create_text(cx, cy1, text=line1, fill='black',
                                    font=font_obj, tags="footer_preview")
            if line2:
                canvas.create_text(cx, cy2, text=line2, fill='black',
                                    font=font_obj, tags="footer_preview")

        # Dashed outline marks this as a preview.
        # Orange = export will compress this page's content to fit the footer.
        # Blue   = content already has enough whitespace; no compression needed.
        box_color = '#cc6600' if will_compress else '#0066cc'
        top_y = (page_h - (y_line1 + fitted_size_pt)) * scale + off_y
        bottom_y = (page_h - bottom_margin + fitted_size_pt) * scale + off_y
        left_x = cfg.left_margin * scale + off_x
        right_x = (page_w - cfg.right_margin) * scale + off_x
        canvas.create_rectangle(left_x, top_y, right_x, bottom_y, outline=box_color,
                                 dash=(3, 2), tags="footer_preview")
        if will_compress:
            label_x = (left_x + right_x) / 2
            label_y = top_y - 10
            canvas.create_text(label_x, label_y,
                                text="⚠ page will be compressed on export",
                                fill=box_color, font=('TkDefaultFont', 8),
                                tags="footer_preview")

    def _fit_font_size_px(self, resolved_items, font_name: str, configured_size_px: int,
                           col_w_px: float, min_size_px: int = 6, padding_px: float = 4.0) -> int:
        texts = [t for l1, l2 in resolved_items for t in (l1, l2) if t]
        if not texts:
            return configured_size_px

        family = font_name if font_name in tkFont.families() else 'Helvetica'
        usable_px = max(1.0, col_w_px - padding_px)
        size = configured_size_px
        while size > min_size_px:
            f = tkFont.Font(family=family, size=size)
            if all(f.measure(t) <= usable_px for t in texts):
                return size
            size -= 1
        return min_size_px

    def _effective_bottom_margin(self, doc, page_number: int, page_h: float,
                                  cfg: FooterConfig,
                                  rendered_font_size_pt: float) -> tuple:
        """Return (renderer_bottom_margin, will_compress).

        Mirrors DocumentExporter's two-path logic:
          - No-shrink: footer floats just below content, will_compress=False.
          - Shrink: footer at page bottom (0.0), will_compress=True so the
            caller can draw a warning indicator in the preview.
        """
        try:
            detector = self._get_detector(doc.pdf_path)
            analysis = detector.analyze_page(page_number)
        except Exception:
            analysis = None

        if analysis is not None:
            available_pts = page_h * (analysis.bottom_margin / 100.0)
            required_height = (cfg.bottom_margin
                                + 2 * rendered_font_size_pt
                                + cfg.line_gap
                                + SAFETY_GAP_PT
                                + FOOTER_PHYSICAL_MARGIN_PT)
            compress = getattr(cfg, 'compress_content', True)
            if available_pts < required_height and compress:
                return FOOTER_PHYSICAL_MARGIN_PT, True

        margin = compute_content_relative_bottom_margin(
            page_h, analysis, cfg.bottom_margin, rendered_font_size_pt, cfg.line_gap)
        return margin, False

    def _get_detector(self, pdf_path: str) -> WhiteSpaceDetector:
        if self._detector is None or self._detector_path != pdf_path:
            self._detector = WhiteSpaceDetector(pdf_path)
            self._detector_path = pdf_path
        return self._detector

    @staticmethod
    def _resolve_font(font_name: str, size_px: int) -> tkFont.Font:
        family = font_name if font_name in tkFont.families() else 'Helvetica'
        try:
            return tkFont.Font(family=family, size=size_px)
        except tk.TclError:
            return tkFont.Font(family='Helvetica', size=size_px)

    def _current_page_width_pt(self) -> Optional[float]:
        doc = self.pdf_viewer.document
        if not doc or not doc.metadata:
            return None
        pages = doc.metadata.get('pages', [])
        idx = self.pdf_viewer.current_page - 1
        if 0 <= idx < len(pages):
            return pages[idx]['width']
        return None
