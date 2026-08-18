"""
PDF handling - reading, writing, overlay generation and merging
"""

import os
from io import BytesIO
from utils.fonts import get_reportlab_font
from utils.geometry import rotated_bbox_size

# Lazy imports
_PdfReader = None
_PdfWriter = None
_canvas = None
_ImageReader = None


def ensure_pdf_libraries():
    """Ensure PDF libraries are available"""
    global _PdfReader, _PdfWriter, _canvas, _ImageReader

    if _PdfReader is None:
        try:
            from pypdf import PdfReader, PdfWriter
            _PdfReader = PdfReader
            _PdfWriter = PdfWriter
        except ImportError:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                _PdfReader = PdfReader
                _PdfWriter = PdfWriter
            except ImportError:
                raise RuntimeError("pypdf or PyPDF2 is required for PDF handling")

    if _canvas is None:
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            _canvas = canvas
            _ImageReader = ImageReader
        except ImportError:
            raise RuntimeError("reportlab is required for PDF processing")


class PDFHandler:
    """Handle PDF operations"""
    
    @staticmethod
    def load_pdf(pdf_path):
        """
        Load a PDF file
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            PdfReader instance
            
        Raises:
            IOError: If file cannot be read
            RuntimeError: If PDF is invalid
        """
        ensure_pdf_libraries()
        
        try:
            reader = _PdfReader(pdf_path)
            return reader
        except Exception as e:
            raise RuntimeError(f"Failed to load PDF: {e}")
    
    @staticmethod
    def get_pdf_metadata(reader):
        """
        Extract PDF metadata
        
        Args:
            reader: PdfReader instance
            
        Returns:
            Dictionary with metadata
        """
        try:
            page_count = len(reader.pages)
            first_page = reader.pages[0] if page_count > 0 else None
            
            metadata = {
                'page_count': page_count,
                'is_encrypted': reader.is_encrypted if hasattr(reader, 'is_encrypted') else False,
            }
            
            if first_page:
                mediabox = first_page.mediabox
                metadata['first_page_width'] = float(mediabox[2]) - float(mediabox[0])
                metadata['first_page_height'] = float(mediabox[3]) - float(mediabox[1])
                metadata['first_page_rotation'] = first_page.get('/Rotate', 0)
            
            return metadata
        except Exception as e:
            raise RuntimeError(f"Failed to extract PDF metadata: {e}")
    
    @staticmethod
    def get_page_dimensions(page):
        """
        Get page dimensions from a PDF page
        
        Args:
            page: PDF page object
            
        Returns:
            Tuple of (width, height) in points
        """
        mediabox = page.mediabox
        width = float(mediabox[2]) - float(mediabox[0])
        height = float(mediabox[3]) - float(mediabox[1])
        return width, height


