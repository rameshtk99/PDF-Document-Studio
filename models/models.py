"""
Data models for Document, Page, and Objects
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
import uuid


@dataclass
class PageRef:
    """A single page's stable identity within a (possibly combined)
    document -- decoupled from its current display position, which
    changes on delete/move/insert. Points at wherever the page's actual
    content lives (its own source PDF file + index within that file)
    rather than duplicating the page's bytes, so combining pages from
    another PDF costs only this small record, not a copy of that PDF.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_path: str = ""   # PDF file this page's content comes from
    source_index: int = 0   # 0-based page index within that file
    width: float = 0.0      # PDF points -- cached from source metadata
    height: float = 0.0
    rotation: int = 0


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
    rotation: float = 0.0  # degrees, clockwise
    opacity: float = 100.0  # 0-100%
    z_index: int = 0
    locked: bool = False
    visible: bool = True
    group_id: Optional[str] = None  # None = ungrouped; shared value = same group
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
    bottom_margin: float = 72.0  # points (gap between content bottom and footer top; 72pt = 1 inch)
    line_gap: float = 4.0  # points
    compress_content: bool = True  # shrink page content to fit footer when needed

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
        self.pages: List[PageRef] = []  # display order; source of truth for page identity/order
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
        g = self.global_settings.footer_config
        config.footer_config = FooterConfig(
            enabled=g.enabled,
            text_columns=g.text_columns.copy(),
            font_name=g.font_name,
            font_size=g.font_size,
            left_margin=g.left_margin,
            right_margin=g.right_margin,
            bottom_margin=g.bottom_margin,
            line_gap=g.line_gap,
            compress_content=g.compress_content,
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
    
    # ---- page management ---------------------------------------------
    # The only place page order changes. Everything else keeps using
    # 1-indexed display positions; these methods carry page_configs and
    # PageObject.page_number across to each page's new position.

    def _renumber_page_configs(self, old_to_new: Dict[int, Optional[int]]):
        """Rebuild page_configs with every key (and each contained
        PageObject.page_number) remapped from old 1-indexed display
        position to new, per old_to_new. A page mapped to None (deleted)
        has its config dropped."""
        new_configs: Dict[int, PageConfig] = {}
        for old_num, cfg in self.page_configs.items():
            new_num = old_to_new.get(old_num)
            if new_num is None:
                continue
            cfg.page_number = new_num
            for obj in cfg.objects:
                obj.page_number = new_num
            new_configs[new_num] = cfg
        self.page_configs = new_configs

    def delete_page(self, index: int) -> PageRef:
        """Remove the page at 0-based `index`. Returns the removed PageRef
        (callers needing undo should hold onto it, along with whatever
        get_page_config(index+1) returned before calling this, since that
        config is dropped here)."""
        if not (0 <= index < len(self.pages)):
            raise IndexError(f"Page index {index} out of range")
        old_count = len(self.pages)
        removed = self.pages.pop(index)
        old_num = index + 1

        old_to_new: Dict[int, Optional[int]] = {}
        for i in range(1, old_count + 1):
            if i < old_num:
                old_to_new[i] = i
            elif i == old_num:
                old_to_new[i] = None
            else:
                old_to_new[i] = i - 1
        self._renumber_page_configs(old_to_new)

        self.page_count = len(self.pages)
        self._modified = True
        return removed

    def move_page(self, from_index: int, to_index: int):
        """Move the page at 0-based `from_index` to 0-based `to_index`,
        shifting the pages in between and carrying every page's
        config/objects along to its new position."""
        n = len(self.pages)
        if not (0 <= from_index < n) or not (0 <= to_index < n):
            raise IndexError("Page index out of range")
        if from_index == to_index:
            return

        ref = self.pages.pop(from_index)
        self.pages.insert(to_index, ref)

        old_num = from_index + 1
        new_num = to_index + 1
        old_to_new: Dict[int, int] = {}
        for i in range(1, n + 1):
            if i == old_num:
                old_to_new[i] = new_num
            elif from_index < to_index and old_num < i <= new_num:
                old_to_new[i] = i - 1
            elif from_index > to_index and new_num <= i < old_num:
                old_to_new[i] = i + 1
            else:
                old_to_new[i] = i
        self._renumber_page_configs(old_to_new)
        self._modified = True

    def insert_pages(self, at_index: int, refs: List[PageRef]):
        """Insert `refs` starting at 0-based `at_index` (0 = before the
        first page, len(self.pages) = after the last). Existing pages at
        or after at_index shift right; their configs move with them. The
        newly-inserted pages get no config (they fall back to global
        settings, same as any page with no override)."""
        if not refs:
            return
        n = len(self.pages)
        at_index = max(0, min(at_index, n))
        self.pages[at_index:at_index] = refs

        shift = len(refs)
        new_num_at = at_index + 1
        old_to_new: Dict[int, int] = {}
        for i in range(1, n + 1):
            old_to_new[i] = i if i < new_num_at else i + shift
        self._renumber_page_configs(old_to_new)

        self.page_count = len(self.pages)
        self._modified = True

    def reorder_pages(self, new_order: List[int]):
        """Rebuild the page list from `new_order` (0-based indices into
        the current list). Indices left out are dropped, so this covers
        both reordering and deleting; configs follow their page."""
        n = len(self.pages)
        if any(not (0 <= i < n) for i in new_order) or len(set(new_order)) != len(new_order):
            raise ValueError("new_order must be unique indices into the current pages")

        self.pages = [self.pages[i] for i in new_order]
        old_to_new: Dict[int, Optional[int]] = {i + 1: None for i in range(n)}
        for new_idx, old_idx in enumerate(new_order):
            old_to_new[old_idx + 1] = new_idx + 1
        self._renumber_page_configs(old_to_new)

        self.page_count = len(self.pages)
        self._modified = True

    def file_groups(self) -> List[Dict[str, Any]]:
        """Pages grouped by source file, ordered by first appearance.

        A file's pages can end up scattered after page-level moves; they
        still report as one group, which is what makes a file-level
        reorder or delete mean "all of this file's pages".
        """
        groups: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for index, ref in enumerate(self.pages):
            path = ref.source_path
            if path not in groups:
                groups[path] = {'source_path': path, 'page_indices': []}
                order.append(path)
            groups[path]['page_indices'].append(index)
        return [groups[p] for p in order]

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
