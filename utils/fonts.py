"""
Font management and registration
"""

import os
from utils.constants import FONT_MAPPING, PROJECT_ROOT

# Lazy imports - only when needed
_pdfmetrics = None
_TTFont = None
_registered_fonts = set()


def ensure_reportlab_available():
    """Ensure reportlab modules are available"""
    global _pdfmetrics, _TTFont
    if _pdfmetrics is None:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            _pdfmetrics = pdfmetrics
            _TTFont = TTFont
        except ImportError:
            return False
    return True


def register_custom_fonts():
    """Register custom TTF fonts (e.g., Nepali fonts)"""
    if not ensure_reportlab_available():
        return
    
    # Try to register Preeti font if it exists
    preeti_path = os.path.join(PROJECT_ROOT, 'preeti.ttf')
    if os.path.exists(preeti_path) and _pdfmetrics and _TTFont:
        try:
            if 'Preeti' not in _registered_fonts:
                _pdfmetrics.registerFont(_TTFont('Preeti', preeti_path))
                _registered_fonts.add('Preeti')
                FONT_MAPPING['Preeti'] = 'Preeti'
        except Exception as e:
            print(f"Warning: Could not register Preeti font: {e}")


def get_reportlab_font(font_name):
    """
    Get ReportLab-compatible font name
    
    Args:
        font_name: Display font name
        
    Returns:
        ReportLab font name
    """
    return FONT_MAPPING.get(font_name, 'Helvetica')


def get_available_tk_fonts():
    """
    Get available system fonts for Tkinter
    
    Returns:
        List of font family names
    """
    try:
        import tkinter.font as tkFont
        return list(tkFont.families())
    except:
        return []


def get_filtered_fonts(available_fonts=None):
    """
    Get a filtered list of common fonts that are actually available
    
    Args:
        available_fonts: List of available font names (from tkFont.families())
                        If None, will auto-detect
        
    Returns:
        List of available common fonts
    """
    from utils.constants import COMMON_FONTS
    
    if available_fonts is None:
        available_fonts = get_available_tk_fonts()
    
    # Filter to include only available fonts
    filtered = [font for font in COMMON_FONTS if font in available_fonts]
    
    # If no common fonts are available, return first 10 available fonts
    if not filtered and available_fonts:
        filtered = available_fonts[:10]
    
    return filtered if filtered else ['Helvetica']
