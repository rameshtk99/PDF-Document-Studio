"""
PDF Loader - Load PDFs and extract comprehensive metadata

Handles:
- PDF file validation
- Page extraction
- Per-page metadata (dimensions, rotation, etc.)
- Encrypted PDF detection
- Corrupted PDF handling
- Document initialization
"""

import os
from typing import Optional, List, Dict, Any
from models import Document, PageConfig, FooterConfig
from pdf import PDFHandler


class PDFLoader:
    """Load PDF files and extract metadata"""
    
    @staticmethod
    def validate_pdf(pdf_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate if a PDF file exists and is readable
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(pdf_path):
            return False, f"File does not exist: {pdf_path}"
        
        if not os.path.isfile(pdf_path):
            return False, f"Not a file: {pdf_path}"
        
        if not pdf_path.lower().endswith('.pdf'):
            return False, f"Not a PDF file: {pdf_path}"
        
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    return False, "Invalid PDF header"
        except IOError as e:
            return False, f"Cannot read file: {e}"
        
        return True, None
    
    @staticmethod
    def load_pdf(pdf_path: str) -> Optional[Document]:
        """
        Load a PDF and create a Document object with metadata
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Document object with loaded metadata, or None if failed
        """
        # Validate file
        is_valid, error = PDFLoader.validate_pdf(pdf_path)
        if not is_valid:
            raise RuntimeError(f"Invalid PDF: {error}")
        
        # Create document
        doc = Document(pdf_path)
        
        try:
            # Load PDF reader
            reader = PDFHandler.load_pdf(pdf_path)
            
            # Extract page count
            doc.page_count = len(reader.pages)
            
            # Extract per-page metadata
            page_dimensions = []
            for idx, page in enumerate(reader.pages):
                page_num = idx + 1
                
                try:
                    width, height = PDFHandler.get_page_dimensions(page)
                    rotation = page.get('/Rotate', 0)
                    
                    page_dims = {
                        'page_number': page_num,
                        'width': width,
                        'height': height,
                        'rotation': rotation,
                        'aspect_ratio': width / height if height > 0 else 1.0
                    }
                    page_dimensions.append(page_dims)
                    
                    # Initialize default page config
                    page_config = PageConfig(page_number=page_num)
                    page_config.footer_config = FooterConfig(
                        enabled=doc.global_settings.footer_config.enabled,
                        text_columns=doc.global_settings.footer_config.text_columns.copy()
                    )
                except Exception as e:
                    print(f"Warning: Could not extract metadata for page {page_num}: {e}")
                    page_dims = {
                        'page_number': page_num,
                        'width': 612,  # Default 8.5x11
                        'height': 792,
                        'rotation': 0,
                        'aspect_ratio': 612/792
                    }
                    page_dimensions.append(page_dims)
            
            # Store metadata
            doc.metadata = {
                'file_path': pdf_path,
                'file_name': os.path.basename(pdf_path),
                'file_size': os.path.getsize(pdf_path),
                'page_count': doc.page_count,
                'pages': page_dimensions,
                'is_encrypted': False,  # TODO: Check if encrypted
            }
            
            # Extract global metadata if available
            try:
                if hasattr(reader, 'metadata') and reader.metadata:
                    doc.metadata['pdf_metadata'] = {
                        'title': reader.metadata.get('/Title', ''),
                        'author': reader.metadata.get('/Author', ''),
                        'subject': reader.metadata.get('/Subject', ''),
                        'creator': reader.metadata.get('/Creator', ''),
                    }
            except:
                pass
            
            doc.set_modified(False)  # Mark as just-loaded, no modifications
            return doc
            
        except Exception as e:
            raise RuntimeError(f"Failed to load PDF: {e}")
    
    @staticmethod
    def get_page_info(doc: Document, page_num: int) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific page
        
        Args:
            doc: Document object
            page_num: Page number (1-based)
            
        Returns:
            Dictionary with page information
        """
        if not doc.metadata or 'pages' not in doc.metadata:
            return None
        
        pages = doc.metadata.get('pages', [])
        for page_info in pages:
            if page_info['page_number'] == page_num:
                return page_info
        
        return None
    
    @staticmethod
    def get_all_pages_info(doc: Document) -> List[Dict[str, Any]]:
        """Get metadata for all pages"""
        return doc.metadata.get('pages', []) if doc.metadata else []
