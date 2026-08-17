"""
Document export engine: whitespace-aware, page-by-page PDF generation.

Unlike FooterGenerator.add_footer_to_pdf (the legacy, CLI-compatible path
which applies one flat footer to every page), DocumentExporter walks a
Document's per-page configuration so:

- each page can have its own footer text/font/columns (or none at all)
- each page is checked independently for whether it has enough bottom
  white-space for its own footer, using WhiteSpaceDetector
- pages that lack space receive a per-page vertical compression so the
  original content is scaled up to fit above the footer -- there is no
  single global shrink percentage; every page is handled independently
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

# Extra breathing room between the top of the footer block and the last
# line of page content, so they never sit flush against each other.
SAFETY_GAP_PT = 6.0

# Minimum physical distance from the page's bottom edge to the footer's
# lower edge.  18 pt ≈ ¼ inch -- well inside the printable area of even
# the most conservative laser/inkjet printers.
FOOTER_PHYSICAL_MARGIN_PT = 18.0


def compute_content_relative_bottom_margin(page_height_pt: float, analysis,
                                            configured_gap_pt: float,
                                            font_size_pt: float, line_gap_pt: float,
                                            safety_gap_pt: float = SAFETY_GAP_PT,
                                            physical_margin_pt: float = FOOTER_PHYSICAL_MARGIN_PT) -> float:
    """Physical renderer bottom_margin (distance from page bottom to footer's
    lower edge) that places the footer's visual top exactly configured_gap_pt
    below the page's actual content bottom, while keeping the footer at least
    physical_margin_pt away from the physical page edge (printer safety zone).

    Two concepts are explicitly separated:
      - configured_gap_pt  : gap between content bottom and footer top (user setting)
      - renderer_bottom_margin : physical distance from page bottom to footer bottom
        (computed; always >= physical_margin_pt so text is never in the gutter)

    In the shrink case (insufficient whitespace), returns physical_margin_pt so
    the footer sits at the printer-safe minimum position after the content
    transform is applied by _apply_whitespace_adjustment.

    Falls back to configured_gap_pt when whitespace analysis is unavailable.
    """
    if analysis is None:
        return configured_gap_pt

    content_bottom_pt = page_height_pt * (analysis.bottom_margin / 100.0)
    footer_block_height_pt = 2 * font_size_pt + line_gap_pt + safety_gap_pt
    # Include physical_margin_pt in required_height so the no-shrink formula
    # automatically guarantees renderer_bottom_margin >= physical_margin_pt.
    required_height = configured_gap_pt + footer_block_height_pt + physical_margin_pt

    if content_bottom_pt < required_height:
        # Shrink case: export will compress content; footer at printer-safe minimum.
        return physical_margin_pt

    # No-shrink case: float the footer just below actual content.
    # renderer_bottom_margin = content_bottom - configured_gap - footer_block
    # which equals physical_margin_pt + (content_bottom - required_height),
    # guaranteed >= physical_margin_pt since content_bottom >= required_height here.
    candidate = content_bottom_pt - required_height  # >= 0
    return physical_margin_pt + candidate


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
        """Decide whether this page needs content compression to fit its footer.

        When the page already has enough white-space below its content the
        footer is placed dynamically close to that content (content-relative
        placement) without touching the page at all.

        When the content extends into the footer zone (deficit > 0) the page
        content stream is scaled vertically and shifted up so the content
        bottom lands exactly at the top of the footer zone, then the footer
        overlay is placed at the configured bottom_margin as normal. The
        overlay is appended after the transformed content stream, so it is
        never affected by the transform.
        """
        required_height = (footer_config.bottom_margin
                            + 2 * footer_config.font_size
                            + footer_config.line_gap
                            + SAFETY_GAP_PT
                            + FOOTER_PHYSICAL_MARGIN_PT)

        analysis = detector.analyze_page(page_num)

        if analysis is None:
            result.per_page_notes[page_num] = (
                f"Page {page_num}: whitespace analysis unavailable; "
                f"footer placed at configured margin."
            )
            return footer_config.bottom_margin

        available_pts = (analysis.bottom_margin / 100.0) * page_h
        deficit = required_height - available_pts

        if deficit <= 0:
            # Enough room: place footer just below the actual content.
            effective_margin = compute_content_relative_bottom_margin(
                page_h, analysis, footer_config.bottom_margin,
                footer_config.font_size, footer_config.line_gap)
            result.per_page_notes[page_num] = (
                f"Sufficient space (required {required_height:.0f}pt, "
                f"available {available_pts:.0f}pt). "
                f"Footer placed at {effective_margin:.0f}pt from bottom."
            )
            return effective_margin

        if not getattr(footer_config, 'compress_content', True):
            # Compression disabled: place footer at the content-relative position
            # even if it overlaps -- the user has explicitly opted out of shrinking.
            effective_margin = compute_content_relative_bottom_margin(
                page_h, analysis, footer_config.bottom_margin,
                footer_config.font_size, footer_config.line_gap)
            result.per_page_notes[page_num] = (
                f"Page {page_num}: compression disabled; footer placed at "
                f"{effective_margin:.0f}pt (deficit {deficit:.0f}pt ignored)."
            )
            return effective_margin

        # Deficit: content overlaps the footer zone.
        # Apply MINIMUM-necessary vertical compression so the actual content
        # bottom (at available_pts from the page bottom) is lifted exactly to
        # required_height, leaving the configured gap between it and the footer.
        #
        # Minimum compression anchors the page TOP at page_h (page top stays):
        #   scale_y = (page_h - required_height) / (page_h - available_pts)
        #   translate_y = page_h * (1 - scale_y)
        #
        # Verification:
        #   y=available_pts → scale_y*available_pts + translate_y = required_height ✓
        #   y=page_h        → scale_y*page_h + translate_y = page_h              ✓
        #
        # This is strictly less aggressive than the naïve formula
        # ratio=(page_h-required_height)/page_h which anchors at y=0 and
        # over-compresses pages that have whitespace at the bottom.
        #
        # The overlay is appended after the transformed content stream, so the
        # footer sits at absolute page coordinates, unaffected by the transform.
        denominator = page_h - available_pts
        if denominator <= 0:
            # Guard: page is all blank (unreachable when deficit>0, but be safe).
            result.per_page_notes[page_num] = (
                f"Page {page_num}: all-blank page, no compression needed."
            )
            return footer_config.bottom_margin

        scale_y = (page_h - required_height) / denominator
        if scale_y <= 0:
            result.warnings.append(
                f"Page {page_num}: footer height ({required_height:.0f}pt) equals or "
                f"exceeds page height ({page_h:.0f}pt) — no transform applied."
            )
            result.per_page_notes[page_num] = (
                f"Page {page_num}: cannot compress — required_height ({required_height:.0f}pt) "
                f">= page_h ({page_h:.0f}pt)."
            )
            return footer_config.bottom_margin

        translate_y = page_h * (1.0 - scale_y)
        page.add_transformation(
            Transformation().scale(1, scale_y).translate(0, translate_y)
        )
        result.adjusted_pages.append(page_num)
        result.per_page_notes[page_num] = (
            f"Page {page_num}: content compressed {(1 - scale_y) * 100:.1f}% vertically "
            f"to clear footer zone "
            f"(content_bottom {available_pts:.0f}pt → {required_height:.0f}pt, "
            f"deficit {deficit:.0f}pt, scale_y {scale_y:.4f})."
        )
        # After the transform, content bottom is at y=required_height from page bottom.
        # Footer placed at FOOTER_PHYSICAL_MARGIN_PT from the page edge so the text
        # stays within the printer's printable area.  The gap between content bottom
        # (y=required_height) and footer visual top (≈ FOOTER_PHYSICAL_MARGIN_PT +
        # footer_block_height) equals the configured content_gap_pt. ✓
        return FOOTER_PHYSICAL_MARGIN_PT
