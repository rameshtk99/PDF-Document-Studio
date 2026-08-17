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
    def __init__(self, parent, current_pdf_path: Optional[str] = None):
        super().__init__(parent)
        self.title("Compress PDF")
        self.geometry("500x460")
        self.resizable(False, False)
        self.transient(parent)

        self._compressing = False
        self._build_ui(current_pdf_path)

    def _build_ui(self, current_pdf_path):
        pad = dict(padx=10, pady=6)

        tk.Label(self, text="Input PDF:").grid(row=0, column=0, sticky='w', **pad)
        self.input_var = tk.StringVar(value=current_pdf_path or "")
        tk.Entry(self, textvariable=self.input_var, width=42).grid(row=0, column=1, **pad)
        tk.Button(self, text="Browse...", command=self._browse_input).grid(row=0, column=2, **pad)

        tk.Label(self, text="Maximum output size:").grid(row=1, column=0, sticky='w', **pad)
        self.preset_var = tk.StringVar(value=_SIZE_PRESETS[1][0])  # default 10 MB
        preset_combo = ttk.Combobox(self, textvariable=self.preset_var,
                                     values=[p[0] for p in _SIZE_PRESETS],
                                     state='readonly', width=18)
        preset_combo.grid(row=1, column=1, sticky='w', **pad)
        preset_combo.bind('<<ComboboxSelected>>', self._on_preset_changed)

        self.custom_size_var = tk.DoubleVar(value=10.0)
        self.custom_size_entry = tk.Spinbox(self, from_=0.1, to=1000, increment=0.5,
                                             textvariable=self.custom_size_var, width=8,
                                             state=tk.DISABLED)
        self.custom_size_entry.grid(row=1, column=2, sticky='w', **pad)

        tk.Label(self, text="Compression mode:").grid(row=2, column=0, sticky='w', **pad)
        self.mode_var = tk.StringVar(value=_MODE_LABELS[1][0])  # default Balanced
        ttk.Combobox(self, textvariable=self.mode_var, values=[m[0] for m in _MODE_LABELS],
                     state='readonly', width=30).grid(row=2, column=1, columnspan=2, sticky='w', **pad)

        tk.Label(self, text="The maximum size is an upper limit, not a target -- a PDF that's\n"
                             "already smaller, or safely compresses well below it, is never\n"
                             "padded back up to fill the limit.",
                 fg='gray30', font=('Arial', 8), justify=tk.LEFT
                 ).grid(row=3, column=0, columnspan=3, sticky='w', padx=10, pady=(0, 6))

        self.status_label = tk.Label(self, text="", fg='gray20', anchor='w',
                                      justify=tk.LEFT, wraplength=460)
        self.status_label.grid(row=4, column=0, columnspan=3, sticky='w', padx=10, pady=(4, 2))

        self.progress = ttk.Progressbar(self, mode='indeterminate', length=460)
        self.progress.grid(row=5, column=0, columnspan=3, padx=10, pady=(0, 6))

        self.result_text = tk.Text(self, height=9, width=58, state=tk.DISABLED, bg='#f5f5f5')
        self.result_text.grid(row=6, column=0, columnspan=3, padx=10, pady=6)

        btns = tk.Frame(self)
        btns.grid(row=7, column=0, columnspan=3, pady=8)
        self.compress_button = tk.Button(btns, text="Compress...", command=self._start_compress,
                                          bg='#2e7d32', fg='white', width=16)
        self.compress_button.pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Close", command=self.destroy).pack(side=tk.LEFT, padx=4)

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

    def _set_result_text(self, text: str):
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete('1.0', tk.END)
        self.result_text.insert('1.0', text)
        self.result_text.config(state=tk.DISABLED)
