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
from models import Document, PageRef
from pdf import PDFHandler


class PDFLoader:
    """Load PDF files and extract metadata"""

    @staticmethod
    def build_page_refs(pdf_path: str, reader=None) -> List[PageRef]:
        """Read a PDF's page count/dimensions only (no page content) and
        return one PageRef per page, pointing at pdf_path. Used both by
        load_pdf (for the primary document) and by the Insert-Pages-From-PDF
        dialog (for a secondary document being combined in) -- this is
        metadata-only work, the same low cost as opening any PDF, and never
        copies page bytes: the PageRef just remembers where to read them
        from later (render/export time), which is what keeps combining
        pages from another PDF lightweight.

        Args:
            reader: an already-open PdfReader for pdf_path, to avoid
                re-parsing the same file twice when the caller already has
                one open (e.g. load_pdf).
        """
        if reader is None:
            reader = PDFHandler.load_pdf(pdf_path)
        refs = []
        for idx, page in enumerate(reader.pages):
            try:
                width, height = PDFHandler.get_page_dimensions(page)
                rotation = int(page.get('/Rotate', 0) or 0)
            except Exception as e:
                print(f"Warning: Could not extract metadata for page {idx + 1} of {pdf_path}: {e}")
                width, height, rotation = 612, 792, 0
            refs.append(PageRef(source_path=pdf_path, source_index=idx,
                                 width=width, height=height, rotation=rotation))
        return refs

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
            reader = PDFHandler.load_pdf(pdf_path)

            # Page identity + dimensions -- single source of truth for both
            # doc.pages (page management) and doc.metadata['pages'] (kept
            # in sync below for every existing reader that expects it).
            doc.pages = PDFLoader.build_page_refs(pdf_path, reader=reader)
            doc.page_count = len(doc.pages)

            page_dimensions = [
                {
                    'page_number': i + 1,
                    'width': ref.width,
                    'height': ref.height,
                    'rotation': ref.rotation,
                    'aspect_ratio': (ref.width / ref.height) if ref.height > 0 else 1.0,
                }
                for i, ref in enumerate(doc.pages)
            ]

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
