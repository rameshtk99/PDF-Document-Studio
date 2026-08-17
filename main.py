#!/usr/bin/env python3
"""
PDF Document Studio - Main Entry Point

A visual PDF editor and CLI toolkit. This application lets you:
- View and navigate PDFs with page thumbnails
- Add customized, page-by-page footers with a live preview and undo
- Manage per-page vs. global footer settings independently
- Insert images/stamps with drag, resize, and exact positioning
- Compress PDFs while preserving readability and print quality
- Save/reopen editing projects (.pdfeditor)

Existing CLI and GUI functionality is fully preserved.
"""

import os
import sys

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.config import AppConfig, DependencyChecker
from utils.fonts import register_custom_fonts


def main():
    """Main application entry point"""
    
    # Initialize configuration and check dependencies
    config = AppConfig()
    
    # Ensure dependencies are available
    config.dep_checker.ensure_dependencies()
    
    # Register custom fonts (Nepali, etc.)
    register_custom_fonts()
    
    # Check if CLI arguments are provided (run CLI mode)
    # Skip the first argument which is the script name
    if len(sys.argv) > 1:
        # CLI Mode - arguments provided
        from batch import run_cli
        run_cli()
    elif config.gui_available:
        # GUI Mode
        run_gui_mode()
    else:
        # No GUI and no CLI args - print help
        from batch import run_cli
        run_cli()


def _fix_windows_taskbar_icon():
    """On Windows, a python.exe-hosted GUI app shows python.exe's own
    icon in the taskbar instead of the window's icon, because Explorer
    groups taskbar entries by process AppUserModelID, which defaults to
    python.exe's. Giving this process its own explicit AppUserModelID
    (before any window is created) makes Explorer treat it as its own
    app, so the window's actual icon (see PDFEditorApp/FooterApp's
    root.iconbitmap(logo.ico)) shows in the taskbar too, not just the
    title bar.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'PDFDocumentStudio.PDFEditorApp.1')
    except Exception:
        pass


def run_gui_mode():
    """Run application in GUI mode"""
    try:
        _fix_windows_taskbar_icon()

        import tkinter as tk
        from app import PDFEditorApp

        root = tk.Tk()
        app = PDFEditorApp(root)
        root.mainloop()
    except ImportError as e:
        print(f"Error: Could not import GUI components: {e}", file=sys.stderr)
        print("Falling back to CLI mode.", file=sys.stderr)
        from batch import run_cli
        run_cli()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()