class FooterGenerator:
    """Generate footer overlays"""
    
    @staticmethod
    def create_footer_overlay(page_width, page_height, footer_items,
                             page_num, total_pages,
                             left_margin=36, right_margin=36, bottom_margin=24,
                             font='Helvetica', size1=13, size2=13, line_gap=4,
                             image_objects=None):
        """
        Generate a footer overlay as a PDF stream

        Args:
            page_width: Page width in points
            page_height: Page height in points
            footer_items: List of (line1, line2) tuples for each column
            page_num: Current page number
            total_pages: Total number of pages
            left_margin: Left margin in points
            right_margin: Right margin in points
            bottom_margin: Bottom margin in points
            font: Font name
            size1: Font size for line 1
            size2: Font size for line 2
            line_gap: Gap between lines
            image_objects: Optional list of PageObject (type='image') to draw
                onto this page's overlay, in addition to the footer text.
                Defaults to None (no images) for full backward compatibility.

        Returns:
            BytesIO stream containing overlay PDF
        """
        ensure_pdf_libraries()

        if _canvas is None:
            raise RuntimeError("reportlab is not available")

        packet = BytesIO()
        c = _canvas.Canvas(packet, pagesize=(page_width, page_height))

        if footer_items:
            ncols = len(footer_items)
            avail_w = page_width - left_margin - right_margin
            col_w = avail_w / ncols

            # Substitute placeholders first so the fitted size accounts for
            # the real rendered text (e.g. "{total}" expanding to "32").
            resolved_items = [
                (l1.replace("{page}", str(page_num)).replace("{total}", str(total_pages)),
                 l2.replace("{page}", str(page_num)).replace("{total}", str(total_pages)))
                for l1, l2 in footer_items
            ]

            # A column's word (e.g. a long Devanagari committee title)
            # can easily be wider than its equal-share column width at
            # the configured size -- shrink uniformly across the whole
            # footer row until every column's text actually fits, rather
            # than letting neighboring columns' text overlap.
            fitted_size = FooterGenerator._fit_footer_font_size(
                resolved_items, font, max(size1, size2), col_w)
            size1 = min(size1, fitted_size)
            size2 = min(size2, fitted_size)

            y_line2 = bottom_margin + size2
            y_line1 = y_line2 + size2 + line_gap

            for i, (line1, line2) in enumerate(resolved_items):
                x_center = left_margin + (i * col_w) + col_w / 2.0

                c.setFont(font, size1)
                c.drawCentredString(x_center, y_line1, line1)
                c.setFont(font, size2)
                c.drawCentredString(x_center, y_line2, line2)

        if image_objects:
            for obj in sorted(image_objects, key=lambda o: o.z_index):
                FooterGenerator._draw_image_object(c, obj)

        c.save()
        packet.seek(0)
        return packet

    @staticmethod
    def _fit_footer_font_size(resolved_items, font_name, configured_size, col_w,
                               min_size=6, padding_pt=4.0):
        """Largest font size <= configured_size (and >= min_size) at which
        every non-empty column line fits within its column width, so
        long words (e.g. multi-syllable Devanagari titles) never overlap
        into a neighboring column. Falls back to min_size if nothing fits
        even at the floor -- still readable-ish rather than crashing."""
        from reportlab.pdfbase.pdfmetrics import stringWidth

        texts = [t for l1, l2 in resolved_items for t in (l1, l2) if t]
        if not texts:
            return configured_size

        usable_w = max(1.0, col_w - padding_pt)
        size = int(configured_size)
        while size > min_size:
            if all(stringWidth(t, font_name, size) <= usable_w for t in texts):
                return size
            size -= 1
        return min_size
        packet.seek(0)
        return packet

    @staticmethod
    def _draw_image_object(c, obj):
        """Draw a single image PageObject onto an in-progress reportlab canvas.

        Geometry mirrors app/image_overlay.py's on-screen preview exactly,
        via the shared utils/geometry helpers: the source image is
        rasterized at its true LOCAL (un-rotated) size first, then -- only
        if rotated -- rotated with expand=True (no corners clipped, no
        shrink-to-refit into the original box) and drawn at its analytic
        rotated bounding-box size, centered on the object's center. There
        is intentionally no separate/alternate rotation math for export;
        this is the same shape the editor already showed the user.

        Silently skips objects that are invisible, missing an image path,
        or whose file cannot be opened -- an image problem must never abort
        the whole export.
        """
        if not getattr(obj, 'visible', True):
            return

        image_path = (obj.properties or {}).get('image_path', '')
        if not image_path or not os.path.exists(image_path):
            return

        try:
            from PIL import Image
            pil_img = Image.open(image_path).convert('RGBA')

            opacity = max(0.0, min(100.0, getattr(obj, 'opacity', 100.0)))
            if opacity < 100.0:
                alpha = pil_img.split()[3].point(lambda p: int(p * opacity / 100.0))
                pil_img.putalpha(alpha)

            rotation = getattr(obj, 'rotation', 0.0)
            box_w, box_h = obj.width, obj.height
            if rotation:
                # Rasterize at the object's true local (un-rotated) size at a
                # fixed density -- export quality only, not related to the
                # PDF-point geometry -- then rotate losslessly.
                px_per_pt = 4.0
                local_w_px = max(1, round(box_w * px_per_pt))
                local_h_px = max(1, round(box_h * px_per_pt))
                pil_img = pil_img.resize((local_w_px, local_h_px), Image.LANCZOS)
                pil_img = pil_img.rotate(-rotation, expand=True, resample=Image.BICUBIC)

                rot_w_pt, rot_h_pt = rotated_bbox_size(box_w, box_h, rotation)
                draw_x = obj.x + box_w / 2.0 - rot_w_pt / 2.0
                draw_y = obj.y + box_h / 2.0 - rot_h_pt / 2.0
                c.drawImage(_ImageReader(pil_img), draw_x, draw_y, rot_w_pt, rot_h_pt, mask='auto')
            else:
                c.drawImage(_ImageReader(pil_img), obj.x, obj.y, obj.width, obj.height, mask='auto')
        except Exception as e:
            print(f"Warning: could not draw image object {getattr(obj, 'id', '?')} "
                  f"({image_path}): {e}")
    
    @staticmethod
    def add_footer_to_pdf(input_pdf_path, output_pdf_path, footer_items, 
                         font_name='Helvetica', font_size=13,
                         left_margin=36, right_margin=36, bottom_margin=24, line_gap=4):
        """
        Add footer to all pages of a PDF
        
        Args:
            input_pdf_path: Path to input PDF
            output_pdf_path: Path to output PDF
            footer_items: List of (line1, line2) tuples for each column
            font_name: Display font name (will be mapped)
            font_size: Font size
            left_margin: Left margin in points
            right_margin: Right margin in points
            bottom_margin: Bottom margin in points
            line_gap: Gap between lines
        """
        ensure_pdf_libraries()
        
        reader = PDFHandler.load_pdf(input_pdf_path)
        writer = _PdfWriter()
        total = len(reader.pages)
        
        # Map the font name for ReportLab
        mapped_font = get_reportlab_font(font_name)
        
        for idx, page in enumerate(reader.pages):
            page_w, page_h = PDFHandler.get_page_dimensions(page)
            
            # Generate footer overlay
            overlay_stream = FooterGenerator.create_footer_overlay(
                page_w, page_h, footer_items, idx + 1, total,
                left_margin=left_margin, right_margin=right_margin,
                bottom_margin=bottom_margin,
                font=mapped_font, size1=font_size, size2=font_size,
                line_gap=line_gap
            )
            
            # Merge overlay with page
            overlay_pdf = _PdfReader(overlay_stream)
            overlay_page = overlay_pdf.pages[0]
            page.merge_page(overlay_page)
            writer.add_page(page)
        
        # Write output
        with open(output_pdf_path, "wb") as f_out:
            writer.write(f_out)
