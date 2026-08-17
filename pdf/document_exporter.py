"""
Document export engine: whitespace-aware, page-by-page PDF generation.

Unlike FooterGenerator.add_footer_to_pdf (the legacy, CLI-compatible path
which applies one flat footer to every page), DocumentExporter walks a
Document's per-page configuration so:

- each page can have its own footer text/font/columns (or none at all)
- each page is checked independently for whether it has enough bottom
  white-space for its own footer, using WhiteSpaceDetector
- only pages that actually lack space receive the minimum necessary
  layout adjustment -- there is no global shrink percentage
- image objects placed on a page are embedded into the real output PDF

This module never touches FooterGenerator.add_footer_to_pdf or the CLI
contract in batch/cli.py -- both keep working exactly as before.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from models.models import Document, FooterConfig
from pdf.pdf_handler import PDFHandler, FooterGenerator
from pdf.white_space_detector import WhiteSpaceDetector
from utils.fonts import get_reportlab_font

# Extra breathing room added on top of the raw footer text height, so the
# footer never sits flush against the last line of page content.
SAFETY_GAP_PT = 6.0

# Never compress a page's content by more than half, no matter how large
# the deficit -- beyond this point auto-adjustment stops being "safe".
MIN_ADJUSTMENT_RATIO = 0.5


def compute_content_relative_bottom_margin(page_height_pt: float, analysis,
                                            configured_gap_pt: float,
                                            font_size_pt: float, line_gap_pt: float,
                                            safety_gap_pt: float = SAFETY_GAP_PT) -> float:
    """Where the footer's `bottom_margin` term should actually be, so the
    footer's TOP edge sits `configured_gap_pt` below wherever the page's
    content ends -- not pinned to a fixed distance from the page's far
    bottom edge, which looks wrong on a page that's mostly blank (e.g.
    only the top 25% has content: the footer ends up stranded far below
    it with an awkward gap).

    `bottom_margin` measures from the page's absolute bottom edge (y=0)
    to just under line 2, but the footer block actually extends further
    up from there -- line 2's height, the line gap, line 1's height, and
    a safety buffer (mirroring the same `2*font_size + line_gap +
    safety_gap` term used to decide whether a page needs shrinking at
    all). That extra height has to be subtracted out here, otherwise the
    footer's top ends up sitting *inside* the content instead of below
    it by the intended gap -- this was tried without the subtraction
    first and produced exactly that overlap on pages with less spare
    white-space than others.

    When content already reaches close to the bottom, this collapses
    back to the same fixed, safe distance from the page's true bottom
    edge (content-bottom and page-bottom are nearly the same edge in
    that case), so dense pages are unaffected.
    """
    if analysis is None:
        return configured_gap_pt
    content_bottom_pt = page_height_pt * (analysis.bottom_margin / 100.0)
    footer_block_height_pt = 2 * font_size_pt + line_gap_pt + safety_gap_pt
    candidate = content_bottom_pt - configured_gap_pt - footer_block_height_pt
    return max(configured_gap_pt, candidate)

_PdfReader = None
_PdfWriter = None
_Transformation = None


def _ensure_pypdf():
    """Lazily resolve pypdf (preferred) or PyPDF2 (fallback) classes."""
    global _PdfReader, _PdfWriter, _Transformation
    if _PdfReader is None:
        try:
            from pypdf import PdfReader, PdfWriter, Transformation
        except ImportError:
            from PyPDF2 import PdfReader, PdfWriter, Transformation
        _PdfReader = PdfReader
        _PdfWriter = PdfWriter
        _Transformation = Transformation
    return _PdfReader, _PdfWriter, _Transformation


@dataclass
class ExportResult:
    """Outcome of a DocumentExporter.export() call, auditable per page."""
    output_path: str
    per_page_notes: Dict[int, str] = field(default_factory=dict)
    adjusted_pages: List[int] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DocumentExporter:
    """Exports a Document to a final PDF, processing every page
    independently (Section 2 of the design spec: page-by-page processing,
    never a single global rule).
    """

    def __init__(self, document: Document):
        self.document = document

    def export(self, output_path: str) -> ExportResult:
        doc = self.document
        PdfReader, PdfWriter, Transformation = _ensure_pypdf()

        reader = PDFHandler.load_pdf(doc.pdf_path)
        writer = PdfWriter()
        total = len(reader.pages)
        result = ExportResult(output_path=output_path)
        detector = WhiteSpaceDetector(doc.pdf_path)

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            page_config = doc.get_page_config(page_num)
            footer_config = page_config.footer_config or FooterConfig()
            page_w, page_h = PDFHandler.get_page_dimensions(page)

            footer_items = []
            if footer_config.enabled:
                footer_items = [(l1, l2) for (l1, l2) in footer_config.text_columns if (l1 or l2)]

            image_objects = [o for o in page_config.objects if o.type == 'image' and o.visible]

            effective_bottom_margin = footer_config.bottom_margin
            if footer_items:
                effective_bottom_margin = self._apply_whitespace_adjustment(
                    page, page_num, page_h, footer_config, page_config,
                    doc, detector, Transformation, result
                )

            if footer_items or image_objects:
                mapped_font = get_reportlab_font(footer_config.font_name)
                overlay_stream = FooterGenerator.create_footer_overlay(
                    page_w, page_h, footer_items, page_num, total,
                    left_margin=footer_config.left_margin,
                    right_margin=footer_config.right_margin,
                    bottom_margin=effective_bottom_margin,
                    font=mapped_font,
                    size1=footer_config.font_size,
                    size2=footer_config.font_size,
                    line_gap=footer_config.line_gap,
                    image_objects=image_objects,
                )
                overlay_pdf = PdfReader(overlay_stream)
                page.merge_page(overlay_pdf.pages[0])

            writer.add_page(page)

        with open(output_path, "wb") as f_out:
            writer.write(f_out)

        return result

    def _apply_whitespace_adjustment(self, page, page_num, page_h, footer_config,
                                      page_config, doc, detector, Transformation, result) -> float:
        """Decide whether this single page needs a minimum layout
        adjustment to fit its own footer, applying it in-place on `page`
        if so, and return the bottom margin the footer should actually be
        drawn at. Mutates `result` with an auditable note for this page.
        """
        required_height = (footer_config.bottom_margin
                            + 2 * footer_config.font_size
                            + footer_config.line_gap
                            + SAFETY_GAP_PT)

        analysis = detector.analyze_page(page_num)
        available_pts = 0.0
        if analysis is not None:
            available_pts = (analysis.bottom_margin / 100.0) * page_h

        deficit = required_height - available_pts

        if deficit <= 0:
            effective_margin = compute_content_relative_bottom_margin(
                page_h, analysis, footer_config.bottom_margin,
                footer_config.font_size, footer_config.line_gap)
            result.per_page_notes[page_num] = (
                f"Sufficient white-space (required {required_height:.0f}pt, "
                f"available {available_pts:.0f}pt) - no adjustment, "
                f"footer positioned {effective_margin:.0f}pt from bottom."
            )
            return effective_margin

        note = (f"Required {required_height:.0f}pt, available {available_pts:.0f}pt, "
                f"deficit {deficit:.0f}pt. ")

        can_adjust = page_config.auto_layout and doc.global_settings.allow_page_shrinking
        if not can_adjust:
            note += "Auto-adjustment disabled -- footer may overlap page content."
            result.warnings.append(
                f"Page {page_num}: insufficient white-space for footer and auto-adjustment is off."
            )
            result.per_page_notes[page_num] = note
            return footer_config.bottom_margin

        max_deficit = page_h * (1 - MIN_ADJUSTMENT_RATIO)
        applied_deficit = min(deficit, max_deficit)
        ratio = (page_h - applied_deficit) / page_h

        page.add_transformation(Transformation().scale(1, ratio).translate(0, applied_deficit))
        result.adjusted_pages.append(page_num)

        if applied_deficit < deficit:
            note += (f"Applied maximum safe adjustment ({applied_deficit:.0f}pt); "
                      f"footer may still be tight.")
            result.warnings.append(
                f"Page {page_num}: could not fully fit footer even at maximum safe shrinkage."
            )
        else:
            note += f"Applied minimum necessary layout adjustment ({applied_deficit:.0f}pt)."

        result.per_page_notes[page_num] = note
        return footer_config.bottom_margin
