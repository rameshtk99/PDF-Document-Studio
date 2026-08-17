"""
Data models for Document, Page, and Objects
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
import uuid


@dataclass
class PageObject:
    """Represents an editable object on a page (image, text, watermark, etc.)"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "image"  # "image", "text", "watermark", etc.
    page_number: int = 1
    x: float = 0.0  # PDF points
    y: float = 0.0  # PDF points
    width: float = 100.0
    height: float = 100.0
    rotation: float = 0.0  # degrees
    opacity: float = 100.0  # 0-100%
    z_index: int = 0
    locked: bool = False
    visible: bool = True
    properties: Dict[str, Any] = field(default_factory=dict)  # type, path, text, etc.


@dataclass
class FooterConfig:
    """Footer configuration for a page"""
    enabled: bool = True
    text_columns: List[Tuple[str, str]] = field(default_factory=list)  # List of (line1, line2)
    font_name: str = "Helvetica"
    font_size: int = 13
    left_margin: float = 36.0  # points
    right_margin: float = 36.0  # points
    bottom_margin: float = 24.0  # points
    line_gap: float = 4.0  # points
    
    def __post_init__(self):
        if not self.text_columns:
            self.text_columns = [("", "")] * 5  # Default 5 columns


@dataclass
class PageConfig:
    """Page-specific configuration"""
    page_number: int
    footer_config: FooterConfig = field(default_factory=FooterConfig)
    objects: List[PageObject] = field(default_factory=list)
    auto_layout: bool = True  # Apply automatic layout adjustment
    preserve_original: bool = True
    overrides_global: bool = False  # Whether this page differs from global settings
    adjustment_data: Optional[Dict[str, Any]] = None  # Stage 9 page adjustment data
    white_space_analysis: Optional[Dict[str, Any]] = None  # Stage 8 analysis results


@dataclass
class GlobalSettings:
    """Global default settings"""
    footer_config: FooterConfig = field(default_factory=FooterConfig)
    auto_layout: bool = True
    preserve_original: bool = True
    allow_page_shrinking: bool = True  # "Safe mode" toggle


class Document:
    """Represents a PDF document with metadata and pages"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.page_count = 0
        self.page_configs: Dict[int, PageConfig] = {}
        self.global_settings = GlobalSettings()
        self.metadata: Dict[str, Any] = {}
        self._project_path: Optional[str] = None
        self._modified = False
    
    def set_page_config(self, page_num: int, config: PageConfig):
        """Set configuration for a specific page"""
        self.page_configs[page_num] = config
        config.overrides_global = True
        self._modified = True
    
    def get_page_config(self, page_num: int) -> PageConfig:
        """
        Get configuration for a page
        
        Returns page-specific config if it exists, otherwise a config based on global settings
        """
        if page_num in self.page_configs:
            return self.page_configs[page_num]
        
        # Create default page config from global settings
        config = PageConfig(page_number=page_num)
        config.footer_config = FooterConfig(
            enabled=self.global_settings.footer_config.enabled,
            text_columns=self.global_settings.footer_config.text_columns.copy(),
            font_name=self.global_settings.footer_config.font_name,
            font_size=self.global_settings.footer_config.font_size,
            left_margin=self.global_settings.footer_config.left_margin,
            right_margin=self.global_settings.footer_config.right_margin,
            bottom_margin=self.global_settings.footer_config.bottom_margin,
            line_gap=self.global_settings.footer_config.line_gap,
        )
        config.auto_layout = self.global_settings.auto_layout
        config.preserve_original = self.global_settings.preserve_original
        return config
    
    def add_object_to_page(self, page_num: int, obj: PageObject):
        """Add an editable object to a page"""
        if page_num not in self.page_configs:
            self.set_page_config(page_num, PageConfig(page_number=page_num))
        self.page_configs[page_num].objects.append(obj)
        self._modified = True
    
    def remove_object(self, obj_id: str):
        """Remove an object by ID"""
        for page_config in self.page_configs.values():
            page_config.objects = [o for o in page_config.objects if o.id != obj_id]
        self._modified = True
    
    def get_object(self, obj_id: str) -> Optional[PageObject]:
        """Find an object by ID"""
        for page_config in self.page_configs.values():
            for obj in page_config.objects:
                if obj.id == obj_id:
                    return obj
        return None
    
    def is_modified(self) -> bool:
        """Check if document has unsaved changes"""
        return self._modified
    
    def set_modified(self, modified: bool = True):
        """Mark document as modified or saved"""
        self._modified = modified
    
    def set_project_path(self, project_path: str):
        """Set the project file path"""
        self._project_path = project_path
    
    def get_project_path(self) -> Optional[str]:
        """Get the project file path"""
        return self._project_path
