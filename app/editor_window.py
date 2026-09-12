"""
The main editor window: wires PDFViewerWidget (thumbnails + canvas +
zoom/nav), QuickFooterPanel and ToolsPanel, the image overlay and its
properties panel, undo/redo, project save/load, and PDF export.

The CLI (batch/cli.py) and the legacy FooterApp are untouched; the latter
stays reachable from Tools > Simple Footer Tool (Classic).
"""

import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from models import Document
from pdf import PDFLoader, ImageManager, ImagePlacement, DocumentExporter
from viewer import PDFViewerWidget
from utils.project_manager import ProjectManager
from utils.constants import PROJECT_ROOT
from utils.ui_helpers import center_window
from utils import ui_theme
from utils.ui_theme import apply_base_theme
from utils.widgets import create_button, create_icon_button, vertical_separator
from utils import icons as icon_lib
from app.inspector_panel import ModernInspectorPanel, RAIL_WIDTH as RAIL_W
from app.modern_menu import ModernMenuBar, ModernMenuItem

from app.tools_panel import ToolsPanel
from app.file_organizer_panel import FileOrganizerPanel
from app.quick_footer_panel import QuickFooterPanel
from app.image_editor import ImageEditor
from app.undo_redo import UndoRedoManager
from app.document_commands import (
    AddObjectCommand, DeletePageCommand, MovePageCommand, InsertPagesCommand,
    ReorderFilesCommand, DeleteFileCommand,
)
from app.image_overlay import ImageOverlayController, ImagePropertiesPanel
from app.compress_dialog import CompressDialog
from app.import_pdfs_dialog import ImportPdfsDialog
from app.insert_pages_dialog import InsertPagesDialog
from app.footer_preview import FooterPreviewController
from app import modern_dialogs as dialogs

_FIELDS_THAT_EDIT_TEXT = ('Entry', 'TEntry', 'TCombobox', 'Spinbox', 'Text')


