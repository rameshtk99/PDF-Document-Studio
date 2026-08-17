"""
PDF Footer Editor - Constants and Configuration
"""

import os

# Get the project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Font mapping for ReportLab compatibility
FONT_MAPPING = {
    'Arial': 'Helvetica',
    'Times New Roman': 'Times-Roman',
    'Courier New': 'Courier',
    'Verdana': 'Helvetica',
    'Tahoma': 'Helvetica',
    'Georgia': 'Times-Roman',
    'Calibri': 'Helvetica',
    'Preeti': 'Helvetica',
    'Ganesh': 'Helvetica', 
    'Kantipur': 'Helvetica'
}

# Common fonts to offer in dropdown
COMMON_FONTS = [
    'Arial', 'Times New Roman', 'Courier New', 'Verdana', 
    'Tahoma', 'Georgia', 'Preeti', 'Calibri', 'Ganesh', 'Kantipur'
]

# Footer defaults
FOOTER_DEFAULT_SPACING_PT = 24  # points (bottom margin)
FOOTER_DEFAULT_LEFT_MARGIN_PT = 36
FOOTER_DEFAULT_RIGHT_MARGIN_PT = 36
FOOTER_DEFAULT_LINE_GAP_PT = 4
FOOTER_DEFAULT_FONT_SIZE = 13
FOOTER_DEFAULT_FONT = 'Helvetica'
FOOTER_DEFAULT_COLUMNS = 5

# Draft file location
import tempfile
DRAFT_FILE_PATH = os.path.join(tempfile.gettempdir(), "pdf_footer_draft.json")

# Project file extension
PROJECT_FILE_EXTENSION = '.pdfeditor'

# Coordinate system
PDF_POINT_TO_INCH = 1 / 72.0
PDF_POINT_TO_MM = 10 / 283.465
INCH_TO_PDF_POINT = 72.0
MM_TO_PDF_POINT = 283.465 / 10.0
