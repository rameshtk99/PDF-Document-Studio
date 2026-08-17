"""
PDF handling modules
"""

from pdf.pdf_handler import PDFHandler, FooterGenerator, ensure_pdf_libraries
from pdf.pdf_loader import PDFLoader
from pdf.white_space_detector import WhiteSpaceDetector, PageAnalysis
from pdf.page_adjuster import PageAdjuster, AdjustmentConfig, apply_adjustments_to_pdf
from pdf.image_manager import ImageManager, ImagePlacement
from pdf.document_exporter import DocumentExporter, ExportResult
from pdf.pdf_compressor import PDFCompressor, CompressionResult, CompressionMode, PDFCompressionError

__all__ = [
    'PDFHandler',
    'FooterGenerator',
    'PDFLoader',
    'WhiteSpaceDetector',
    'PageAnalysis',
    'PageAdjuster',
    'AdjustmentConfig',
    'apply_adjustments_to_pdf',
    'ImageManager',
    'ImagePlacement',
    'DocumentExporter',
    'ExportResult',
    'PDFCompressor',
    'CompressionResult',
    'CompressionMode',
    'PDFCompressionError',
    'ensure_pdf_libraries',
]
