"""
PDF Document Studio -- the real, wired-together GUI.

Composes the previously-isolated Phase 1 building blocks into one working
window: PDFViewerWidget (thumbnails + canvas + zoom/nav), QuickFooterPanel
(flat, same-footer-everywhere editing) + ToolsPanel (compress/add image-
stamp/insert-pages/export) as tabs docked right next to the live preview,
ImageOverlayController + ImagePropertiesPanel (interactive image
placement), UndoRedoManager (real Ctrl+Z/Ctrl+Y), ProjectManager
(.pdfeditor save/load), and DocumentExporter (real, per-page,
white-space-aware PDF output).

CLI (batch/cli.py) and the legacy flat FooterApp are untouched -- this
module only changes what `python main.py` launches by default. The
original standalone tool also stays reachable from Tools > Simple Footer
Tool (Classic) as a separate window, for anyone who prefers that flow.
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
from utils.widgets import create_button, create_icon_button, vertical_separator, SegmentedTabs

from app.tools_panel import ToolsPanel
from app.quick_footer_panel import QuickFooterPanel
from app.image_editor import ImageEditor
from app.undo_redo import UndoRedoManager
from app.document_commands import (
    AddObjectCommand, DeletePageCommand, MovePageCommand, InsertPagesCommand,
)
from app.image_overlay import ImageOverlayController, ImagePropertiesPanel
from app.compress_dialog import CompressDialog
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
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open PDF...", command=self.open_pdf, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Open Project...", command=self.open_project)
        file_menu.add_command(label="Save Project", command=self.save_project, accelerator="Ctrl+S")
        file_menu.add_command(label="Save Project As...", command=self.save_project_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Export PDF...", command=self.export_pdf, accelerator="Ctrl+E")
        file_menu.add_command(label="Compress PDF...", command=self.open_compress_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Copy Image(s)",  command=self._copy_images,  accelerator="Ctrl+C")
        edit_menu.add_command(label="Paste Image(s)", command=self._paste_images, accelerator="Ctrl+V")
        edit_menu.add_separator()
        edit_menu.add_command(label="Group Images",   command=self._group_images,   accelerator="Ctrl+G")
        edit_menu.add_command(label="Ungroup Images", command=self._ungroup_images, accelerator="Ctrl+Shift+G")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom In", command=lambda: self.pdf_viewer.zoom_in(), accelerator="Ctrl++")
        view_menu.add_command(label="Zoom Out", command=lambda: self.pdf_viewer.zoom_out(), accelerator="Ctrl+-")
        view_menu.add_command(label="Actual Size (100%)", command=lambda: self.pdf_viewer.zoom_100(), accelerator="Ctrl+0")
        view_menu.add_separator()
        view_menu.add_command(label="Fit Page", command=lambda: self.pdf_viewer.fit_page())
        view_menu.add_command(label="Fit Width", command=lambda: self.pdf_viewer.fit_width())
        view_menu.add_separator()
        view_menu.add_command(label="Next Page", command=lambda: self.pdf_viewer.next_page(), accelerator="Page Down")
        view_menu.add_command(label="Previous Page", command=lambda: self.pdf_viewer.prev_page(), accelerator="Page Up")
        menubar.add_cascade(label="View", menu=view_menu)

        insert_menu = tk.Menu(menubar, tearoff=0)
        insert_menu.add_command(label="Add Image / Stamp...", command=self.add_image)
        insert_menu.add_command(label="Insert Page(s) from PDF...", command=self.insert_pages_from_pdf)
        menubar.add_cascade(label="Insert", menu=insert_menu)

        pages_menu = tk.Menu(menubar, tearoff=0)
        pages_menu.add_command(label="Move Page Up", command=lambda: self._menu_move_current(-1))
        pages_menu.add_command(label="Move Page Down", command=lambda: self._menu_move_current(1))
        pages_menu.add_separator()
        pages_menu.add_command(label="Insert Page(s) Before...", command=lambda: self._open_insert_pages_dialog(
            at_page=self.pdf_viewer.current_page) if self.document else None)
        pages_menu.add_command(label="Insert Page(s) After...", command=lambda: self._open_insert_pages_dialog(
            at_page=self.pdf_viewer.current_page + 1) if self.document else None)
        pages_menu.add_separator()
        pages_menu.add_command(label="Delete Current Page", command=lambda: self._confirm_and_delete_page(
            self.pdf_viewer.current_page) if self.document else None, accelerator="Delete")
        menubar.add_cascade(label="Pages", menu=pages_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Simple Footer Tool (Classic)...", command=self.open_classic_tool)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_command(label="About PDF Document Studio", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

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
        toolbar.grid(row=0, column=0, sticky='ew')
        toolbar.grid_propagate(False)

        # No app name here -- the OS title bar already says it, and
        # repeating it just spends toolbar width on something the user
        # can't act on. The document name lives in the status bar.
        def group(pad_left: int = 0):
            f = ctk.CTkFrame(toolbar, fg_color="transparent")
            f.pack(side=tk.LEFT, padx=(pad_left, 0))
            return f

        # ---- File actions: visual hierarchy -- Export is the one
        # standout primary action, Open/Save are secondary. ------------
        file_group = group(pad_left=ui_theme.SPACE_12)
        self.open_button = create_button(
            file_group, text="Open PDF", icon="open", command=self.open_pdf,
            variant="secondary", height=32, tooltip="Open a PDF file (Ctrl+O)")
        self.open_button.pack(side=tk.LEFT, padx=(0, 6))

        save_btn = create_button(
            file_group, text="Save Project", icon="save", command=self.save_project,
            variant="secondary", height=32, tooltip="Save project (Ctrl+S)")
        save_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._doc_buttons.append(save_btn)

        export_btn = create_button(
            file_group, text="Export PDF", icon="export", command=self.export_pdf,
            variant="primary", height=32, tooltip="Export the finished PDF (Ctrl+E)")
        export_btn.pack(side=tk.LEFT)
        self._doc_buttons.append(export_btn)

        vertical_separator(toolbar, height=24)

        # ---- Editing: compact icon-only utility actions. --------------
        edit_group = group()
        undo_btn = create_icon_button(edit_group, "undo", command=self.undo,
                                       tooltip="Undo (Ctrl+Z)", height=32, width=32)
        undo_btn.pack(side=tk.LEFT, padx=(0, 2))
        self._doc_buttons.append(undo_btn)

        redo_btn = create_icon_button(edit_group, "redo", command=self.redo,
                                       tooltip="Redo (Ctrl+Y)", height=32, width=32)
        redo_btn.pack(side=tk.LEFT)
        self._doc_buttons.append(redo_btn)

        vertical_separator(toolbar, height=24)

        # ---- Insert: secondary action. ---------------------------------
        insert_group = group()
        add_image_btn = create_button(
            insert_group, text="Add Image", icon="add_image", command=self.add_image,
            variant="secondary", height=32, tooltip="Place an image or stamp on the current page")
        add_image_btn.pack(side=tk.LEFT)
        self._doc_buttons.append(add_image_btn)

        # ---- View: panel toggles, right-aligned. Kept apart from the
        # document actions on the left -- these change the workspace, not
        # the document. ---------------------------------------------------
        self.right_panel_button = create_icon_button(
            toolbar, "panel_right", command=self.toggle_side_panel,
            tooltip="Hide properties panel", height=32, width=32, variant="tertiary")
        self.right_panel_button.pack(side=tk.RIGHT, padx=(0, ui_theme.SPACE_12))

        self.left_panel_button = create_icon_button(
            toolbar, "panel_left", command=self.toggle_pages_panel,
            tooltip="Hide pages panel", height=32, width=32, variant="tertiary")
        self.left_panel_button.pack(side=tk.RIGHT, padx=(0, 2))

    def _build_layout(self):
        # Grid (not pack) on self.root for the toolbar/content/status-bar
        # stack: pack's cavity-sharing with a PanedWindow child that has
        # expand=True was leaving the bottom-packed status/progress bars
        # squeezed to ~1px with no reliable way to reclaim their space.
        # Grid with an explicit expanding row is deterministic.
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        content = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL, sashrelief=tk.FLAT, sashwidth=6,
            bg=ui_theme.resolve(ui_theme.BG_APP), bd=0,
            background=ui_theme.resolve(ui_theme.BG_APP))
        content.grid(row=1, column=0, sticky='nsew')

        self.pdf_viewer = PDFViewerWidget(
            content, on_page_changed=self._on_page_changed, on_after_render=self._on_after_render,
            on_page_action=self._on_page_action,
            on_page_reorder=self._execute_move_page,
            on_open_requested=self.open_pdf,
        )
        content.add(self.pdf_viewer, stretch="always", width=850)

        self.footer_preview = FooterPreviewController(self.pdf_viewer)

        side_panel = tk.Frame(content, bg=ui_theme.resolve(ui_theme.BG_APP))
        content.add(side_panel, width=340)

        self.side_notebook = SegmentedTabs(side_panel, fg_color=ui_theme.BG_APP)

        tab_footer = self.side_notebook.add("Quick Footer")
        self.quick_footer_panel = QuickFooterPanel(
            tab_footer, undo_manager=self.undo_manager,
            on_preview_changed=self._on_footer_preview_changed,
            on_export_requested=self.export_pdf,
            on_compress_requested=self.compress_pdf,
        )
        self.quick_footer_panel.get_current_page = lambda: self.pdf_viewer.current_page
        self.quick_footer_panel.pack(fill=tk.BOTH, expand=True)

        tab_tools = self.side_notebook.add("Tools")
        self.tools_panel = ToolsPanel(
            tab_tools,
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

        self.image_properties = ImagePropertiesPanel(
            side_panel, self.undo_manager,
            on_applied=self.image_overlay.redraw,
            on_selection_changed=self.image_overlay.select,
        )
        # Packed BOTTOM/no-expand before the (TOP, expand=True) notebook
        # below -- this way Image Properties keeps its natural content
        # height as a fixed bottom dock, and Quick Footer/Tools get
        # whatever vertical space is left, instead of the two splitting
        # the panel 50/50.
        self.image_properties.pack(side=tk.BOTTOM, fill=tk.X)
        self.side_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Kept for toggle_side_panel(), which removes/re-adds this pane.
        self._content_panes = content
        self._side_panel = side_panel
        self._side_panel_width = 340
        self._side_panel_hidden = False

    # ---- panel visibility -------------------------------------------------

    def toggle_side_panel(self):
        """Show/hide the whole right-hand properties column.

        PanedWindow has no "hide this pane" -- forget() drops it and
        add() puts it back at the end, which is the right place anyway
        since it's the last pane. The width it had is remembered so the
        pane comes back the size the user left it, not the default.
        """
        if self._side_panel_hidden:
            self._content_panes.add(self._side_panel, width=self._side_panel_width)
        else:
            try:
                self._side_panel_width = max(200, self._side_panel.winfo_width())
            except tk.TclError:
                pass
            self._content_panes.forget(self._side_panel)
        self._side_panel_hidden = not self._side_panel_hidden
        self._sync_panel_buttons()
        # The workspace just gained/lost the panel's width -- refit and
        # recenter the page for it.
        self.pdf_viewer.refresh_layout()

    def toggle_pages_panel(self):
        self.pdf_viewer.toggle_thumbnails()
        self._sync_panel_buttons()

    def _sync_panel_buttons(self):
        """Keep the toolbar toggles' tooltips honest about what they do next."""
        pages_hidden = self.pdf_viewer.thumbnails_collapsed()
        self.left_panel_button.tooltip.set_text(
            "Show pages panel" if pages_hidden else "Hide pages panel")
        self.right_panel_button.tooltip.set_text(
            "Show properties panel" if self._side_panel_hidden else "Hide properties panel")

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color=ui_theme.BG_SURFACE, corner_radius=0, height=26)
        bar.grid(row=2, column=0, sticky='ew')
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
        self.busy_bar.grid(row=3, column=0, sticky='ew')
        self._busy_job = None
        self._busy_value = 0.0

    def _bind_shortcuts(self):
        self.root.bind_all('<Control-z>', lambda e: self.undo())
        self.root.bind_all('<Control-y>', lambda e: self.redo())
        self.root.bind_all('<Control-Shift-Z>', lambda e: self.redo())
        self.root.bind_all('<Control-o>', lambda e: self.open_pdf())
        self.root.bind_all('<Control-s>', lambda e: self.save_project())
        self.root.bind_all('<Control-e>', lambda e: self.export_pdf())
        self.root.bind_all('<Delete>', self._delete_selected_image)
        # Image-specific shortcuts fire only when no text field has focus.
        # Bound once here (root-level, focus-independent) rather than also
        # on the canvas widget -- binding the same sequence in both places
        # made Tk fire both handlers on a single keypress, which is what
        # made copy/paste/group feel unreliable (double-invoked).
        self.root.bind_all('<Control-c>', self._copy_images)
        self.root.bind_all('<Control-v>', self._paste_images)
        self.root.bind_all('<Control-g>', lambda e: self._group_images_if_canvas(e))
        self.root.bind_all('<Control-G>', lambda e: self._ungroup_images_if_canvas(e))
        # Zoom / page navigation -- '=' fires for both Ctrl+= and Ctrl+Shift+=
        # (i.e. Ctrl++ on most keyboard layouts, no separate Shift binding needed).
        self.root.bind_all('<Control-equal>', lambda e: self.pdf_viewer.zoom_in())
        self.root.bind_all('<Control-minus>', lambda e: self.pdf_viewer.zoom_out())
        self.root.bind_all('<Control-0>', lambda e: self.pdf_viewer.zoom_100())
        self.root.bind_all('<Prior>', self._prev_page_if_no_text_focus)   # Page Up
        self.root.bind_all('<Next>', self._next_page_if_no_text_focus)    # Page Down

    # ---- document lifecycle ---------------------------------------------

    def open_pdf(self):
        if self._loading:
            return
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path:
            return

        self._begin_loading(f"Loading {os.path.basename(path)} ...")

        def worker():
            try:
                document = PDFLoader.load_pdf(path)
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
        """Common refresh after any page delete/move/insert: reload the
        viewer's continuous-scroll layout + thumbnails from the (already
        mutated) document.pages, land on target_page, and make sure every
        side panel (Page Settings, image selection, footer preview) drops
        anything tied to the old page arrangement."""
        if not self.document:
            return
        target_page = max(1, min(target_page, self.document.page_count))
        self.pdf_viewer.current_page = target_page
        self.pdf_viewer.refresh_after_page_ops(target_page)
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
        # A draft belongs to the page it was being typed for; switching
        # pages should show that new page's real, already-committed
        # footer, not carry over a stale in-progress edit.
        self.footer_preview.clear_draft()
        self._update_status()

    def _on_after_render(self):
        self.image_overlay.redraw()
        self.footer_preview.redraw()

    def _on_footer_preview_changed(self, draft_config, page_number: int):
        if draft_config is None:
            self.footer_preview.clear_draft()
        else:
            self.footer_preview.set_draft(draft_config, page_number)

    def _on_image_selection_changed(self, image_id: Optional[str]):
        if image_id:
            self.image_properties.set_manager_context(self.image_manager, self.pdf_viewer.current_page)
            self.image_properties.load_object(image_id)
        else:
            self.image_properties.clear()

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
        zoom = self.pdf_viewer.zoom_label.cget("text")
        modified = " *modified*" if self.document.is_modified() else ""
        name = os.path.basename(self.document.pdf_path)
        return f"{name}{modified}  |  Page {page} of {total}  |  Zoom {zoom}"

    def _update_status(self):
        self.status_bar.configure(text=self._status_text())
