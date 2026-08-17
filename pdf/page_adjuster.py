"""
Page adjustment module for applying calculated shrinkage to PDF pages

Applies shrinkage percentages (from Stage 8 white-space detection) to adjust
page content, creating space for footer placement.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict
from models.models import Document


@dataclass
class AdjustmentConfig:
    """Configuration for applying page adjustments
    
    Attributes:
        shrinkage_percent: Percentage to shrink page (0-100)
        shrinkage_direction: 'top', 'bottom', or 'both'
        apply_to_all_pages: Apply to all pages or specific pages
        preserve_margins: Preserve existing margins when adjusting
        maintain_aspect_ratio: Keep original aspect ratio
    """
    shrinkage_percent: float = 10.0
    shrinkage_direction: str = 'bottom'
    apply_to_all_pages: bool = False
    preserve_margins: bool = True
    maintain_aspect_ratio: bool = True
    
    def get_adjustment_ratio(self) -> float:
        """
        Calculate the adjustment ratio
        
        Returns:
            Float between 0 and 1 (e.g., 0.90 for 10% shrinkage)
        """
        return 1.0 - (self.shrinkage_percent / 100.0)
    
    def is_valid(self) -> bool:
        """
        Validate configuration values
        
        Returns:
            True if configuration is valid
        """
        # Shrinkage should be between 0 and ~50% (beyond that is unrealistic)
        if self.shrinkage_percent < 0 or self.shrinkage_percent > 50:
            return False
        
        # Direction should be valid
        if self.shrinkage_direction not in ['top', 'bottom', 'both']:
            return False
        
        return True


class PageAdjuster:
    """Applies calculated shrinkage to PDF pages
    
    Takes shrinkage data from white-space detection and applies it to
    adjust page content, creating space for footer placement.
    """
    
    def __init__(self, pdf_path: str, default_shrinkage: float = 10.0):
        """
        Initialize page adjuster
        
        Args:
            pdf_path: Path to PDF file
            default_shrinkage: Default shrinkage percentage (0-100)
        """
        self.pdf_path = pdf_path
        self.document: Optional[Document] = None
        self.default_config = AdjustmentConfig(shrinkage_percent=default_shrinkage)
        self._page_configs: Dict[int, AdjustmentConfig] = {}
    
    def load_document(self, document: Document):
        """
        Load document for adjustment
        
        Args:
            document: Document object to adjust
        """
        self.document = document
    
    def get_page_adjustment_config(self, page_number: int) -> AdjustmentConfig:
        """
        Get adjustment configuration for a page
        
        Falls back to default if page-specific config not set.
        
        Args:
            page_number: Page number (1-indexed)
            
        Returns:
            AdjustmentConfig for the page
        """
        if page_number in self._page_configs:
            return self._page_configs[page_number]
        return self.default_config
    
    def set_page_adjustment_config(self, page_number: int, config: AdjustmentConfig):
        """
        Set adjustment configuration for a specific page
        
        Args:
            page_number: Page number (1-indexed)
            config: AdjustmentConfig to apply
        """
        if config.is_valid():
            self._page_configs[page_number] = config
    
    def clear_page_adjustment_config(self, page_number: int):
        """
        Clear page-specific configuration (revert to default)
        
        Args:
            page_number: Page number (1-indexed)
        """
        if page_number in self._page_configs:
            del self._page_configs[page_number]
    
    def calculate_adjustment_for_page(self, page_number: int, 
                                     config: Optional[AdjustmentConfig] = None) -> Optional[Dict]:
        """
        Calculate adjustment dimensions for a page
        
        Args:
            page_number: Page number (1-indexed)
            config: AdjustmentConfig (uses page config if not provided)
            
        Returns:
            Dict with adjustment data: original_height, adjusted_height, space_created
        """
        if not self.document:
            return None
        
        if config is None:
            config = self.get_page_adjustment_config(page_number)
        
        if not config.is_valid():
            return None
        
        # Get original page dimensions using PDFLoader.get_page_info
        from pdf.pdf_loader import PDFLoader
        page_info = PDFLoader.get_page_info(self.document, page_number)
        
        if not page_info:
            return None
        
        original_height = page_info['height']
        original_width = page_info['width']
        
        # Calculate adjusted dimensions
        ratio = config.get_adjustment_ratio()
        adjusted_height = original_height * ratio
        space_created = original_height - adjusted_height
        
        return {
            'page_number': page_number,
            'original_height': original_height,
            'original_width': original_width,
            'adjusted_height': adjusted_height,
            'adjusted_width': original_width,  # Width unchanged
            'space_created': space_created,
            'shrinkage_percent': config.shrinkage_percent,
            'shrinkage_direction': config.shrinkage_direction,
        }
    
    def preview_adjustments(self, config: Optional[AdjustmentConfig] = None, 
                           max_pages: Optional[int] = None) -> Dict[int, Dict]:
        """
        Preview adjustments for multiple pages
        
        Args:
            config: Global config to apply (uses default if not provided)
            max_pages: Maximum number of pages to preview (None for all)
            
        Returns:
            Dict mapping page number to adjustment data
        """
        if not self.document:
            return {}
        
        if config is None:
            config = self.default_config
        
        results = {}
        pages_to_process = self.document.page_count
        
        if max_pages:
            pages_to_process = min(max_pages, pages_to_process)
        
        for page_num in range(1, pages_to_process + 1):
            adjustment = self.calculate_adjustment_for_page(page_num, config)
            if adjustment:
                results[page_num] = adjustment
        
        return results
    
    def apply_adjustments_to_document(self, config: Optional[AdjustmentConfig] = None,
                                    pages: Optional[list] = None) -> bool:
        """
        Apply adjustments to document pages
        
        Stores adjustment data in PageConfig for later use during PDF generation.
        
        Args:
            config: Adjustment config to apply
            pages: Specific pages to adjust (None for all pages or config.apply_to_all_pages)
            
        Returns:
            True if successful
        """
        if not self.document:
            return False
        
        if config is None:
            config = self.default_config
        
        if not config.is_valid():
            return False
        
        # Determine which pages to adjust
        if pages is None:
            if config.apply_to_all_pages:
                pages = list(range(1, self.document.page_count + 1))
            else:
                pages = [1]  # Default to first page
        
        # Apply to specified pages
        for page_num in pages:
            if 1 <= page_num <= self.document.page_count:
                adjustment_data = self.calculate_adjustment_for_page(page_num, config)
                
                if adjustment_data:
                    # Store in page config
                    page_config = self.document.get_page_config(page_num)
                    if not hasattr(page_config, 'adjustment_data'):
                        page_config.adjustment_data = None
                    page_config.adjustment_data = adjustment_data
                    self.document.set_page_config(page_num, page_config)
        
        # Mark document as modified
        self.document.set_modified(True)
        return True
    
    def get_adjustment_summary(self) -> Dict:
        """
        Get summary of all adjustments
        
        Returns:
            Dict with summary statistics
        """
        if not self.document:
            return {}
        
        preview = self.preview_adjustments()
        
        if not preview:
            return {'total_pages': 0, 'adjusted_pages': 0}
        
        total_space_created = sum(adj['space_created'] for adj in preview.values())
        avg_shrinkage = sum(adj['shrinkage_percent'] for adj in preview.values()) / len(preview)
        
        return {
            'total_pages': self.document.page_count,
            'adjusted_pages': len(preview),
            'total_space_created': total_space_created,
            'average_shrinkage': avg_shrinkage,
            'details': preview
        }
    
    def get_recommended_footer_height(self, page_number: int) -> Optional[float]:
        """
        Get recommended footer height based on space created
        
        Args:
            page_number: Page number (1-indexed)
            
        Returns:
            Recommended footer height in points, or None
        """
        adjustment = self.calculate_adjustment_for_page(page_number)
        if not adjustment:
            return None
        
        # Use 80% of created space for footer, reserve 20% for margin
        space_created = adjustment['space_created']
        footer_height = space_created * 0.8
        
        # Sanity check - footer should be reasonable size
        if footer_height < 10 or footer_height > space_created:
            return None
        
        return footer_height


def apply_adjustments_to_pdf(pdf_path: str, output_path: str, 
                            config: AdjustmentConfig, 
                            pages: Optional[list] = None) -> bool:
    """
    Convenience function to apply adjustments to a PDF
    
    Args:
        pdf_path: Input PDF path
        output_path: Output PDF path
        config: Adjustment configuration
        pages: Pages to adjust (None for all)
        
    Returns:
        True if successful
    """
    try:
        from pdf.pdf_loader import PDFLoader
        doc = PDFLoader.load_pdf(pdf_path)
        adjuster = PageAdjuster(pdf_path)
        adjuster.load_document(doc)
        
        return adjuster.apply_adjustments_to_document(config, pages)
        
    except Exception as e:
        print(f"Error applying adjustments: {e}")
        return False
