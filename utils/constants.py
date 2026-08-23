"""
PDF Footer Editor - Constants and Configuration
"""

import os
import sys

# Get the project root directory. When running from a PyInstaller one-file EXE,
# resources are extracted under sys._MEIPASS, which is the correct base for
# bundled assets like logo.ico and .json configuration files.
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    PROJECT_ROOT = sys._MEIPASS
else:
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

# Named Quick Footer drafts (user-saved presets, distinct from the single
# auto-draft above). Stored under the user's own AppData\Local rather than
# temp (survives temp-cleanup/reboots) or the install folder (would need
# admin rights to write to) -- writable for a normal user both when run
# from source and from a packaged EXE.
QUICK_FOOTER_DRAFTS_DIR = os.path.join(
    os.path.expanduser('~'), 'AppData', 'Local', 'PDFDocumentStudio')
QUICK_FOOTER_DRAFTS_FILE = os.path.join(QUICK_FOOTER_DRAFTS_DIR, 'quick_footer_drafts.json')

# Project file extension
PROJECT_FILE_EXTENSION = '.pdfeditor'

# Coordinate system
PDF_POINT_TO_INCH = 1 / 72.0
PDF_POINT_TO_MM = 10 / 283.465
INCH_TO_PDF_POINT = 72.0
MM_TO_PDF_POINT = 283.465 / 10.0
