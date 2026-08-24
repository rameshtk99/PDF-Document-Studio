"""
PDF Document Studio -- the real, wired-together GUI.

Composes the previously-isolated Phase 1 building blocks into one working
window: PDFViewerWidget (thumbnails + canvas + zoom/nav), PageSettingsPanel
+ QuickFooterPanel (per-page vs flat-same-everywhere footer editing, as
tabs docked right next to the live preview), ImageOverlayController +
ImagePropertiesPanel (interactive image placement), UndoRedoManager (real
Ctrl+Z/Ctrl+Y), ProjectManager (.pdfeditor save/load), and DocumentExporter
(real, per-page, white-space-aware PDF output).

CLI (batch/cli.py) and the legacy flat FooterApp are untouched -- this
module only changes what `python main.py` launches by default. The
original standalone tool also stays reachable from Tools > Simple Footer
Tool (Classic) as a separate window, for anyone who prefers that flow.
"""

import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Optional

from models import Document
from pdf import PDFLoader, ImageManager, ImagePlacement, DocumentExporter
from viewer import PDFViewerWidget
from utils.project_manager import ProjectManager
from utils.constants import PROJECT_ROOT

from app.page_settings import PageSettingsPanel
from app.quick_footer_panel import QuickFooterPanel
from app.image_editor import ImageEditor
from app.undo_redo import UndoRedoManager
from app.document_commands import AddObjectCommand
from app.image_overlay import ImageOverlayController, ImagePropertiesPanel
from app.compress_dialog import CompressDialog
from app.footer_preview import FooterPreviewController

_FIELDS_THAT_EDIT_TEXT = ('Entry', 'TEntry', 'TCombobox', 'Spinbox', 'Text')


