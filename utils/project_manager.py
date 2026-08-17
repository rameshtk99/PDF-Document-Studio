"""
Stage 13: Project Manager - Save/Load functionality
Handles .pdfeditor project file format with JSON serialization
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from models.models import Document, PageConfig, FooterConfig, PageObject, GlobalSettings
from pdf.pdf_loader import PDFLoader


class ProjectManager:
    """Manages saving and loading projects in .pdfeditor format"""
    
    PROJECT_VERSION = "1.0"
    FILE_EXTENSION = ".pdfeditor"
    
    def __init__(self, project_file: Optional[Path] = None):
        """
        Initialize ProjectManager
        
        Args:
            project_file: Path to .pdfeditor file
        """
        self.project_file = Path(project_file) if project_file else None
        self.document: Optional[Document] = None
        self._modified = False
    
    def new_project(self, pdf_path: str) -> Document:
        """
        Create a new project from a PDF
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Initialized Document
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        loader = PDFLoader()
        document = loader.load_pdf(pdf_path)
        self.document = document
        self._modified = False
        
        return document
    
    def save(self, document: Optional[Document] = None) -> bool:
        """
        Save document to project file
        
        Args:
            document: Document to save (uses self.document if not provided)
            
        Returns:
            True if save successful
            
        Raises:
            ValueError: If no project file specified
            FileNotFoundError: If PDF file doesn't exist
        """
        if not self.project_file:
            raise ValueError("No project file specified")
        
        doc = document or self.document
        if not doc:
            raise ValueError("No document to save")
        
        if not os.path.exists(doc.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {doc.pdf_path}")
        
        # Build project data structure
        project_data = self._serialize_document(doc)
        
        # Ensure directory exists
        self.project_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        with open(self.project_file, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=2)
        
        self._modified = False
        return True
    
    def load(self) -> Document:
        """
        Load document from project file
        
        Returns:
            Loaded Document
            
        Raises:
            FileNotFoundError: If project file doesn't exist
            ValueError: If file format invalid
        """
        if not self.project_file or not self.project_file.exists():
            raise FileNotFoundError(f"Project file not found: {self.project_file}")
        
        with open(self.project_file, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
        
        # Validate project format
        self._validate_project_data(project_data)
        
        # Reconstruct document
        self.document = self._deserialize_document(project_data)
        self._modified = False
        
        return self.document
    
    def save_as(self, project_file: Path, document: Optional[Document] = None) -> bool:
        """
        Save document to a different project file
        
        Args:
            project_file: New project file path
            document: Document to save
            
        Returns:
            True if save successful
        """
        self.project_file = Path(project_file)
        return self.save(document)
    
    def _serialize_document(self, doc: Document) -> Dict[str, Any]:
        """
        Serialize document to JSON-compatible dict
        
        Args:
            doc: Document to serialize
            
        Returns:
            Serialized document data
        """
        page_configs = {}
        
        for page_idx, page_cfg in doc.page_configs.items():
            page_configs[str(page_idx)] = self._serialize_page_config(page_cfg)
        
        return {
            'version': self.PROJECT_VERSION,
            'pdf_path': str(doc.pdf_path),
            'page_count': doc.page_count,
            'global_settings': self._serialize_global_settings(doc.global_settings),
            'page_configs': page_configs,
            'metadata': {
                'created': doc.metadata.get('created', datetime.now().isoformat()),
                'modified': datetime.now().isoformat(),
                'version': self.PROJECT_VERSION
            }
        }
    
    def _serialize_page_config(self, page_cfg: PageConfig) -> Dict[str, Any]:
        """
        Serialize page configuration
        
        Args:
            page_cfg: PageConfig to serialize
            
        Returns:
            Serialized page config
        """
        footer_config = {}
        if page_cfg.footer_config:
            footer_config = {
                'enabled': page_cfg.footer_config.enabled,
                'text_columns': page_cfg.footer_config.text_columns,
                'font_name': page_cfg.footer_config.font_name,
                'font_size': page_cfg.footer_config.font_size,
                'left_margin': page_cfg.footer_config.left_margin,
                'right_margin': page_cfg.footer_config.right_margin,
                'bottom_margin': page_cfg.footer_config.bottom_margin,
                'line_gap': page_cfg.footer_config.line_gap
            }
        
        objects = []
        for obj in page_cfg.objects:
            objects.append(self._serialize_page_object(obj))
        
        return {
            'footer_config': footer_config,
            'objects': objects,
            'auto_layout': page_cfg.auto_layout,
            'preserve_original': page_cfg.preserve_original,
            'adjustment_data': getattr(page_cfg, 'adjustment_data', None),
            'white_space_analysis': getattr(page_cfg, 'white_space_analysis', None)
        }
    
    def _serialize_page_object(self, obj: PageObject) -> Dict[str, Any]:
        """
        Serialize page object (image, etc.)
        
        Args:
            obj: PageObject to serialize
            
        Returns:
            Serialized object
        """
        return {
            'id': obj.id,
            'type': obj.type,
            'x': obj.x,
            'y': obj.y,
            'width': obj.width,
            'height': obj.height,
            'rotation': obj.rotation,
            'opacity': obj.opacity,
            'z_index': obj.z_index,
            'visible': obj.visible,
            'locked': obj.locked,
            'properties': obj.properties
        }
    
    def _serialize_global_settings(self, settings: GlobalSettings) -> Dict[str, Any]:
        """
        Serialize global settings
        
        Args:
            settings: GlobalSettings to serialize
            
        Returns:
            Serialized settings
        """
        footer_config = {}
        if settings.footer_config:
            footer_config = {
                'enabled': settings.footer_config.enabled,
                'text_columns': settings.footer_config.text_columns,
                'font_name': settings.footer_config.font_name,
                'font_size': settings.footer_config.font_size,
                'left_margin': settings.footer_config.left_margin,
                'right_margin': settings.footer_config.right_margin,
                'bottom_margin': settings.footer_config.bottom_margin,
                'line_gap': settings.footer_config.line_gap
            }
        
        return {
            'footer_config': footer_config,
            'auto_layout': settings.auto_layout,
            'preserve_original': settings.preserve_original,
            'allow_page_shrinking': settings.allow_page_shrinking
        }
    
    def _deserialize_document(self, data: Dict[str, Any]) -> Document:
        """
        Deserialize document from JSON data
        
        Args:
            data: Project data dict
            
        Returns:
            Reconstructed Document
        """
        # Create document from PDF
        pdf_path = data['pdf_path']
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Referenced PDF not found: {pdf_path}")
        
        document = Document(pdf_path=pdf_path)
        document.page_count = data.get('page_count', 0)
        document.metadata = data.get('metadata', {})
        
        # Restore global settings
        global_settings_data = data.get('global_settings', {})
        if global_settings_data:
            footer_data = global_settings_data.get('footer_config', {})
            # Convert text_columns from lists back to tuples (JSON converts tuples to lists)
            text_columns = footer_data.get('text_columns', [("", "")] * 5)
            if text_columns and isinstance(text_columns[0], list):
                text_columns = [tuple(col) for col in text_columns]
            
            document.global_settings.footer_config = FooterConfig(
                enabled=footer_data.get('enabled', True),
                text_columns=text_columns,
                font_name=footer_data.get('font_name', 'Helvetica'),
                font_size=footer_data.get('font_size', 13),
                left_margin=footer_data.get('left_margin', 36.0),
                right_margin=footer_data.get('right_margin', 36.0),
                bottom_margin=footer_data.get('bottom_margin', 24.0),
                line_gap=footer_data.get('line_gap', 4.0)
            )
            document.global_settings.auto_layout = global_settings_data.get('auto_layout', True)
            document.global_settings.preserve_original = global_settings_data.get('preserve_original', True)
            document.global_settings.allow_page_shrinking = global_settings_data.get('allow_page_shrinking', True)
        
        # Restore page configs
        for page_idx_str, page_cfg_data in data.get('page_configs', {}).items():
            page_idx = int(page_idx_str)
            page_cfg = PageConfig(page_number=page_idx)
            
            # Restore footer config
            footer_data = page_cfg_data.get('footer_config')
            if footer_data:
                # Convert text_columns from lists back to tuples (JSON converts tuples to lists)
                text_columns = footer_data.get('text_columns', [("", "")] * 5)
                if text_columns and isinstance(text_columns[0], list):
                    text_columns = [tuple(col) for col in text_columns]
                
                page_cfg.footer_config = FooterConfig(
                    enabled=footer_data.get('enabled', True),
                    text_columns=text_columns,
                    font_name=footer_data.get('font_name', 'Helvetica'),
                    font_size=footer_data.get('font_size', 13),
                    left_margin=footer_data.get('left_margin', 36.0),
                    right_margin=footer_data.get('right_margin', 36.0),
                    bottom_margin=footer_data.get('bottom_margin', 24.0),
                    line_gap=footer_data.get('line_gap', 4.0)
                )
            
            # Restore objects
            for obj_data in page_cfg_data.get('objects', []):
                obj = PageObject(
                    id=obj_data['id'],
                    type=obj_data['type'],
                    page_number=page_idx,
                    x=obj_data['x'],
                    y=obj_data['y'],
                    width=obj_data['width'],
                    height=obj_data['height'],
                    rotation=obj_data.get('rotation', 0),
                    opacity=obj_data.get('opacity', 100),
                    z_index=obj_data.get('z_index', 0),
                    visible=obj_data.get('visible', True),
                    locked=obj_data.get('locked', False),
                    properties=obj_data.get('properties', {})
                )
                page_cfg.objects.append(obj)
            
            # Restore page settings
            page_cfg.auto_layout = page_cfg_data.get('auto_layout', True)
            page_cfg.preserve_original = page_cfg_data.get('preserve_original', True)
            
            # Restore adjustment data if present
            if 'adjustment_data' in page_cfg_data:
                page_cfg.adjustment_data = page_cfg_data['adjustment_data']
            
            if 'white_space_analysis' in page_cfg_data:
                page_cfg.white_space_analysis = page_cfg_data['white_space_analysis']
            
            document.page_configs[page_idx] = page_cfg
        
        return document
    
    def _validate_project_data(self, data: Dict[str, Any]) -> None:
        """
        Validate project data structure
        
        Args:
            data: Project data to validate
            
        Raises:
            ValueError: If required fields missing or invalid
        """
        required_fields = ['version', 'pdf_path', 'page_count', 'page_configs']
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate version compatibility
        version = data.get('version', '1.0')
        major, minor = version.split('.')[:2]
        if major != '1':
            raise ValueError(f"Unsupported project version: {version}")
    
    def is_modified(self) -> bool:
        """Check if document has unsaved changes"""
        return self._modified
    
    def mark_modified(self):
        """Mark document as modified"""
        self._modified = True
