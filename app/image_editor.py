"""
Interactive image editing module for PDF canvas

Manages:
- Drag-and-drop repositioning
- Resize handle detection and manipulation
- Z-order controls (bring forward, send back, arrange)
- Snap-to-grid alignment
- Visual selection feedback
- Mouse event handling
- Multi-select operations
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from models.models import Document, PageObject


@dataclass
class ResizeHandle:
    """Represents a resize handle on a selection box
    
    Attributes:
        handle_type: Position (TL, T, TR, R, BR, B, BL, L)
        x: X position of handle center
        y: Y position of handle center
        size: Handle click area size
    """
    handle_type: str  # TL, T, TR, R, BR, B, BL, L
    x: float
    y: float
    size: float = 10.0  # 10x10 pixels
    
    def contains_point(self, px: float, py: float) -> bool:
        """
        Check if point is within handle click area
        
        Args:
            px: Point X
            py: Point Y
            
        Returns:
            True if point is within handle
        """
        half_size = self.size / 2
        return (abs(px - self.x) <= half_size and 
                abs(py - self.y) <= half_size)


@dataclass
class SelectionBox:
    """Visual selection box around a selected image
    
    Attributes:
        x: Left position
        y: Top position
        width: Box width
        height: Box height
        stroke_width: Border thickness
        stroke_color: Border color (hex)
    """
    x: float
    y: float
    width: float
    height: float
    stroke_width: float = 2.0
    stroke_color: str = '#0080FF'
    is_visible: bool = True
    
    def get_bounds(self) -> Dict[str, float]:
        """
        Get bounding box coordinates
        
        Returns:
            Dict with left, top, right, bottom
        """
        return {
            'left': self.x,
            'top': self.y,
            'right': self.x + self.width,
            'bottom': self.y + self.height
        }
    
    def get_resize_handles(self) -> List[ResizeHandle]:
        """
        Get all 8 resize handles
        
        Returns:
            List of ResizeHandle objects
        """
        handles = []
        
        # Corner handles
        corners = {
            'TL': (self.x, self.y),
            'TR': (self.x + self.width, self.y),
            'BR': (self.x + self.width, self.y + self.height),
            'BL': (self.x, self.y + self.height),
        }
        
        for handle_type, (hx, hy) in corners.items():
            handles.append(ResizeHandle(handle_type, hx, hy))
        
        # Edge midpoint handles
        edges = {
            'T': (self.x + self.width / 2, self.y),
            'R': (self.x + self.width, self.y + self.height / 2),
            'B': (self.x + self.width / 2, self.y + self.height),
            'L': (self.x, self.y + self.height / 2),
        }
        
        for handle_type, (hx, hy) in edges.items():
            handles.append(ResizeHandle(handle_type, hx, hy))
        
        return handles
    
    def move(self, new_x: float, new_y: float):
        """
        Move selection box to new position
        
        Args:
            new_x: New X position
            new_y: New Y position
        """
        self.x = new_x
        self.y = new_y
    
    def resize(self, new_width: float, new_height: float):
        """
        Resize selection box
        
        Args:
            new_width: New width
            new_height: New height
        """
        self.width = max(20.0, new_width)  # Minimum 20pt
        self.height = max(20.0, new_height)  # Minimum 20pt


class ImageEditor:
    """Manages interactive image editing on PDF canvas"""
    
    def __init__(self):
        """Initialize image editor"""
        self.document: Optional[Document] = None
        self.manager = None
        
        # Drag/resize state
        self.dragging_object: Optional[str] = None
        self.resizing_object: Optional[str] = None
        self.resizing_handle: Optional[ResizeHandle] = None
        self.drag_start_x: float = 0.0
        self.drag_start_y: float = 0.0
        self.object_start_x: float = 0.0
        self.object_start_y: float = 0.0
        self.object_start_width: float = 0.0
        self.object_start_height: float = 0.0
        
        # Selection state
        self.selected_objects: List[str] = []
        self.selection_boxes: Dict[str, SelectionBox] = {}
        
        # Grid state
        self.grid_enabled: bool = False
        self.grid_size: float = 10.0
    
    def load_document(self, document: Document):
        """
        Load document for editing
        
        Args:
            document: Document object
        """
        self.document = document
    
    def set_manager(self, manager):
        """
        Set image manager
        
        Args:
            manager: ImageManager instance
        """
        self.manager = manager
    
    def get_hit_target(self, x: float, y: float, 
                      image_ids: List[str], manager) -> Optional[str]:
        """
        Detect which image is clicked at given position
        
        Uses z-order to return topmost image
        
        Args:
            x: Mouse X position
            y: Mouse Y position
            image_ids: List of image IDs to check
            manager: ImageManager instance
            
        Returns:
            Image ID if hit, None otherwise
        """
        if not manager:
            return None
        
        # Collect all images with their z-index
        images_at_pos = []
        
        for image_id in image_ids:
            obj = manager.get_image_object(image_id)
            if not obj:
                continue
            
            # Check if point is within image bounds
            if (obj.x <= x <= obj.x + obj.width and
                obj.y <= y <= obj.y + obj.height):
                images_at_pos.append((obj.z_index, image_id))
        
        if not images_at_pos:
            return None
        
        # Return topmost image (highest z-index)
        images_at_pos.sort(reverse=True)
        return images_at_pos[0][1]
    
    def start_drag(self, x: float, y: float, image_id: str):
        """
        Start dragging an image
        
        Args:
            x: Mouse X position
            y: Mouse Y position
            image_id: ID of image to drag
        """
        if not self.manager:
            return
        
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        self.dragging_object = image_id
        self.drag_start_x = x
        self.drag_start_y = y
        self.object_start_x = obj.x
        self.object_start_y = obj.y
    
    def drag_to(self, x: float, y: float):
        """
        Move dragging object to new position or resize if resizing
        
        Args:
            x: New mouse X position
            y: New mouse Y position
        """
        # Handle resize operation
        if self.resizing_object and self.resizing_handle and self.manager:
            self._handle_resize(x, y)
        # Handle drag operation
        elif self.dragging_object and self.manager:
            # Calculate delta
            dx = x - self.drag_start_x
            dy = y - self.drag_start_y
            
            # Apply snap-to-grid if enabled
            if self.grid_enabled:
                dx = self._snap_value(dx)
                dy = self._snap_value(dy)
            
            # Calculate new position
            new_x = self.object_start_x + dx
            new_y = self.object_start_y + dy
            
            # Clamp to reasonable bounds (optional)
            new_x = max(0, new_x)
            new_y = max(0, new_y)
            
            # Update image position
            self.manager.set_image_position(self.dragging_object, new_x, new_y)
    
    def _handle_resize(self, x: float, y: float):
        """
        Handle resize operation based on handle type
        
        Args:
            x: New mouse X position
            y: New mouse Y position
        """
        if not self.resizing_object or not self.resizing_handle or not self.manager:
            return
        
        obj = self.manager.get_image_object(self.resizing_object)
        if not obj:
            return
        
        # Calculate delta
        dx = x - self.drag_start_x
        dy = y - self.drag_start_y
        
        handle_type = self.resizing_handle.handle_type
        new_x = self.object_start_x
        new_y = self.object_start_y
        new_width = self.object_start_width
        new_height = self.object_start_height
        
        # Handle corner and edge resizing
        if handle_type in ['TL', 'L', 'BL']:
            new_x = self.object_start_x + dx
            new_width = self.object_start_width - dx
        elif handle_type in ['TR', 'R', 'BR']:
            new_width = self.object_start_width + dx
        
        if handle_type in ['TL', 'T', 'TR']:
            new_y = self.object_start_y + dy
            new_height = self.object_start_height - dy
        elif handle_type in ['BL', 'B', 'BR']:
            new_height = self.object_start_height + dy
        
        # Ensure minimum size
        new_width = max(20.0, new_width)
        new_height = max(20.0, new_height)
        
        # Apply snap-to-grid if enabled
        if self.grid_enabled:
            new_x = self._snap_value(new_x)
            new_y = self._snap_value(new_y)
            new_width = self._snap_value(new_width)
            new_height = self._snap_value(new_height)
        
        # Update image
        self.manager.set_image_position(self.resizing_object, new_x, new_y)
        self.manager.set_image_size(self.resizing_object, new_width, new_height)
    
    def start_resize(self, handle: ResizeHandle, image_id: str):
        """
        Start resizing an image via a handle
        
        Args:
            handle: ResizeHandle being dragged
            image_id: ID of image to resize
        """
        if not self.manager:
            return
        
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        self.resizing_object = image_id
        self.resizing_handle = handle
        self.drag_start_x = handle.x
        self.drag_start_y = handle.y
        self.object_start_x = obj.x
        self.object_start_y = obj.y
        self.object_start_width = obj.width
        self.object_start_height = obj.height
    
    def end_drag(self):
        """End current drag or resize operation"""
        self.dragging_object = None
        self.resizing_object = None
        self.resizing_handle = None
    
    def bring_forward(self, image_id: str):
        """
        Bring image forward one layer
        
        Args:
            image_id: Image to bring forward
        """
        if not self.manager:
            return
        
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        # Increment z-index
        self.manager.set_image_property(image_id, 'z_index', obj.z_index + 1)
    
    def send_backward(self, image_id: str):
        """
        Send image backward one layer
        
        Args:
            image_id: Image to send backward
        """
        if not self.manager:
            return
        
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        # Decrement z-index
        self.manager.set_image_property(image_id, 'z_index', max(0, obj.z_index - 1))
    
    def bring_to_front(self, image_id: str):
        """
        Bring image to front (highest z-index)
        
        Args:
            image_id: Image to bring to front
        """
        if not self.manager or not self.document:
            return
        
        # Get current page and find max z-index
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        page_images = self.manager.get_page_images(obj.page_number)
        if not page_images:
            return
        
        max_z = max(img.z_index for img in page_images)
        self.manager.set_image_property(image_id, 'z_index', max_z + 1)
    
    def send_to_back(self, image_id: str):
        """
        Send image to back (lowest z-index)
        
        Args:
            image_id: Image to send to back
        """
        if not self.manager:
            return
        
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        # Set z-index to 0 and shift others up
        page_images = self.manager.get_page_images(obj.page_number)
        for img in page_images:
            if img.id != image_id:
                self.manager.set_image_property(img.id, 'z_index', img.z_index + 1)
        
        self.manager.set_image_property(image_id, 'z_index', 0)
    
    def enable_grid(self, enabled: bool = True, grid_size: float = 10.0):
        """
        Enable/disable snap-to-grid
        
        Args:
            enabled: True to enable grid
            grid_size: Grid size in points
        """
        self.grid_enabled = enabled
        self.grid_size = grid_size
    
    def snap_to_grid(self, x: float, y: float) -> Tuple[float, float]:
        """
        Snap coordinates to grid
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            Tuple of snapped (x, y)
        """
        if not self.grid_enabled or self.grid_size <= 0:
            return (x, y)
        
        snapped_x = round(x / self.grid_size) * self.grid_size
        snapped_y = round(y / self.grid_size) * self.grid_size
        
        return (snapped_x, snapped_y)
    
    def snap_object_to_grid(self, image_id: str):
        """
        Snap image to grid
        
        Args:
            image_id: Image to snap
        """
        if not self.manager or not self.grid_enabled:
            return
        
        obj = self.manager.get_image_object(image_id)
        if not obj:
            return
        
        snapped = self.snap_to_grid(obj.x, obj.y)
        self.manager.set_image_position(image_id, snapped[0], snapped[1])
    
    def select_objects(self, image_ids: List[str]):
        """
        Select one or more images
        
        Args:
            image_ids: List of image IDs to select
        """
        self.selected_objects = image_ids.copy()
        
        # Create selection boxes
        for image_id in image_ids:
            if self.manager:
                obj = self.manager.get_image_object(image_id)
                if obj:
                    self.selection_boxes[image_id] = SelectionBox(
                        obj.x, obj.y, obj.width, obj.height
                    )
    
    def deselect_all(self):
        """Deselect all objects"""
        self.selected_objects.clear()
        self.selection_boxes.clear()
    
    def deselect_object(self, image_id: str):
        """
        Deselect specific object
        
        Args:
            image_id: Image to deselect
        """
        if image_id in self.selected_objects:
            self.selected_objects.remove(image_id)
        if image_id in self.selection_boxes:
            del self.selection_boxes[image_id]
    
    def _snap_value(self, value: float) -> float:
        """
        Snap single value to grid
        
        Args:
            value: Value to snap
            
        Returns:
            Snapped value
        """
        if not self.grid_enabled or self.grid_size <= 0:
            return value
        
        return round(value / self.grid_size) * self.grid_size
    
    def get_selection_summary(self) -> Dict:
        """
        Get summary of current selection
        
        Returns:
            Dict with selection statistics
        """
        return {
            'selected_count': len(self.selected_objects),
            'selected_ids': self.selected_objects.copy(),
            'selection_boxes': len(self.selection_boxes),
            'dragging': self.dragging_object is not None,
            'resizing': self.resizing_object is not None,
            'grid_enabled': self.grid_enabled,
            'grid_size': self.grid_size,
        }
