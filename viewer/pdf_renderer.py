"""
PDF rendering - Convert PDF pages to displayable images

Supports multiple rendering backends:
1. PyMuPDF (fitz) - Fast, high quality (recommended)
2. pdf2image + Poppler - Good quality
3. PIL rendering fallback - Limited but works
"""

import os
from typing import Optional, Tuple, List
from io import BytesIO
import PIL.Image
import PIL.ImageDraw

# Lazy imports for rendering backends
_fitz = None
_fitz_available = False
_pdf2image_available = False


def ensure_fitz():
    """Ensure PyMuPDF (fitz) is available"""
    global _fitz, _fitz_available
    if _fitz is None:
        try:
            import fitz
            _fitz = fitz
            _fitz_available = True
            return True
        except ImportError:
            _fitz_available = False
            return False
    return _fitz_available


def ensure_pdf2image():
    """Ensure pdf2image is available"""
    global _pdf2image_available
    try:
        import pdf2image
        _pdf2image_available = True
        return True
    except ImportError:
        _pdf2image_available = False
        return False


class PDFRenderer:
    """Render PDF pages to images"""
    
    @staticmethod
    def get_rendering_backend() -> str:
        """
        Determine which rendering backend is available
        
        Returns:
            'fitz', 'pdf2image', or 'none'
        """
        if ensure_fitz():
            return 'fitz'
        elif ensure_pdf2image():
            return 'pdf2image'
        else:
            return 'none'
    
    @staticmethod
    def render_page_fitz(pdf_path: str, page_num: int, zoom: float = 1.0,
                         dpi: int = 150) -> Optional[PIL.Image.Image]:
        """
        Render a PDF page using PyMuPDF (fitz)
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-based)
            zoom: Zoom factor (1.0 = 100%)
            dpi: Dots per inch for rendering
            
        Returns:
            PIL Image object or None if failed
        """
        if not ensure_fitz():
            return None
        
        try:
            # Open PDF
            doc = _fitz.open(pdf_path)
            
            # Get page (0-based in fitz)
            if page_num < 1 or page_num > len(doc):
                return None
            
            page = doc[page_num - 1]

            # Render to image. fitz's native matrix scale is 1 unit = 1
            # PDF point (i.e. a 72 DPI render at scale 1.0), so combine the
            # requested dpi with zoom to get the actual pixel scale --
            # every caller (fit-page/fit-width math, thumbnail sizing,
            # white-space analysis) assumes `dpi` controls resolution.
            scale = (dpi / 72.0) * zoom
            mat = _fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # pix.samples is the raw RGB pixel buffer (no header), unlike
            # pix.tobytes("ppm") which prepends a PPM header that must not
            # be fed directly to Image.frombytes. Also note pix.n is the
            # channel count (3 for RGB), not the image width.
            img = PIL.Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            doc.close()
            return img
            
        except Exception as e:
            print(f"Error rendering page with fitz: {e}")
            return None
    
    @staticmethod
    def render_page_pdf2image(pdf_path: str, page_num: int,
                              dpi: int = 150) -> Optional[PIL.Image.Image]:
        """
        Render a PDF page using pdf2image + Poppler
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-based)
            dpi: Dots per inch for rendering
            
        Returns:
            PIL Image object or None if failed
        """
        if not ensure_pdf2image():
            return None
        
        try:
            from pdf2image import convert_from_path
            
            images = convert_from_path(pdf_path, first_page=page_num,
                                      last_page=page_num, dpi=dpi)
            
            if images:
                return images[0]
            return None
            
        except Exception as e:
            print(f"Error rendering page with pdf2image: {e}")
            return None
    
    @staticmethod
    def render_page(pdf_path: str, page_num: int, zoom: float = 1.0,
                    dpi: int = 150) -> Optional[PIL.Image.Image]:
        """
        Render a PDF page using the best available backend
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-based)
            zoom: Zoom factor (1.0 = 100%)
            dpi: Dots per inch for rendering
            
        Returns:
            PIL Image object or None if no backend available
        """
        backend = PDFRenderer.get_rendering_backend()
        
        if backend == 'fitz':
            return PDFRenderer.render_page_fitz(pdf_path, page_num, zoom, dpi)
        elif backend == 'pdf2image':
            # pdf2image doesn't support zoom directly, need to adjust DPI
            adjusted_dpi = int(dpi * zoom)
            return PDFRenderer.render_page_pdf2image(pdf_path, page_num, adjusted_dpi)
        else:
            print("No PDF rendering backend available. Install PyMuPDF or pdf2image.")
            return None
    
    @staticmethod
    def render_pages_fitz(pdf_path: str, page_numbers: List[int],
                          zoom: float = 1.0, dpi: int = 150) -> List[PIL.Image.Image]:
        """
        Render multiple PDF pages using PyMuPDF (efficient batch rendering)
        
        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers (1-based)
            zoom: Zoom factor
            dpi: Dots per inch
            
        Returns:
            List of PIL Image objects
        """
        if not ensure_fitz():
            return []
        
        images = []
        try:
            doc = _fitz.open(pdf_path)
            scale = (dpi / 72.0) * zoom
            mat = _fitz.Matrix(scale, scale)

            for page_num in page_numbers:
                if 1 <= page_num <= len(doc):
                    page = doc[page_num - 1]
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = PIL.Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    images.append(img)
            
            doc.close()
        except Exception as e:
            print(f"Error rendering pages: {e}")
        
        return images
    
    @staticmethod
    def create_placeholder_image(width: int = 600, height: int = 800,
                                 text: str = "PDF Preview") -> PIL.Image.Image:
        """
        Create a placeholder image when PDF rendering fails
        
        Args:
            width: Image width in pixels
            height: Image height in pixels
            text: Text to display
            
        Returns:
            PIL Image object
        """
        img = PIL.Image.new('RGB', (width, height), color='white')
        draw = PIL.ImageDraw.Draw(img)
        
        # Draw border
        draw.rectangle([0, 0, width-1, height-1], outline='gray')
        
        # Draw text
        text_bbox = draw.textbbox((0, 0), text)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        draw.text((x, y), text, fill='gray')
        
        return img
