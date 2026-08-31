"""
Compress PDF dialog -- lets the user pick an input PDF, a maximum output
size, and a compression mode, then runs PDFCompressor in the background
and reports the result. A standalone Toplevel so it works whether or not
a document is currently open in the main editor window.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from pdf import PDFCompressor, CompressionMode
from utils.ui_helpers import center_window

_SIZE_PRESETS = [
    ("Maximum 5 MB", 5.0),
    ("Maximum 10 MB", 10.0),
    ("Maximum 15 MB", 15.0),
    ("Maximum 20 MB", 20.0),
    ("Custom", None),
]

_MODE_LABELS = [
    ("Best Quality", CompressionMode.BEST_QUALITY),
    ("Balanced (recommended)", CompressionMode.BALANCED),
    ("Maximum Reduction", CompressionMode.MAXIMUM),
    ("Lossless only (no image changes)", CompressionMode.LOSSLESS),
]


class CompressDialog(tk.Toplevel):
    def __init__(self, parent, current_pdf_path: Optional[str] = None,
                 cleanup_input_on_close: bool = False):
        """
        Args:
            current_pdf_path: Pre-filled input PDF path.
            cleanup_input_on_close: Delete the input file when this dialog
                closes -- set by callers (e.g. the "Compress PDF" button
                flow) that exported a throwaway temp file just to feed it
                in here, so it doesn't linger after the dialog is done
                with it.
        """
        super().__init__(parent)
        self.title("Compress PDF")
        center_window(self, parent, 500, 520)
        self.resizable(True, True)
        self.minsize(420, 380)
        self.transient(parent)

        self._compressing = False
        self._cleanup_input_on_close = cleanup_input_on_close
        self._input_to_cleanup = current_pdf_path if cleanup_input_on_close else None
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui(current_pdf_path)

    def _build_ui(self, current_pdf_path):
        pad = dict(padx=10, pady=6)

        # Only the result-summary row grows when the dialog is resized (or
        # shrunk to fit a small screen -- see center_window's clamping);
        # everything else, including the button row, keeps its natural
        # size so Compress/Close never get squeezed off-screen the way
        # the Insert-Pages dialog's button bar could.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)  # row 6 = result_text

        tk.Label(self, text="Input PDF:").grid(row=0, column=0, sticky='w', **pad)
        self.input_var = tk.StringVar(value=current_pdf_path or "")
        tk.Entry(self, textvariable=self.input_var, width=42).grid(row=0, column=1, **pad)
        tk.Button(self, text="Browse...", command=self._browse_input).grid(row=0, column=2, **pad)

        tk.Label(self, text="Strategy:").grid(row=1, column=0, sticky='nw', **pad)
        strategy_frame = tk.Frame(self)
        strategy_frame.grid(row=1, column=1, columnspan=2, sticky='w', padx=10, pady=6)
        self.strategy_var = tk.StringVar(value="smart")
        tk.Radiobutton(strategy_frame, text="Smart Compress (recommended)", value="smart",
                        variable=self.strategy_var, command=self._on_strategy_changed
                        ).pack(anchor='w')
        tk.Label(strategy_frame, text="Keeps text sharp/selectable -- only shrinks embedded images.",
                 fg='gray40', font=('Arial', 8)).pack(anchor='w', padx=20)
        tk.Radiobutton(strategy_frame, text="Screenshot Mode", value="screenshot",
                        variable=self.strategy_var, command=self._on_strategy_changed
                        ).pack(anchor='w', pady=(4, 0))
        tk.Label(strategy_frame, text="Flattens every page to a compact image, like a screen capture --\n"
                                       "predictable per-page size, but text is no longer selectable.",
                 fg='gray40', font=('Arial', 8), justify=tk.LEFT).pack(anchor='w', padx=20)

        # -- Smart Compress controls --
        self.smart_frame = tk.Frame(self)
        self.smart_frame.grid(row=2, column=0, columnspan=3, sticky='w')
        tk.Label(self.smart_frame, text="Maximum output size:").grid(row=0, column=0, sticky='w', **pad)
        self.preset_var = tk.StringVar(value=_SIZE_PRESETS[1][0])  # default 10 MB
        preset_combo = ttk.Combobox(self.smart_frame, textvariable=self.preset_var,
                                     values=[p[0] for p in _SIZE_PRESETS],
                                     state='readonly', width=18)
        preset_combo.grid(row=0, column=1, sticky='w', **pad)
        preset_combo.bind('<<ComboboxSelected>>', self._on_preset_changed)

        self.custom_size_var = tk.DoubleVar(value=10.0)
        self.custom_size_entry = tk.Spinbox(self.smart_frame, from_=0.1, to=1000, increment=0.5,
                                             textvariable=self.custom_size_var, width=8,
                                             state=tk.DISABLED)
        self.custom_size_entry.grid(row=0, column=2, sticky='w', **pad)

        tk.Label(self.smart_frame, text="Compression mode:").grid(row=1, column=0, sticky='w', **pad)
        self.mode_var = tk.StringVar(value=_MODE_LABELS[1][0])  # default Balanced
        ttk.Combobox(self.smart_frame, textvariable=self.mode_var, values=[m[0] for m in _MODE_LABELS],
                     state='readonly', width=30).grid(row=1, column=1, columnspan=2, sticky='w', **pad)

        tk.Label(self.smart_frame,
                 text="The maximum size is an upper limit, not a target -- a PDF that's\n"
                      "already smaller, or safely compresses well below it, is never\n"
                      "padded back up to fill the limit.",
                 fg='gray30', font=('Arial', 8), justify=tk.LEFT
                 ).grid(row=2, column=0, columnspan=3, sticky='w', padx=10, pady=(0, 6))

        # -- Screenshot Mode controls --
        self.screenshot_frame = tk.Frame(self)
        self.screenshot_frame.grid(row=2, column=0, columnspan=3, sticky='w')
        tk.Label(self.screenshot_frame, text="Maximum size per page:").grid(
            row=0, column=0, sticky='w', **pad)
        self.max_page_kb_var = tk.DoubleVar(value=200.0)
        tk.Spinbox(self.screenshot_frame, from_=20, to=2000, increment=10,
                   textvariable=self.max_page_kb_var, width=8).grid(row=0, column=1, sticky='w', **pad)
        tk.Label(self.screenshot_frame, text="KB").grid(row=0, column=2, sticky='w')
        tk.Label(self.screenshot_frame,
                 text="Each page is rasterized at the best quality (150-200 DPI) that still\n"
                      "fits this cap -- good for A4 printing without ballooning file size.",
                 fg='gray30', font=('Arial', 8), justify=tk.LEFT
                 ).grid(row=1, column=0, columnspan=3, sticky='w', padx=10, pady=(0, 6))
        self.screenshot_frame.grid_remove()  # hidden until Screenshot Mode is selected

        self.status_label = tk.Label(self, text="", fg='gray20', anchor='w',
                                      justify=tk.LEFT, wraplength=460)
        self.status_label.grid(row=4, column=0, columnspan=3, sticky='w', padx=10, pady=(4, 2))

        self.progress = ttk.Progressbar(self, mode='indeterminate', length=460)
        self.progress.grid(row=5, column=0, columnspan=3, padx=10, pady=(0, 6))

        self.result_text = tk.Text(self, height=9, width=58, state=tk.DISABLED, bg='#f5f5f5')
        self.result_text.grid(row=6, column=0, columnspan=3, sticky='nsew', padx=10, pady=6)

        btns = tk.Frame(self)
        btns.grid(row=7, column=0, columnspan=3, pady=8)
        self.compress_button = tk.Button(btns, text="Compress...", command=self._start_compress,
                                          bg='#2e7d32', fg='white', width=16)
        self.compress_button.pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Close", command=self._on_close).pack(side=tk.LEFT, padx=4)

    def _on_strategy_changed(self):
        if self.strategy_var.get() == "screenshot":
            self.smart_frame.grid_remove()
            self.screenshot_frame.grid()
        else:
            self.screenshot_frame.grid_remove()
            self.smart_frame.grid()

    def _on_close(self):
        if self._cleanup_input_on_close and self._input_to_cleanup:
            try:
                os.remove(self._input_to_cleanup)
            except OSError:
                pass
        self.destroy()

    def _on_preset_changed(self, event=None):
        is_custom = self.preset_var.get() == "Custom"
        self.custom_size_entry.config(state=tk.NORMAL if is_custom else tk.DISABLED)

    def _browse_input(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.input_var.set(path)

    def _resolve_max_size_mb(self) -> float:
        label = self.preset_var.get()
        for name, value in _SIZE_PRESETS:
            if name == label and value is not None:
                return value
        return float(self.custom_size_var.get())

    def _resolve_mode(self) -> CompressionMode:
        label = self.mode_var.get()
        for name, mode in _MODE_LABELS:
            if name == label:
                return mode
        return CompressionMode.BALANCED

    def _start_compress(self):
        if self._compressing:
            return
        input_path = self.input_var.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Compress PDF", "Please choose a valid input PDF.")
            return

        base, _ = os.path.splitext(os.path.basename(input_path))
        suggested = f"{base}_compressed.pdf"
        output_path = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=suggested,
            filetypes=[("PDF files", "*.pdf")], title="Save Compressed PDF As")
        if not output_path:
            return

        screenshot_mode = self.strategy_var.get() == "screenshot"

        if screenshot_mode:
            try:
                max_page_kb = float(self.max_page_kb_var.get())
            except (tk.TclError, ValueError):
                messagebox.showerror("Compress PDF", "Enter a valid per-page size in KB.")
                return
        else:
            try:
                max_size_mb = self._resolve_max_size_mb()
            except (tk.TclError, ValueError):
                messagebox.showerror("Compress PDF", "Enter a valid custom size in MB.")
                return
            mode = self._resolve_mode()

        self._compressing = True
        self.compress_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"Compressing {os.path.basename(input_path)} ...", fg='#8a5a00')
        self.progress.start(12)
        self._set_result_text("")

        def worker():
            try:
                if screenshot_mode:
                    result = PDFCompressor().compress_screenshot(
                        input_path, output_path, max_page_size_kb=max_page_kb)
                else:
                    result = PDFCompressor().compress(input_path, output_path,
                                                        max_size_mb=max_size_mb, mode=mode)
                self.after(0, lambda: self._on_done(result, None))
            except Exception as e:
                # Capture now -- `e` is unbound by the time a deferred
                # lambda would run on the main thread via after().
                error_message = str(e)
                self.after(0, lambda: self._on_done(None, error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, result, error_message):
        self._compressing = False
        self.compress_button.config(state=tk.NORMAL)
        self.progress.stop()

        if error_message is not None:
            self.status_label.config(text="Compression failed.", fg='#a02020')
            self._set_result_text(error_message)
            messagebox.showerror("Compress PDF", error_message)
            return

        self.status_label.config(
            text="Done." if result.target_reached else "Done (target size could not be reached safely).",
            fg='#1b5e20' if result.target_reached else '#8a5a00',
        )
        summary = (
            f"Original size:    {result.original_size / (1024 * 1024):.2f} MB\n"
            f"Compressed size:  {result.output_size / (1024 * 1024):.2f} MB\n"
            f"Reduction:        {result.reduction_percent:.1f}%\n"
            f"Pages:            {result.page_count}\n"
            f"Mode:             {result.mode}\n"
            f"Status:           {result.message}\n"
            f"Output:           {result.output_path}"
        )
        self._set_result_text(summary)

        # An explicit "done, click OK" moment -- leaving the dialog sitting
        # open afterward (as before) read as ambiguous/still-in-progress.
        # Closing it here, but only on success: a failed run should stay
        # open so the user can adjust settings and retry. _on_close()
        # (not a bare destroy()) so the "Compress PDF" button flow's
        # throwaway temp input file still gets cleaned up.
        messagebox.showinfo("Compression Complete", summary)
        self._on_close()

    def _set_result_text(self, text: str):
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete('1.0', tk.END)
        self.result_text.insert('1.0', text)
        self.result_text.config(state=tk.DISABLED)
