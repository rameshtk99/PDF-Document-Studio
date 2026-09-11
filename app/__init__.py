"""
Application modules

PDFEditorApp is the only export the normal startup path
(main.py::run_gui_mode) actually needs, so it's the only eager import
here. FooterApp/init_gui (the legacy flat-footer tool, only reached via
Tools > "Legacy Footer Tool...") are resolved lazily via module
__getattr__ (PEP 562) instead -- importing them eagerly pulled in
PIL.ImageOps/ImageEnhance on every single app launch for a feature most
sessions never touch.
"""

from app.editor_window import PDFEditorApp

__all__ = ['FooterApp', 'init_gui', 'PDFEditorApp']

_LAZY = {'FooterApp': 'app.gui_app', 'init_gui': 'app.gui_app'}


def __getattr__(name):
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    return getattr(importlib.import_module(module_name), name)
