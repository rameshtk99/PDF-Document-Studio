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


def _find_font_file(filename: str) -> str:
    """Search project root then standard system font directories for a TTF file.
    Returns the full path if found, empty string otherwise."""
    candidates = [
        os.path.join(PROJECT_ROOT, filename),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', filename),
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local',
                     'Microsoft', 'Windows', 'Fonts', filename),
        os.path.join('/usr/share/fonts', filename),
        os.path.join('/usr/local/share/fonts', filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # Case-insensitive fallback: scan the Windows Fonts directory
    win_fonts = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    if os.path.isdir(win_fonts):
        low = filename.lower()
        for entry in os.scandir(win_fonts):
            if entry.name.lower() == low and entry.is_file():
                return entry.path
    return ''


def register_custom_fonts():
    """Register Nepali/custom TTF fonts with reportlab.

    Searches the project root, the Windows Fonts directory, and the
    current user's font directory so fonts like Preeti (preeti.ttf)
    are found even when they are installed system-wide rather than
    placed next to the application.
    """
    if not ensure_reportlab_available():
        return

    # All fonts shown in the UI combobox: each entry is (display name) → (TTF filename).
    # Nepali fonts must be embedded as TTF for correct glyph mapping.
    # System fonts are also registered directly so the PDF uses the actual typeface
    # rather than the built-in Type1 approximation (Helvetica, Times-Roman, etc.).
    # Fonts not found on this machine keep their existing FONT_MAPPING fallback.
    fonts_to_register = {
        # Nepali / legacy
        'Preeti':          'preeti.ttf',
        'Ganesh':          'ganesh.ttf',
        'Kantipur':        'kantipur.ttf',
        # Windows system fonts
        'Arial':           'arial.ttf',
        'Times New Roman': 'times.ttf',
        'Courier New':     'cour.ttf',
        'Verdana':         'verdana.ttf',
        'Tahoma':          'tahoma.ttf',
        'Georgia':         'georgia.ttf',
        'Calibri':         'calibri.ttf',
    }

    for font_name, ttf_filename in fonts_to_register.items():
        if font_name in _registered_fonts:
            continue
        path = _find_font_file(ttf_filename)
        if path and _pdfmetrics and _TTFont:
            try:
                _pdfmetrics.registerFont(_TTFont(font_name, path))
                _registered_fonts.add(font_name)
                FONT_MAPPING[font_name] = font_name
                print(f"Registered font '{font_name}' from {path}")
            except Exception as e:
                print(f"Warning: Could not register '{font_name}' ({path}): {e}")


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
