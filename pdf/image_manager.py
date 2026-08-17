"""
Image insertion and positioning module for PDF pages

Manages:
- Image file validation and loading
- Image placement calculations
- Multi-image management per page
- Image properties (opacity, rotation, z-index)
- Integration with adjustment data
- Z-order (layering) support
"""

from dataclasses import dataclass
import os
from typing import Optional, List, Dict, Tuple
from PIL import Image
from models.models import Document, PageObject


@dataclass
class ImagePlacement:
    """Configuration for placing an image on a page
    
    Attributes:
        page_number: Page number (1-indexed)
        x: Left position in PDF points
        y: Top position in PDF points
        width: Image width in PDF points
        height: Image height in PDF points
        rotation: Rotation in degrees (0-360)
        opacity: Opacity percentage (0-100)
        z_index: Layer order (higher = on top)
    """
    page_number: int
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    opacity: float = 100.0
    z_index: int = 0
    
    def get_aspect_ratio(self) -> float:
        """
        Get aspect ratio of placement (width/height)
        
        Returns:
            Aspect ratio
        """
        if self.height == 0:
            return 1.0
        return self.width / self.height
    
    def get_center(self) -> Tuple[float, float]:
        """
        Get center point of placement
        
        Returns:
            Tuple of (center_x, center_y)
        """
        return (self.x + self.width / 2, self.y + self.height / 2)
    
    def get_bounds(self) -> Dict[str, float]:
        """
        Get bounding box of placement
        
        Returns:
            Dict with 'left', 'top', 'right', 'bottom'
        """
        return {
            'left': self.x,
            'top': self.y,
            'right': self.x + self.width,
            'bottom': self.y + self.height
        }