class PDFEditorApp:
    """Main integrated editor window"""

    def __init__(self, root):
        apply_base_theme()
        self.root = root
        root.title("PDF Document Studio")
        self._set_initial_geometry(root)
        self._set_window_icon(root)

        self.document: Optional[Document] = None
        self.project_manager = ProjectManager()
        self.image_manager = ImageManager()
        self.image_editor = ImageEditor()
        self.undo_manager = UndoRedoManager()
        self._doc_buttons = []
        self._loading = False

        self._build_menu()
        self._build_toolbar()
        self._build_layout()
        self._build_status_bar()
        self._bind_shortcuts()

        self._set_document_dependent_state(False)

    # ---- layout construction -------------------------------------------

    def _build_menu(self):
        self.menubar = ModernMenuBar(self.root)
        self.menubar.grid(row=0, column=0, sticky='ew')

        self.menubar.add_menu("file", "File", icon="open", items=[
            ModernMenuItem("Open PDF...", command=self.open_pdf, accelerator="Ctrl+O"),
            ModernMenuItem("Import Multiple PDFs...", command=self.import_pdfs),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Open Project...", command=self.open_project),
            ModernMenuItem("Save Project", command=self.save_project, accelerator="Ctrl+S"),
            ModernMenuItem("Save Project As...", command=self.save_project_as, accelerator="Ctrl+Shift+S"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Export PDF...", command=self.export_pdf, accelerator="Ctrl+E", icon="export"),
            ModernMenuItem("Compress PDF...", command=self.open_compress_dialog, icon="compress"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Close Document", command=self.close_document, accelerator="Ctrl+W"),
            ModernMenuItem("Exit", command=self.quit_app, accelerator="Ctrl+Q"),
        ])

        self.menubar.add_menu("edit", "Edit", icon="edit", items=[
            ModernMenuItem("Undo", command=self.undo, accelerator="Ctrl+Z", icon="undo"),
            ModernMenuItem("Redo", command=self.redo, accelerator="Ctrl+Y", icon="redo"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Copy Image(s)", command=self._copy_images, accelerator="Ctrl+C"),
            ModernMenuItem("Paste Image(s)", command=self._paste_images, accelerator="Ctrl+V"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Group Images", command=self._group_images, accelerator="Ctrl+G"),
            ModernMenuItem("Ungroup Images", command=self._ungroup_images, accelerator="Ctrl+Shift+G"),
        ])

        self.menubar.add_menu("view", "View", icon="zoom_in", items=[
            ModernMenuItem("Zoom In", command=lambda: self.pdf_viewer.zoom_in(), accelerator="Ctrl++", icon="zoom_in"),
            ModernMenuItem("Zoom Out", command=lambda: self.pdf_viewer.zoom_out(), accelerator="Ctrl+-", icon="zoom_out"),
            ModernMenuItem("Actual Size (100%)", command=lambda: self.pdf_viewer.zoom_100(), accelerator="Ctrl+0"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Fit Page", command=lambda: self.pdf_viewer.fit_page(), icon="fit_page"),
            ModernMenuItem("Fit Width", command=lambda: self.pdf_viewer.fit_width(), icon="fit_width"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Next Page", command=lambda: self.pdf_viewer.next_page(), accelerator="Page Down", icon="chevron_down"),
            ModernMenuItem("Previous Page", command=lambda: self.pdf_viewer.prev_page(), accelerator="Page Up", icon="chevron_up"),
        ])

        self.menubar.add_menu("insert", "Insert", icon="plus", items=[
            ModernMenuItem("Add Image / Stamp...", command=self.add_image, icon="add_image"),
            ModernMenuItem("Insert Page(s) from PDF...", command=self.insert_pages_from_pdf, icon="insert_pages"),
        ])

        self.menubar.add_menu("pages", "Pages", icon="document", items=[
            ModernMenuItem("Move Page Up", command=lambda: self._menu_move_current(-1), icon="move_up"),
            ModernMenuItem("Move Page Down", command=lambda: self._menu_move_current(1), icon="move_down"),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Insert Page(s) Before...", command=lambda: self._open_insert_pages_dialog(
                at_page=self.pdf_viewer.current_page) if self.document else None),
            ModernMenuItem("Insert Page(s) After...", command=lambda: self._open_insert_pages_dialog(
                at_page=self.pdf_viewer.current_page + 1) if self.document else None),
            ModernMenuItem("", is_separator=True),
            ModernMenuItem("Delete Current Page", command=lambda: self._confirm_and_delete_page(
                self.pdf_viewer.current_page) if self.document else None, accelerator="Delete", icon="delete"),
        ])

        self.menubar.add_menu("tools", "Tools", icon="settings", items=[
            ModernMenuItem("Simple Footer Tool (Classic)...", command=self.open_classic_tool),
        ])

        self.menubar.add_menu("help", "Help", icon="more", items=[
            ModernMenuItem("Keyboard Shortcuts", command=self._show_shortcuts),
            ModernMenuItem("About PDF Document Studio", command=self._show_about),
        ])

    def _menu_move_current(self, delta: int):
        if not self.document:
            return
        p = self.pdf_viewer.current_page
        self._execute_move_page(p, p + delta)

    def _show_shortcuts(self):
        dialogs.show_info(self.root, "Keyboard Shortcuts", (
            "Ctrl+O   Open PDF\n"
            "Ctrl+S   Save Project\n"
            "Ctrl+Shift+S   Save Project As\n"
            "Ctrl+E   Export PDF\n"
            "Ctrl+Z / Ctrl+Y   Undo / Redo\n"
            "Ctrl+C / Ctrl+V   Copy / Paste Image(s)\n"
            "Ctrl+G / Ctrl+Shift+G   Group / Ungroup Images\n"
            "Delete   Delete Selected Image\n"
            "Ctrl++ / Ctrl+-   Zoom In / Out\n"
            "Ctrl+0   Actual Size\n"
            "Page Up / Page Down   Previous / Next Page"
        ))

    def _show_about(self):
        dialogs.show_info(self.root, "About PDF Document Studio", (
            "PDF Document Studio\n\n"
            "A visual PDF editor for footers, page management, image "
            "stamps, and compression."
        ))

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self.root, fg_color=ui_theme.BG_SURFACE, corner_radius=0, height=48)
        toolbar.grid(row=1, column=0, sticky='ew')
        toolbar.grid_propagate(False)

        def group(side=tk.LEFT, padx=(0, 0)):
            f = ctk.CTkFrame(toolbar, fg_color="transparent")
            f.pack(side=side, padx=padx, fill=tk.Y)
            return f

        # ---- Left Group: File actions ----
        left_group = group(side=tk.LEFT, padx=(ui_theme.SPACE_12, 0))

        self.open_button = create_button(
            left_group, text="Open PDF", icon="open", command=self.open_pdf,
            variant="secondary", height=32, tooltip="Open a PDF file (Ctrl+O)")
        self.open_button.pack(side=tk.LEFT, padx=(0, 6), pady=8)

        save_btn = create_button(
            left_group, text="Save", icon="save", command=self.save_project,
            variant="secondary", height=32, tooltip="Save project (Ctrl+S)")
        save_btn.pack(side=tk.LEFT, padx=(0, 6), pady=8)
        self._doc_buttons.append(save_btn)

        export_btn = create_button(
            left_group, text="Export PDF", icon="export", command=self.export_pdf,
            variant="primary", height=32, tooltip="Export the finished PDF (Ctrl+E)")
        export_btn.pack(side=tk.LEFT, pady=8)
        self._doc_buttons.append(export_btn)

        vertical_separator(toolbar, height=22, pad=ui_theme.SPACE_12)

        # ---- Center Group: Document navigation & Zoom ----
        center_group = group(side=tk.LEFT, padx=(0, 0))

        prev_btn = create_icon_button(
            center_group, "chevron_left", command=lambda: self.pdf_viewer.prev_page(),
            tooltip="Previous page (Page Up)", size=13, width=28, height=30)
        prev_btn.pack(side=tk.LEFT, padx=(0, 4), pady=9)
        self._doc_buttons.append(prev_btn)

        self.top_page_label = ctk.CTkLabel(
            center_group, text="No pages", font=ui_theme.font(11, "bold"),
            text_color=ui_theme.TEXT_PRIMARY, width=80)
        self.top_page_label.pack(side=tk.LEFT, padx=4, pady=9)

        next_btn = create_icon_button(
            center_group, "chevron_right", command=lambda: self.pdf_viewer.next_page(),
            tooltip="Next page (Page Down)", size=13, width=28, height=30)
        next_btn.pack(side=tk.LEFT, padx=(4, 0), pady=9)
        self._doc_buttons.append(next_btn)

        vertical_separator(center_group, height=20, pad=ui_theme.SPACE_8)

        zoom_out_btn = create_icon_button(
            center_group, "zoom_out", command=lambda: self.pdf_viewer.zoom_out(),
            tooltip="Zoom out (Ctrl+-)", size=13, width=28, height=30)
        zoom_out_btn.pack(side=tk.LEFT, padx=(0, 4), pady=9)
        self._doc_buttons.append(zoom_out_btn)

        self.top_zoom_label = ctk.CTkLabel(
            center_group, text="100%", width=46, font=ui_theme.font(11),
            text_color=ui_theme.TEXT_PRIMARY)
        self.top_zoom_label.pack(side=tk.LEFT, padx=4, pady=9)

        zoom_in_btn = create_icon_button(
            center_group, "zoom_in", command=lambda: self.pdf_viewer.zoom_in(),
            tooltip="Zoom in (Ctrl++)", size=13, width=28, height=30)
        zoom_in_btn.pack(side=tk.LEFT, padx=(4, 6), pady=9)
        self._doc_buttons.append(zoom_in_btn)

        fit_page_btn = create_button(
            center_group, text="Fit Page", icon="fit_page",
            command=lambda: self.pdf_viewer.fit_page(),
            variant="ghost", height=30, icon_size=13, tooltip="Fit whole page in view")
        fit_page_btn.pack(side=tk.LEFT, padx=2, pady=9)
        self._doc_buttons.append(fit_page_btn)

        fit_width_btn = create_button(
            center_group, text="Fit Width", icon="fit_width",
            command=lambda: self.pdf_viewer.fit_width(),
            variant="ghost", height=30, icon_size=13, tooltip="Fit page width to view")
        fit_width_btn.pack(side=tk.LEFT, padx=2, pady=9)
        self._doc_buttons.append(fit_width_btn)

        # ---- Right Group: Edit actions, Add image, Theme, Sidebar toggles ----
        right_group = group(side=tk.RIGHT, padx=(0, ui_theme.SPACE_12))

        self.right_panel_button = create_icon_button(
            right_group, "panel_right", command=self.toggle_side_panel,
            tooltip="Hide properties panel", height=32, width=32, variant="tertiary")
        self.right_panel_button.pack(side=tk.RIGHT, padx=(2, 0), pady=8)

        self.left_panel_button = create_icon_button(
            right_group, "panel_left", command=self.toggle_pages_panel,
            tooltip="Hide pages panel", height=32, width=32, variant="tertiary")
        self.left_panel_button.pack(side=tk.RIGHT, padx=(2, 2), pady=8)

        # Theme toggle button
        curr_mode = ctk.get_appearance_mode()
        theme_icon = "sun" if curr_mode == "Dark" else "moon"
        self.theme_btn = create_icon_button(
            right_group, theme_icon, command=self._toggle_theme,
            tooltip="Toggle Light / Dark theme", height=32, width=32, variant="tertiary")
        self.theme_btn.pack(side=tk.RIGHT, padx=(6, 2), pady=8)

        vertical_separator(right_group, height=20, pad=ui_theme.SPACE_8)

        add_image_btn = create_button(
            right_group, text="Add Image", icon="add_image", command=self.add_image,
            variant="secondary", height=32, tooltip="Place an image or stamp on the current page")
        add_image_btn.pack(side=tk.RIGHT, padx=(4, 6), pady=8)
        self._doc_buttons.append(add_image_btn)

        vertical_separator(right_group, height=20, pad=ui_theme.SPACE_8)

        redo_btn = create_icon_button(
            right_group, "redo", command=self.redo,
            tooltip="Redo (Ctrl+Y)", height=32, width=32)
        redo_btn.pack(side=tk.RIGHT, padx=(2, 2), pady=8)
        self._doc_buttons.append(redo_btn)

        undo_btn = create_icon_button(
            right_group, "undo", command=self.undo,
            tooltip="Undo (Ctrl+Z)", height=32, width=32)
        undo_btn.pack(side=tk.RIGHT, padx=(0, 2), pady=8)
        self._doc_buttons.append(undo_btn)

    def _toggle_theme(self):
        new_mode = ui_theme.toggle_appearance_mode()
        icon_name = "sun" if new_mode == "Dark" else "moon"
        self.theme_btn.configure(image=icon_lib.get(icon_name, size=15, color=ui_theme.TEXT_SECONDARY))

    def _on_viewer_page_info_changed(self, current: int, total: int):
        if hasattr(self, 'top_page_label'):
            if total > 0:
                self.top_page_label.configure(text=f"{current} / {total}")
            else:
                self.top_page_label.configure(text="No pages")

    def _on_viewer_zoom_info_changed(self, text: str):
        if hasattr(self, 'top_zoom_label'):
            self.top_zoom_label.configure(text=text)

    def _build_layout(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        content = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL, sashrelief=tk.FLAT, sashwidth=6,
            bg=ui_theme.resolve(ui_theme.BG_APP), bd=0,
            background=ui_theme.resolve(ui_theme.BG_APP))
        content.grid(row=2, column=0, sticky='nsew')

        self.pdf_viewer = PDFViewerWidget(
            content,
            show_toolbar=False,
            on_page_changed=self._on_page_changed,
            on_after_render=self._on_after_render,
            on_page_action=self._on_page_action,
            on_page_reorder=self._execute_move_page,
            on_open_requested=self.open_pdf,
            on_page_info_changed=self._on_viewer_page_info_changed,
            on_zoom_info_changed=self._on_viewer_zoom_info_changed,
        )
        content.add(self.pdf_viewer, stretch="always", width=850)

        self.footer_preview = FooterPreviewController(self.pdf_viewer)

        side_panel = tk.Frame(content, bg=ui_theme.resolve(ui_theme.BG_PANEL))
        content.add(side_panel, width=340)

        self.side_panels = ModernInspectorPanel(
            side_panel, on_collapsed_change=self._on_side_collapsed_change)
        self.side_panels.pack(fill=tk.BOTH, expand=True)

        body = self.side_panels.add("footer", "Quick Footer", icon="footer", expanded=True)
        self.quick_footer_panel = QuickFooterPanel(
            body, undo_manager=self.undo_manager,
            on_preview_changed=self._on_footer_preview_changed,
            on_export_requested=self.export_pdf,
            on_compress_requested=self.compress_pdf,
            on_applied=self._on_footer_applied,
        )
        self.quick_footer_panel.get_current_page = lambda: self.pdf_viewer.current_page
        self.quick_footer_panel.get_selected_pages = (
            lambda: self.pdf_viewer.thumbnail_panel.get_selected_pages())
        self.quick_footer_panel.pack(fill=tk.BOTH, expand=True)

        body = self.side_panels.add("files", "File Organizer", icon="document", expanded=False)
        self.file_organizer = FileOrganizerPanel(
            body,
            on_reorder=self._reorder_file,
            on_remove=self._confirm_and_remove_file,
            on_file_selected=self._on_file_selected,
        )
        self.file_organizer.pack(fill=tk.BOTH, expand=True)

        body = self.side_panels.add("tools", "Tools", icon="compress", expanded=False)
        self.tools_panel = ToolsPanel(
            body,
            on_compress=self.compress_pdf,
            on_add_image=self.add_image,
            on_insert_pages=self.insert_pages_from_pdf,
            on_export=self.export_pdf,
        )
        self.tools_panel.pack(fill=tk.BOTH, expand=True)

        self.image_overlay = ImageOverlayController(
            self.pdf_viewer, self.image_manager, self.image_editor, self.undo_manager,
            on_selection_changed=self._on_image_selection_changed,
        )

        body = self.side_panels.add("image", "Image Properties", icon="add_image", expanded=False)
        self.image_properties = ImagePropertiesPanel(
            body, self.undo_manager,
            on_applied=self.image_overlay.redraw,
            on_selection_changed=self.image_overlay.select,
        )
        self.image_properties.pack(fill=tk.BOTH, expand=True)
        self.side_panels.set_section_visible("image", False)

        # Kept for toggle_side_panel(), which removes/re-adds this pane.
        self._content_panes = content
        self._side_panel = side_panel
        self._side_panel_width = 340

    # ---- panel visibility -------------------------------------------------

    def toggle_side_panel(self):
        """Collapse the right column to its rail of panel names, or back.

        The pane itself stays in the PanedWindow (only its width shrinks)
        so the rail keeps a way back on screen.
        """
        self.side_panels.toggle_collapsed()

    def toggle_pages_panel(self):
        self.pdf_viewer.toggle_thumbnails()
        self._sync_panel_buttons()

    def _sync_panel_buttons(self):
        """Keep the toolbar toggles' tooltips honest about what they do next."""
        pages_hidden = self.pdf_viewer.thumbnails_collapsed()
        self.left_panel_button.tooltip.set_text(
            "Show pages panel" if pages_hidden else "Hide pages panel")
        self.right_panel_button.tooltip.set_text(
            "Show properties panel" if self.side_panels.collapsed() else "Hide properties panel")

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color=ui_theme.BG_SURFACE, corner_radius=0, height=26)
        bar.grid(row=3, column=0, sticky='ew')
        bar.grid_propagate(False)
        self.status_bar = ctk.CTkLabel(bar, text="No document loaded", anchor='w',
                                        font=ui_theme.font(11), text_color=ui_theme.TEXT_SECONDARY)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=ui_theme.PAD)

        # Thin progress bar, animated only while something is loading/
        # exporting -- a clearer "working" signal than the status text
        # alone. CTkProgressBar has no native indeterminate mode, so
        # busy state is faked with a repeating sweep (same technique as
        # CompressDialog's progress bar).
        self.busy_bar = ctk.CTkProgressBar(self.root, height=4, corner_radius=2,
                                            progress_color=ui_theme.ACCENT)
        self.busy_bar.set(0)
        self.busy_bar.grid(row=4, column=0, sticky='ew')
        self._busy_job = None
        self._busy_value = 0.0

    def _bind_shortcuts(self):
        self.root.bind_all('<Control-z>', lambda e: self.undo())
        self.root.bind_all('<Control-y>', lambda e: self.redo())
        self.root.bind_all('<Control-Shift-Z>', lambda e: self.redo())
        self.root.bind_all('<Control-o>', lambda e: self.open_pdf())
        self.root.bind_all('<Control-s>', lambda e: self.save_project())
        self.root.bind_all('<Control-e>', lambda e: self.export_pdf())
        self.root.bind_all('<Control-w>', self.close_document)
        self.root.bind_all('<Control-q>', self.quit_app)
        self.root.bind_all('<Delete>', self._delete_selected_image)
        # Bound once at root level only -- binding these on the canvas
        # too made Tk fire both handlers per keypress.
        self.root.bind_all('<Control-c>', self._copy_images)
        self.root.bind_all('<Control-v>', self._paste_images)
        self.root.bind_all('<Control-g>', lambda e: self._group_images_if_canvas(e))
        self.root.bind_all('<Control-G>', lambda e: self._ungroup_images_if_canvas(e))
        # '=' covers both Ctrl+= and Ctrl+Shift+= (Ctrl++ on most layouts).
        self.root.bind_all('<Control-equal>', lambda e: self.pdf_viewer.zoom_in())
        self.root.bind_all('<Control-minus>', lambda e: self.pdf_viewer.zoom_out())
        self.root.bind_all('<Control-0>', lambda e: self.pdf_viewer.zoom_100())
        self.root.bind_all('<Prior>', self._prev_page_if_no_text_focus)   # Page Up
        self.root.bind_all('<Next>', self._next_page_if_no_text_focus)    # Page Down

    # ---- document lifecycle ---------------------------------------------

    def open_pdf(self):
        """Open one PDF, or several combined into a single document.

        The chooser allows multi-select; picking exactly one file goes
        straight to loading it (unchanged behaviour), while picking
        several first opens the ordering step, since "which file comes
        first" is a decision only the user can make.
        """
        if self._loading:
            return
        paths = filedialog.askopenfilenames(filetypes=[("PDF files", "*.pdf")])
        if not paths:
            return
        paths = list(paths)

        if len(paths) == 1:
            self._load_pdf_paths(paths)
        else:
            ImportPdfsDialog(self.root, on_import=self._load_pdf_paths,
                              initial_paths=paths)

    def import_pdfs(self):
        """File > Import PDFs...: same combine flow, but starting from an
        empty list so files can be gathered over several picks."""
        if self._loading:
            return
        ImportPdfsDialog(self.root, on_import=self._load_pdf_paths)

    def _load_pdf_paths(self, paths):
        """Load one or more PDFs (in the given order) as the document."""
        if self._loading or not paths:
            return
        paths = list(paths)
        if len(paths) == 1:
            message = f"Loading {os.path.basename(paths[0])} ..."
        else:
            message = f"Combining {len(paths)} PDFs ..."
        self._begin_loading(message)

        def worker():
            try:
                document = PDFLoader.load_pdfs(paths)
                self.root.after(0, lambda: self._on_pdf_loaded(document))
            except Exception as e:
                # Capture now -- `e` is unbound by the time a deferred
                # lambda would run on the main thread via after().
                error_message = str(e)
                self.root.after(0, lambda: self._on_load_error("Cannot Open PDF", error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_pdf_loaded(self, document: Document):
        self.project_manager = ProjectManager()
        self._load_document(document, project_path=None)
        self._end_loading()

    def close_document(self, event=None):
        """Close the open document and return to the empty state (Ctrl+W)."""
        if self._loading or not self.document:
            return
        if not self._confirm_discard_changes("Close Document"):
            return

        self.document = None
        self.project_manager = ProjectManager()
        self.image_manager.load_document(None)
        self.image_editor.load_document(None)
        self.undo_manager.clear()
        self.footer_preview.clear_draft()
        self.image_overlay.select(None)
        self.image_properties.clear()
        self.pdf_viewer.clear_document()
        self.quick_footer_panel.load_document(None)
        self.file_organizer.load_document(None)
        if hasattr(self, 'top_page_label'):
            self.top_page_label.configure(text="No pages")
        if hasattr(self, 'top_zoom_label'):
            self.top_zoom_label.configure(text="100%")
        self._set_document_dependent_state(False)
        self._update_status()

    def quit_app(self, event=None):
        """Exit the application (Ctrl+Q)."""
        if not self._confirm_discard_changes("Exit"):
            return
        self.root.quit()

    def _confirm_discard_changes(self, title: str) -> bool:
        """True if it's safe to proceed -- either nothing is unsaved or
        the user chose to discard."""
        if not self.document or not self.document.is_modified():
            return True
        name = os.path.basename(self.document.pdf_path)
        return dialogs.ask_yes_no(
            self.root, title,
            f"{name} has unsaved changes.\n\nDiscard them?", danger=True)

    def _load_document(self, document: Document, project_path: Optional[str]):
        self.document = document
        self.project_manager.document = document
        if project_path:
            self.project_manager.project_file = Path(project_path)
            document.set_project_path(project_path)

        self.image_manager.load_document(document)
        self.image_editor.load_document(document)
        self.image_editor.set_manager(self.image_manager)
        self.undo_manager.clear()
        self.footer_preview.clear_draft()

        self.pdf_viewer.load_document(document)
        self.quick_footer_panel.load_document(document)
        self.file_organizer.load_document(document)
        self.image_properties.set_manager_context(self.image_manager, self.pdf_viewer.current_page)
        self.image_overlay.select(None)

        self._set_document_dependent_state(True)
        self._update_status()

    def open_project(self):
        if self._loading:
            return
        path = filedialog.askopenfilename(
            filetypes=[("PDF Editor Project", f"*{ProjectManager.FILE_EXTENSION}")])
        if not path:
            return

        self._begin_loading(f"Loading project {os.path.basename(path)} ...")

        def worker():
            try:
                pm = ProjectManager(Path(path))
                document = pm.load()
                self.root.after(0, lambda: self._on_project_loaded(pm, document, path))
            except Exception as e:
                error_message = str(e)
                self.root.after(0, lambda: self._on_load_error("Cannot Open Project", error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_project_loaded(self, pm: ProjectManager, document: Document, path: str):
        self.project_manager = pm
        self._load_document(document, project_path=path)
        self._end_loading()

    def _on_load_error(self, title: str, message: str):
        self._end_loading()
        dialogs.show_error(self.root, title, message)

    def save_project(self):
        if not self.document:
            return
        if not self.project_manager.project_file:
            self.save_project_as()
            return
        try:
            self.project_manager.save(self.document)
            self._update_status()
        except Exception as e:
            dialogs.show_error(self.root, "Save Failed", str(e))

    def save_project_as(self):
        if not self.document:
            return
        default_name = Path(self.document.pdf_path).stem + ProjectManager.FILE_EXTENSION
        path = filedialog.asksaveasfilename(
            defaultextension=ProjectManager.FILE_EXTENSION,
            initialfile=default_name,
            filetypes=[("PDF Editor Project", f"*{ProjectManager.FILE_EXTENSION}")])
        if not path:
            return
        try:
            self.project_manager.save_as(Path(path), self.document)
            self.document.set_project_path(path)
            self._update_status()
            dialogs.show_info(self.root, "Saved", f"Project saved to:\n{path}")
        except Exception as e:
            dialogs.show_error(self.root, "Save Failed", str(e))

    def export_pdf(self):
        if not self.document:
            return
        base, _ = os.path.splitext(os.path.basename(self.document.pdf_path))
        suggested = f"{base}_edited.pdf"
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=suggested,
            filetypes=[("PDF files", "*.pdf")], title="Export PDF As")
        if not path:
            return

        self._set_ui_busy(True, "Exporting...")

        def worker():
            try:
                result = DocumentExporter(self.document).export(path)
                self.root.after(0, lambda: self._on_export_complete(result))
            except Exception as e:
                error_message = str(e)
                self.root.after(0, lambda: self._on_export_error(error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_export_complete(self, result):
        self._set_ui_busy(False)
        message = f"Exported to:\n{result.output_path}"
        if result.adjusted_pages:
            message += (f"\n\n{len(result.adjusted_pages)} page(s) received a minimum "
                        f"layout adjustment to fit their footer: {result.adjusted_pages}")
        if result.warnings:
            message += "\n\nWarnings:\n" + "\n".join(result.warnings)
        dialogs.show_info(self.root, "Export Complete", message)

    def _on_export_error(self, message):
        self._set_ui_busy(False)
        dialogs.show_error(self.root, "Export Failed", message)

    def open_compress_dialog(self):
        current_path = self.document.pdf_path if self.document else None
        CompressDialog(self.root, current_pdf_path=current_path)

    def compress_pdf(self):
        """"Compress PDF" button flow (Quick Footer / Page Settings tabs):
        export the current document's committed state to a throwaway temp
        file -- same content Export PDF would produce -- then hand that to
        CompressDialog so the user picks a strategy/size and it compresses
        + saves to their chosen final path. Unlike open_compress_dialog()
        (Tools menu), this always reflects the live document, not
        whatever's still on disk at self.document.pdf_path.
        """
        if not self.document:
            return
        fd, tmp_path = tempfile.mkstemp(suffix='.pdf', prefix='pdfstudio_precompress_')
        os.close(fd)

        self._set_ui_busy(True, "Preparing for compression...")

        def worker():
            try:
                DocumentExporter(self.document).export(tmp_path)
                self.root.after(0, lambda: self._on_precompress_export_done(tmp_path))
            except Exception as e:
                error_message = str(e)
                self.root.after(0, lambda: self._on_precompress_export_error(tmp_path, error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_precompress_export_done(self, tmp_path):
        self._set_ui_busy(False)
        CompressDialog(self.root, current_pdf_path=tmp_path, cleanup_input_on_close=True)

    def _on_precompress_export_error(self, tmp_path, message):
        self._set_ui_busy(False)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        dialogs.show_error(self.root, "Compress PDF", message)

    # ---- page management (delete / move / insert / combine) -----------------

    def _on_page_action(self, action: str, page_num: int):
        """Dispatch for ThumbnailPanel's right-click page menu -- see
        ThumbnailPanel.__init__'s on_page_action docstring for the
        (action, page_num) contract."""
        if not self.document:
            return
        if action == 'move_up':
            self._execute_move_page(page_num, page_num - 1)
        elif action == 'move_down':
            self._execute_move_page(page_num, page_num + 1)
        elif action == 'delete':
            self._confirm_and_delete_page(page_num)
        elif action == 'insert_before':
            self._open_insert_pages_dialog(at_page=page_num)
        elif action == 'insert_after':
            self._open_insert_pages_dialog(at_page=page_num + 1)

    def _execute_move_page(self, from_page: int, to_page: int):
        if not self.document or not (1 <= to_page <= self.document.page_count):
            return  # already at a boundary -- context menu disables these, but stay safe
        self.undo_manager.execute(MovePageCommand(self.document, from_page - 1, to_page - 1))
        self.document.set_modified(True)
        self._refresh_after_page_ops(target_page=to_page)

    def _confirm_and_delete_page(self, page_num: int):
        if not self.document:
            return
        if self.document.page_count <= 1:
            dialogs.show_error(self.root, "Delete Page", "Cannot delete the only page in the document.")
            return
        if not dialogs.ask_yes_no(
                self.root, "Delete Page", f"Delete page {page_num}?\n\nYou can undo this with Ctrl+Z.",
                danger=True):
            return
        self.undo_manager.execute(DeletePageCommand(self.document, page_num - 1))
        self.document.set_modified(True)
        self._refresh_after_page_ops(target_page=min(page_num, self.document.page_count))

    def insert_pages_from_pdf(self):
        """Insert menu entry point -- no specific position known yet
        (unlike the context menu's Insert Before/After), so default to
        right after whichever page is currently in view."""
        if not self.document:
            dialogs.show_error(self.root, "Insert Pages", "Open a PDF first.")
            return
        self._open_insert_pages_dialog(at_page=self.pdf_viewer.current_page + 1)

    def _open_insert_pages_dialog(self, at_page: int):
        """at_page is the 1-indexed display position the newly-inserted
        pages should end up occupying."""
        def on_insert(refs):
            if not refs or not self.document:
                return
            self.undo_manager.execute(InsertPagesCommand(self.document, at_page - 1, refs))
            self.document.set_modified(True)
            self._refresh_after_page_ops(target_page=at_page)
        InsertPagesDialog(self.root, on_insert=on_insert)

    def _refresh_after_page_ops(self, target_page: int):
        """Refresh after a page delete/move/insert: rebuild the viewer's
        layout and thumbnails from document.pages and land on
        target_page."""
        if not self.document:
            return
        target_page = max(1, min(target_page, self.document.page_count))
        self.pdf_viewer.current_page = target_page
        self.pdf_viewer.refresh_after_page_ops(target_page)
        self.file_organizer.refresh()
        self._on_page_changed(target_page)

    def open_classic_tool(self):
        from app.gui_app import FooterApp
        top = tk.Toplevel(self.root)
        self._set_window_icon(top)
        FooterApp(top)  # sets top's own geometry ("800x600") as part of building its UI
        center_window(top, self.root, 800, 600)

    @staticmethod
    def _set_window_icon(window):
        icon_path = os.path.join(PROJECT_ROOT, 'logo.ico')
        if not os.path.exists(icon_path):
            return
        try:
            window.iconbitmap(icon_path)
        except tk.TclError:
            pass
        # iconbitmap() alone doesn't reliably reach the Windows taskbar/
        # Alt-Tab icon for a python.exe-hosted app -- iconphoto() uses a
        # different underlying mechanism and is more likely to stick
        # there too. Keep a reference on the window so the PhotoImage
        # isn't garbage-collected.
        try:
            from PIL import Image, ImageTk
            photo = ImageTk.PhotoImage(Image.open(icon_path))
            window.iconphoto(True, photo)
            window._icon_photo_ref = photo
        except Exception:
            pass

    @staticmethod
    def _set_initial_geometry(root):
        """Size the window to fit the actual screen instead of a fixed
        1300x850 -- on a 1366x768 laptop screen that request is taller
        than the whole screen, pushing the status bar/loading indicator
        (the last row of the layout) off-screen below the visible area.
        """
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        width = min(1300, screen_w - 60)
        height = min(850, screen_h - 90)  # leave room for taskbar + title bar
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        root.geometry(f"{width}x{height}+{x}+{y}")

    # ---- image objects ----------------------------------------------------

    def add_image(self):
        if not self.document:
            dialogs.show_error(self.root, "No Document", "Open a PDF first.")
            return
        path = filedialog.askopenfilename(
            title="Select Image / Stamp",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff")])
        if not path:
            return

        valid, error = ImageManager.validate_image_file(path)
        if not valid:
            dialogs.show_error(self.root, "Invalid Image", error)
            return

        page_num = self.pdf_viewer.current_page
        page_h = self.pdf_viewer.get_current_page_height_pt() or 792.0
        try:
            from PIL import Image
            with Image.open(path) as im:
                iw, ih = im.size
        except Exception:
            iw, ih = 200, 200
        display_w = 150.0
        display_h = display_w * (ih / iw) if iw else 150.0

        placement = ImagePlacement(
            page_number=page_num, x=72.0, y=max(0.0, page_h - 72.0 - display_h),
            width=display_w, height=display_h,
        )
        cmd = AddObjectCommand(self.image_manager, page_num, placement, path)
        self.undo_manager.execute(cmd)
        self.document.set_modified(True)
        if cmd.image_id:
            self.image_overlay.select(cmd.image_id)
        self.image_overlay.redraw()
        self._update_status()

    def _prev_page_if_no_text_focus(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        self.pdf_viewer.prev_page()

    def _next_page_if_no_text_focus(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        self.pdf_viewer.next_page()

    def _delete_selected_image(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        if self.image_overlay.selected_ids:
            self.image_overlay.delete_selection()
            self.image_properties.clear()

    def _copy_images(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        self.image_overlay._on_copy()

    def _paste_images(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        self.image_overlay._on_paste()

    def _group_images(self):
        self.image_overlay._on_group()

    def _ungroup_images(self):
        self.image_overlay._on_ungroup()

    def _group_images_if_canvas(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        self.image_overlay._on_group()

    def _ungroup_images_if_canvas(self, event=None):
        focused = self.root.focus_get()
        if focused is not None and focused.winfo_class() in _FIELDS_THAT_EDIT_TEXT:
            return
        self.image_overlay._on_ungroup()

    # ---- callbacks ----------------------------------------------------------

    def _on_page_changed(self, page_num: int):
        self.image_properties.set_manager_context(self.image_manager, page_num)
        self.image_overlay.on_page_changed(page_num)
        # A draft belongs to the page it was typed for -- don't carry it
        # over to the page being switched to.
        self.footer_preview.clear_draft()
        self.quick_footer_panel.refresh_scope_hint()
        self._update_status()

    def _on_after_render(self):
        self.image_overlay.redraw()
        self.footer_preview.redraw()

    def _on_footer_preview_changed(self, draft_config, page_number: int):
        if draft_config is None:
            self.footer_preview.clear_draft()
        else:
            self.footer_preview.set_draft(draft_config, page_number)

    # ---- file-level organisation -----------------------------------------

    def _reorder_file(self, from_index: int, to_index: int):
        if not self.document or from_index == to_index:
            return
        self.undo_manager.execute(ReorderFilesCommand(self.document, from_index, to_index))
        self.document.set_modified(True)
        self._refresh_after_page_ops(target_page=1)

    def _confirm_and_remove_file(self, file_index: int):
        if not self.document:
            return
        groups = self.document.file_groups()
        if not (0 <= file_index < len(groups)):
            return
        if len(groups) <= 1:
            dialogs.show_error(self.root, "Remove File",
                                "This is the only file in the document. Use File > Close "
                                "Document to start over.")
            return

        group = groups[file_index]
        name = os.path.basename(group['source_path']) or group['source_path']
        count = len(group['page_indices'])
        if not dialogs.ask_yes_no(
                self.root, "Remove File",
                f"Remove {name} and its {count} page{'s' if count != 1 else ''}?\n\n"
                "You can undo this with Ctrl+Z.", danger=True):
            return

        self.undo_manager.execute(DeleteFileCommand(self.document, file_index))
        self.document.set_modified(True)
        self._refresh_after_page_ops(target_page=1)

    def _on_file_selected(self, file_index: int):
        """Jump the viewer to a file's first page."""
        if not self.document:
            return
        groups = self.document.file_groups()
        if 0 <= file_index < len(groups) and groups[file_index]['page_indices']:
            self.pdf_viewer.goto_page(groups[file_index]['page_indices'][0] + 1)

    def _on_side_collapsed_change(self, collapsed: bool):
        """Shrink the pane to the rail's width when the column collapses."""
        if collapsed:
            try:
                self._side_panel_width = max(200, self._side_panel.winfo_width())
            except tk.TclError:
                pass
            self._content_panes.paneconfigure(self._side_panel, width=RAIL_W + 4)
        else:
            self._content_panes.paneconfigure(self._side_panel, width=self._side_panel_width)
        self._sync_panel_buttons()
        self.pdf_viewer.refresh_layout()

    def _on_footer_applied(self):
        # A scoped apply changes only some pages, so redraw rather than
        # assume the visible page changed.
        self.footer_preview.redraw()
        self._update_status()

    def _on_image_selection_changed(self, image_id: Optional[str]):
        if image_id:
            self.image_properties.set_manager_context(self.image_manager, self.pdf_viewer.current_page)
            self.image_properties.load_object(image_id)
            self.side_panels.set_section_visible("image", True)
            self.side_panels.focus_section("image")
        else:
            self.image_properties.clear()
            self.side_panels.set_section_visible("image", False)

    # ---- undo/redo -----------------------------------------------------------

    def undo(self):
        cmd = self.undo_manager.undo()
        if cmd:
            self._refresh_after_undo_redo(cmd)

    def redo(self):
        cmd = self.undo_manager.redo()
        if cmd:
            self._refresh_after_undo_redo(cmd)

    def _refresh_after_undo_redo(self, cmd=None):
        # Page delete/move/insert change the page collection itself (count,
        # order, which source each page renders from) -- the viewer's
        # layout/thumbnails must be rebuilt from the document, not just
        # have their overlays redrawn, or they'd keep showing stale pages.
        if cmd is not None and getattr(cmd, 'affects_page_structure', False):
            target = max(1, min(self.pdf_viewer.current_page, self.document.page_count))
            self.pdf_viewer.current_page = target
            self.pdf_viewer.refresh_after_page_ops(target)
            self.file_organizer.refresh()

        self.image_overlay.redraw()
        # Any in-progress typing draft is now stale relative to the
        # (just-changed) document state -- drop it so the preview falls
        # back to showing the real, current footer.
        self.footer_preview.clear_draft()
        self.quick_footer_panel.sync_from_document()
        self._update_status()

    # ---- misc UI helpers ---------------------------------------------------------

    def _set_document_dependent_state(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for b in self._doc_buttons:
            b.configure(state=state)

    def _set_ui_busy(self, busy: bool, message: str = ""):
        self.status_bar.configure(
            text=message if busy else self._status_text(),
            text_color='#C9962B' if busy else ui_theme.TEXT_SECONDARY,
        )
        if busy:
            self._start_busy_animation()
        else:
            self._stop_busy_animation()
        self.root.update_idletasks()

    def _start_busy_animation(self):
        def step():
            self._busy_value = (self._busy_value + 0.05) % 1.0
            self.busy_bar.set(self._busy_value)
            self._busy_job = self.root.after(16, step)
        if self._busy_job is None:
            step()

    def _stop_busy_animation(self):
        if self._busy_job is not None:
            try:
                self.root.after_cancel(self._busy_job)
            except tk.TclError:
                pass
            self._busy_job = None
        self.busy_bar.set(0)

    def _begin_loading(self, message: str):
        """Show a visible loading indicator (status text + hourglass
        cursor) and lock out re-entrant Open actions while a background
        load is in progress -- opening a PDF/project used to block the
        whole window with zero feedback, which looked like it had hung.
        """
        self._loading = True
        self.open_button.configure(state=tk.DISABLED)
        self._set_ui_busy(True, message)

    def _end_loading(self):
        self._loading = False
        self.open_button.configure(state=tk.NORMAL)
        self._set_ui_busy(False)

    def _status_text(self) -> str:
        if not self.document:
            return "No document loaded"
        page = self.pdf_viewer.current_page
        total = self.document.page_count
        if hasattr(self, 'top_zoom_label'):
            zoom = self.top_zoom_label.cget("text")
        elif self.pdf_viewer.zoom_label:
            zoom = self.pdf_viewer.zoom_label.cget("text")
        else:
            zoom = f"{int(self.pdf_viewer.zoom_level * 100)}%"
        modified = " *modified*" if self.document.is_modified() else ""
        name = os.path.basename(self.document.pdf_path)
        return f"{name}{modified}  |  Page {page} of {total}  |  Zoom {zoom}"

    def _update_status(self):
        self.status_bar.configure(text=self._status_text())