class PDFEditorApp:
    """Main integrated editor window"""

    def __init__(self, root):
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

        insert_menu = tk.Menu(menubar, tearoff=0)
        insert_menu.add_command(label="Add Image / Stamp...", command=self.add_image)
        menubar.add_cascade(label="Insert", menu=insert_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Simple Footer Tool (Classic)...", command=self.open_classic_tool)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        self.root.config(menu=menubar)

    def _build_toolbar(self):
        toolbar = tk.Frame(self.root, bg='lightgray')
        toolbar.grid(row=0, column=0, sticky='ew')

        def add_button(text, command, doc_required=False):
            b = tk.Button(toolbar, text=text, command=command)
            b.pack(side=tk.LEFT, padx=2, pady=2)
            if doc_required:
                self._doc_buttons.append(b)
            return b

        self.open_button = add_button("Open PDF", self.open_pdf)
        add_button("Save Project", self.save_project, doc_required=True)
        add_button("Export PDF", self.export_pdf, doc_required=True)
        tk.Label(toolbar, text="|", bg='lightgray').pack(side=tk.LEFT, padx=4)
        add_button("Undo", self.undo, doc_required=True)
        add_button("Redo", self.redo, doc_required=True)
        tk.Label(toolbar, text="|", bg='lightgray').pack(side=tk.LEFT, padx=4)
        add_button("Add Image", self.add_image, doc_required=True)

    def _build_layout(self):
        # Grid (not pack) on self.root for the toolbar/content/status-bar
        # stack: pack's cavity-sharing with a PanedWindow child that has
        # expand=True was leaving the bottom-packed status/progress bars
        # squeezed to ~1px with no reliable way to reclaim their space.
        # Grid with an explicit expanding row is deterministic.
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        content = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        content.grid(row=1, column=0, sticky='nsew')

        self.pdf_viewer = PDFViewerWidget(
            content, on_page_changed=self._on_page_changed, on_after_render=self._on_after_render
        )
        content.add(self.pdf_viewer, stretch="always", width=850)

        self.footer_preview = FooterPreviewController(self.pdf_viewer)

        side_panel = tk.Frame(content)
        content.add(side_panel, width=340)

        self.side_notebook = ttk.Notebook(side_panel)
        self.side_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.quick_footer_panel = QuickFooterPanel(
            self.side_notebook, undo_manager=self.undo_manager,
            on_preview_changed=self._on_footer_preview_changed,
            on_export_requested=self.export_pdf,
            on_compress_requested=self.compress_pdf,
        )
        self.quick_footer_panel.get_current_page = lambda: self.pdf_viewer.current_page
        self.side_notebook.add(self.quick_footer_panel, text="Quick Footer")

        self.page_settings_panel = PageSettingsPanel(
            self.side_notebook, undo_manager=self.undo_manager,
            on_settings_changed=self._on_footer_settings_changed,
            on_export_requested=self.export_pdf,
            on_preview_changed=self._on_footer_preview_changed,
        )
        self.side_notebook.add(self.page_settings_panel, text="Page Settings")

        self.image_overlay = ImageOverlayController(
            self.pdf_viewer, self.image_manager, self.image_editor, self.undo_manager,
            on_selection_changed=self._on_image_selection_changed,
        )

        self.image_properties = ImagePropertiesPanel(
            side_panel, self.undo_manager,
            on_applied=self.image_overlay.redraw,
            on_selection_changed=self.image_overlay.select,
        )
        self.image_properties.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _build_status_bar(self):
        self.status_bar = tk.Label(self.root, text="No document loaded", anchor='w',
                                    bd=1, relief=tk.SUNKEN)
        self.status_bar.grid(row=2, column=0, sticky='ew')

        # Thin indeterminate progress bar, animated only while something
        # is loading/exporting -- a clearer "working" signal than the
        # status text alone, without touching the mouse cursor.
        self.busy_bar = ttk.Progressbar(self.root, mode='indeterminate', length=200)
        self.busy_bar.grid(row=3, column=0, sticky='ew')

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
        self.page_settings_panel.load_document(document)
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
        messagebox.showerror(title, message)

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
            messagebox.showerror("Save Failed", str(e))

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
            messagebox.showinfo("Saved", f"Project saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))

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
        messagebox.showinfo("Export Complete", message)

    def _on_export_error(self, message):
        self._set_ui_busy(False)
        messagebox.showerror("Export Failed", message)

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
        messagebox.showerror("Compress PDF", message)

    def open_classic_tool(self):
        from app.gui_app import FooterApp
        top = tk.Toplevel(self.root)
        self._set_window_icon(top)
        FooterApp(top)

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
            messagebox.showwarning("No Document", "Open a PDF first.")
            return
        path = filedialog.askopenfilename(
            title="Select Image / Stamp",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff")])
        if not path:
            return

        valid, error = ImageManager.validate_image_file(path)
        if not valid:
            messagebox.showerror("Invalid Image", error)
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
        self.page_settings_panel.set_current_page(page_num)
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

    def _on_footer_settings_changed(self):
        if self.document:
            self.document.set_modified(True)
        self._update_status()

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
            self._refresh_after_undo_redo()

    def redo(self):
        cmd = self.undo_manager.redo()
        if cmd:
            self._refresh_after_undo_redo()

    def _refresh_after_undo_redo(self):
        self.image_overlay.redraw()
        # Any in-progress typing draft is now stale relative to the
        # (just-changed) document state -- drop it so the preview falls
        # back to showing the real, current footer.
        self.footer_preview.clear_draft()
        self.page_settings_panel.set_current_page(self.page_settings_panel.get_current_page())
        self.quick_footer_panel.sync_from_document()
        self._update_status()

    # ---- misc UI helpers ---------------------------------------------------------

    def _set_document_dependent_state(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for b in self._doc_buttons:
            b.config(state=state)

    def _set_ui_busy(self, busy: bool, message: str = ""):
        self.status_bar.config(
            text=("⏳ " + message) if busy else self._status_text(),
            fg='#8a5a00' if busy else 'black',
        )
        if busy:
            self.busy_bar.start(12)
        else:
            self.busy_bar.stop()
        self.root.update_idletasks()

    def _begin_loading(self, message: str):
        """Show a visible loading indicator (status text + hourglass
        cursor) and lock out re-entrant Open actions while a background
        load is in progress -- opening a PDF/project used to block the
        whole window with zero feedback, which looked like it had hung.
        """
        self._loading = True
        self.open_button.config(state=tk.DISABLED)
        self._set_ui_busy(True, message)

    def _end_loading(self):
        self._loading = False
        self.open_button.config(state=tk.NORMAL)
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
        self.status_bar.config(text=self._status_text())
