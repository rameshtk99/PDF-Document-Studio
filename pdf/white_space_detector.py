"""
White-space detection algorithm for PDF pages

Analyzes PDF pages to determine content boundaries and safe shrinkage zones
for footer placement.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from PIL import Image
import numpy as np
from pathlib import Path

from viewer.pdf_renderer import PDFRenderer


@dataclass
class PageAnalysis:
    """Analysis results for a single page
    
    Attributes:
        page_number: Page number (1-indexed)
        top_margin: Safe white-space margin from top (percentage)
        bottom_margin: Safe white-space margin from bottom (percentage)
        left_margin: Safe white-space margin from left (percentage)
        right_margin: Safe white-space margin from right (percentage)
        safe_shrinkage_percent: Safe percentage to shrink page (without losing content)
        shrinkage_zone: Dict with 'top' and 'bottom' percentage values for shrinkage
        content_density: Percentage of page covered by content (0-100)
    """
    page_number: int
    top_margin: float
    bottom_margin: float
    left_margin: float
    right_margin: float
    safe_shrinkage_percent: float
    shrinkage_zone: Dict[str, float]
    content_density: float


class WhiteSpaceDetector:
    """Detects white-space and content boundaries in PDF pages
    
    Analyzes each page to determine:
    - Content boundaries (where actual content ends)
    - Safe white-space margins
    - Maximum safe shrinkage percentage
    - Optimal shrinkage zones
    
    This enables automatic footer placement without losing content.
    """
    
    def __init__(self, pdf_path: str, analysis_dpi: int = 150):
        """
        Initialize white-space detector
        
        Args:
            pdf_path: Path to PDF file
            analysis_dpi: DPI for rendering pages during analysis (higher = slower but more accurate)
        """
        self.pdf_path = pdf_path
        self.analysis_dpi = analysis_dpi
        self._analysis_cache: Dict[int, PageAnalysis] = {}
    
    def analyze_page(self, page_number: int) -> Optional[PageAnalysis]:
        """
        Analyze a page for white-space and content boundaries
        
        Args:
            page_number: Page number to analyze (1-indexed)
            
        Returns:
            PageAnalysis object with results, or None if analysis fails
        """
        # Validate page number
        if page_number < 1:
            return None
        
        # Check cache first
        if page_number in self._analysis_cache:
            return self._analysis_cache[page_number]
        
        try:
            # Render page for analysis
            image = self._render_page_for_analysis(page_number, dpi=self.analysis_dpi)
            if image is None:
                return None
            
            # Detect boundaries
            boundaries = self._detect_boundaries(image)
            
            # Calculate safe shrinkage
            shrinkage_data = self._calculate_safe_shrinkage(boundaries)
            
            # Analyze content density
            content_density = self._calculate_content_density(image)
            
            # Create analysis result
            analysis = PageAnalysis(
                page_number=page_number,
                top_margin=boundaries['top'],
                bottom_margin=boundaries['bottom'],
                left_margin=boundaries['left'],
                right_margin=boundaries['right'],
                safe_shrinkage_percent=shrinkage_data['total'],
                shrinkage_zone=shrinkage_data['zone'],
                content_density=content_density
            )
            
            # Cache result
            self._analysis_cache[page_number] = analysis
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing page {page_number}: {e}")
            return None
    
    def _render_page_for_analysis(self, page_number: int, dpi: int = 150) -> Optional[Image.Image]:
        """
        Render a page to image for analysis
        
        Args:
            page_number: Page number (1-indexed)
            dpi: Rendering DPI
            
        Returns:
            PIL Image object, or None if rendering fails
        """
        try:
            # Use PDFRenderer to render the page
            image = PDFRenderer.render_page(self.pdf_path, page_number, dpi=dpi)
            return image
        except Exception as e:
            print(f"Failed to render page {page_number}: {e}")
            return None
    
    def _detect_boundaries(self, image: Image.Image) -> Dict[str, float]:
        """
        Detect content boundaries in rendered image
        
        Scans the image to find where content exists and calculates
        white-space margins on all sides.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            Dict with 'top', 'bottom', 'left', 'right' margins (percentage)
        """
        # Convert to grayscale for analysis
        if image.mode != 'L':
            img_gray = image.convert('L')
        else:
            img_gray = image
        
        # Convert to numpy array
        img_array = np.array(img_gray)

        # Define "white" as high values (>240 in 0-255 range)
        # Content is darker pixels
        white_threshold = 240

        # A row/column counts as "content" once at least this fraction of
        # its pixels are dark -- NOT a row/column *average* dropping below
        # the threshold. A thin line of text only darkens a small slice of
        # a row's pixels, so its row-mean can stay above 240 (e.g.
        # verified: a 12pt text line's darkest rows average ~242-247,
        # still reading as "white" by a mean-based check) even though the
        # text is clearly present -- which made the detector think content
        # ended higher up the page than it actually did, letting anything
        # relying on this boundary (e.g. content-relative footer
        # placement) sit too close to, or overlap, real content.
        min_dark_fraction = 0.003

        height, width = img_array.shape

        row_dark_fraction = (img_array < white_threshold).mean(axis=1)
        col_dark_fraction = (img_array < white_threshold).mean(axis=0)

        content_rows = np.where(row_dark_fraction > min_dark_fraction)[0]
        content_cols = np.where(col_dark_fraction > min_dark_fraction)[0]

        top_row = int(content_rows[0]) if len(content_rows) else 0
        bottom_row = int(content_rows[-1]) if len(content_rows) else height - 1
        left_col = int(content_cols[0]) if len(content_cols) else 0
        right_col = int(content_cols[-1]) if len(content_cols) else width - 1
        
        # Calculate margins as percentages
        top_margin = (top_row / height) * 100
        bottom_margin = ((height - 1 - bottom_row) / height) * 100
        left_margin = (left_col / width) * 100
        right_margin = ((width - 1 - right_col) / width) * 100
        
        # Clamp values to reasonable ranges
        top_margin = max(0, min(100, top_margin))
        bottom_margin = max(0, min(100, bottom_margin))
        left_margin = max(0, min(100, left_margin))
        right_margin = max(0, min(100, right_margin))
        
        return {
            'top': top_margin,
            'bottom': bottom_margin,
            'left': left_margin,
            'right': right_margin
        }
    
    def _calculate_safe_shrinkage(self, boundaries: Dict[str, float]) -> Dict:
        """
        Calculate safe shrinkage percentage based on boundaries
        
        Determines how much the page can be shrunk vertically to add footer
        without losing content.
        
        Args:
            boundaries: Boundary values from _detect_boundaries
            
        Returns:
            Dict with 'total' (safe percentage) and 'zone' (shrinkage zone info)
        """
        # Safe shrinkage is limited by the smallest margin
        # (the margin with least white-space)
        
        # Focus on vertical shrinkage (for footer at bottom)
        bottom_available = boundaries['bottom']
        top_available = boundaries['top']
        
        # Safe shrinkage for footer is limited by bottom margin
        # But we also consider top margin for balanced approach
        
        # Conservative approach: use bottom margin, but cap at reasonable value
        safe_shrinkage = min(bottom_available, 15.0)  # Max 15% shrinkage
        
        # Ensure minimum safe value (at least try 2%)
        if safe_shrinkage < 2.0 and bottom_available > 0:
            safe_shrinkage = min(2.0, bottom_available)
        
        # Shrinkage zone shows where we can shrink from
        shrinkage_zone = {
            'top': 0.0,  # Don't shrink from top usually
            'bottom': safe_shrinkage  # Shrink from bottom for footer
        }
        
        return {
            'total': safe_shrinkage,
            'zone': shrinkage_zone
        }
    
    def _calculate_content_density(self, image: Image.Image) -> float:
        """
        Calculate what percentage of page is covered by content
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            Content density as percentage (0-100)
        """
        try:
            if image.mode != 'L':
                img_gray = image.convert('L')
            else:
                img_gray = image
            
            img_array = np.array(img_gray)
            
            # Count non-white pixels (content)
            white_threshold = 240
            content_pixels = np.sum(img_array < white_threshold)
            total_pixels = img_array.size
            
            density = (content_pixels / total_pixels) * 100
            return max(0, min(100, density))
            
        except Exception:
            return 50.0  # Default fallback
    
    def analyze_pdf(self, max_pages: Optional[int] = None) -> Dict[int, PageAnalysis]:
        """
        Analyze all pages in PDF (or up to max_pages)
        
        Args:
            max_pages: Maximum number of pages to analyze (None for all)
            
        Returns:
            Dict mapping page number to PageAnalysis
        """
        from pdf.pdf_loader import PDFLoader
        
        results = {}
        
        try:
            doc = PDFLoader.load_pdf(self.pdf_path)
            pages_to_analyze = doc.page_count
            
            if max_pages:
                pages_to_analyze = min(max_pages, pages_to_analyze)
            
            for page_num in range(1, pages_to_analyze + 1):
                analysis = self.analyze_page(page_num)
                if analysis:
                    results[page_num] = analysis
            
            return results
            
        except Exception as e:
            print(f"Error analyzing PDF: {e}")
            return results
    
    def clear_cache(self):
        """Clear cached analysis results"""
        self._analysis_cache.clear()
    
    def get_cache_info(self) -> Dict:
        """Get information about cached analyses
        
        Returns:
            Dict with cache statistics
        """
        return {
            'cached_pages': list(self._analysis_cache.keys()),
            'cache_size': len(self._analysis_cache),
            'pages_data': {
                page_num: {
                    'shrinkage': analysis.safe_shrinkage_percent,
                    'content_density': analysis.content_density
                }
                for page_num, analysis in self._analysis_cache.items()
            }
        }