class ImageManager:
    """Manages image insertion and positioning on PDF pages"""
    
    # Supported image formats
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
    
    def __init__(self):
        """Initialize image manager"""
        self.document: Optional[Document] = None
        self._image_cache: Dict[str, Image.Image] = {}
    
    def load_document(self, document: Document):
        """
        Load document for image management
        
        Args:
            document: Document object
        """
        self.document = document
    
    @staticmethod
    def validate_image_file(image_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a file is a supported image
        
        Args:
            image_path: Path to image file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(image_path):
            return False, f"File does not exist: {image_path}"
        
        if not os.path.isfile(image_path):
            return False, f"Not a file: {image_path}"
        
        # Check extension
        _, ext = os.path.splitext(image_path)
        if ext.lower() not in ImageManager.SUPPORTED_FORMATS:
            return False, f"Unsupported format: {ext}"
        
        # Try to open as image
        try:
            with Image.open(image_path) as img:
                img.verify()
            return True, None
        except Exception as e:
            return False, f"Cannot read image: {e}"
    
    def add_image_to_page(self, page_number: int, placement: ImagePlacement,
                         image_path: Optional[str] = None) -> str:
        """
        Add an image to a page
        
        Args:
            page_number: Page number (1-indexed)
            placement: ImagePlacement configuration
            image_path: Path to image file (optional)
            
        Returns:
            Image object ID
        """
        if not self.document:
            raise ValueError("No document loaded")
        
        # Create PageObject for the image
        page_obj = PageObject(
            type='image',
            page_number=page_number,
            x=placement.x,
            y=placement.y,
            width=placement.width,
            height=placement.height,
            rotation=placement.rotation,
            opacity=placement.opacity,
            z_index=placement.z_index,
            properties={'image_path': image_path or ''}
        )
        
        # Add to page configuration
        config = self.document.get_page_config(page_number)
        config.objects.append(page_obj)
        self.document.set_page_config(page_number, config)
        
        return page_obj.id
    
    def get_image_object(self, image_id: str) -> Optional[PageObject]:
        """
        Get image object by ID
        
        Args:
            image_id: Image object ID
            
        Returns:
            PageObject, or None if not found
        """
        if not self.document:
            return None
        
        for page_num in range(1, self.document.page_count + 1):
            config = self.document.get_page_config(page_num)
            for obj in config.objects:
                if obj.id == image_id:
                    return obj
        
        return None
    
    def get_page_images(self, page_number: int) -> List[PageObject]:
        """
        Get all images on a page
        
        Args:
            page_number: Page number (1-indexed)
            
        Returns:
            List of PageObject images, sorted by z-index
        """
        if not self.document:
            return []
        
        config = self.document.get_page_config(page_number)
        images = [obj for obj in config.objects if obj.type == 'image']
        
        # Sort by z-index
        images.sort(key=lambda x: x.z_index)
        
        return images
    
    def remove_image(self, image_id: str) -> bool:
        """
        Remove an image from document
        
        Args:
            image_id: Image object ID
            
        Returns:
            True if removed, False if not found
        """
        if not self.document:
            return False
        
        for page_num in range(1, self.document.page_count + 1):
            config = self.document.get_page_config(page_num)
            
            for idx, obj in enumerate(config.objects):
                if obj.id == image_id:
                    config.objects.pop(idx)
                    self.document.set_page_config(page_num, config)
                    return True
        
        return False
    
    def set_image_property(self, image_id: str, property_name: str, value):
        """
        Set a property of an image
        
        Args:
            image_id: Image object ID
            property_name: Property name (opacity, rotation, z_index, visible, locked)
            value: New value
        """
        obj = self.get_image_object(image_id)
        if not obj:
            return
        
        # Update property
        if property_name == 'opacity':
            obj.opacity = max(0, min(100, float(value)))
        elif property_name == 'rotation':
            obj.rotation = float(value) % 360
        elif property_name == 'z_index':
            obj.z_index = int(value)
        elif property_name == 'visible':
            obj.visible = bool(value)
        elif property_name == 'locked':
            obj.locked = bool(value)
        
        # Find page and update
        for page_num in range(1, self.document.page_count + 1):
            config = self.document.get_page_config(page_num)
            for idx, o in enumerate(config.objects):
                if o.id == image_id:
                    config.objects[idx] = obj
                    self.document.set_page_config(page_num, config)
                    return
    
    def set_image_position(self, image_id: str, x: float, y: float):
        """
        Set image position
        
        Args:
            image_id: Image object ID
            x: New X position
            y: New Y position
        """
        obj = self.get_image_object(image_id)
        if not obj:
            return
        
        obj.x = x
        obj.y = y
        
        # Find page and update
        for page_num in range(1, self.document.page_count + 1):
            config = self.document.get_page_config(page_num)
            for idx, o in enumerate(config.objects):
                if o.id == image_id:
                    config.objects[idx] = obj
                    self.document.set_page_config(page_num, config)
                    return
    
    def set_image_size(self, image_id: str, width: float, height: float):
        """
        Set image size
        
        Args:
            image_id: Image object ID
            width: New width
            height: New height
        """
        obj = self.get_image_object(image_id)
        if not obj:
            return
        
        obj.width = width
        obj.height = height
        
        # Find page and update
        for page_num in range(1, self.document.page_count + 1):
            config = self.document.get_page_config(page_num)
            for idx, o in enumerate(config.objects):
                if o.id == image_id:
                    config.objects[idx] = obj
                    self.document.set_page_config(page_num, config)
                    return
    
    @staticmethod
    def validate_image_placement(placement: ImagePlacement, 
                                page_width: float, page_height: float) -> bool:
        """
        Validate if image placement is within page bounds
        
        Args:
            placement: ImagePlacement to validate
            page_width: Page width in points
            page_height: Page height in points
            
        Returns:
            True if placement is valid
        """
        # Check if position is negative
        if placement.x < 0 or placement.y < 0:
            return False
        
        # Check if image extends beyond page bounds
        # Allow some tolerance for slight overflows
        tolerance = 5.0
        if placement.x + placement.width > page_width + tolerance:
            return False
        if placement.y + placement.height > page_height + tolerance:
            return False
        
        # Check if dimensions are positive
        if placement.width <= 0 or placement.height <= 0:
            return False
        
        return True
    
    def calculate_position_for_footer(self, page_number: int, 
                                     available_space: float,
                                     image_width: float) -> Tuple[float, float]:
        """
        Calculate position for image in footer area
        
        Args:
            page_number: Page number
            available_space: Height of footer space (in points)
            image_width: Desired image width
            
        Returns:
            Tuple of (x, y) position
        """
        from pdf.pdf_loader import PDFLoader
        
        if not self.document:
            return (50.0, 50.0)
        
        # Get page dimensions
        page_info = PDFLoader.get_page_info(self.document, page_number)
        page_width = page_info['width']
        page_height = page_info['height']
        
        # Position in footer area (bottom of page)
        x = 50.0  # Left margin
        y = page_height - available_space + (available_space * 0.1)  # 10% margin from bottom
        
        return (x, y)
    
    def get_images_summary(self) -> Dict:
        """
        Get summary of all images in document
        
        Returns:
            Dict with image statistics
        """
        if not self.document:
            return {'total_images': 0}
        
        total_images = 0
        images_by_page = {}
        
        for page_num in range(1, self.document.page_count + 1):
            images = self.get_page_images(page_num)
            if images:
                images_by_page[page_num] = len(images)
                total_images += len(images)
        
        return {
            'total_images': total_images,
            'pages_with_images': len(images_by_page),
            'images_by_page': images_by_page
        }
    
    def clear_cache(self):
        """Clear image cache"""
        self._image_cache.clear()
