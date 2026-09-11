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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.config import AppConfig, DependencyChecker
from utils.fonts import register_custom_fonts


def main():
    """Main application entry point"""
    config = AppConfig()
    config.dep_checker.ensure_dependencies()
    register_custom_fonts()

    if len(sys.argv) > 1:
        from batch import run_cli
        run_cli()
    elif config.gui_available:
        run_gui_mode()
    else:
        from batch import run_cli
        run_cli()


def _fix_windows_taskbar_icon():
    """Gives this process its own AppUserModelID so Explorer shows the
    window's own icon in the taskbar instead of python.exe's."""
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

        import customtkinter as ctk
        from app import PDFEditorApp

        root = ctk.CTk()
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