"""
Compress PDF dialog -- lets the user pick an input PDF, a maximum output
size, and a compression mode, then runs PDFCompressor in the background
and reports the result. A standalone Toplevel so it works whether or not
a document is currently open in the main editor window.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from pdf import PDFCompressor, CompressionMode
from utils.ui_theme import (
    ACCENT, ACCENT_HOVER, BG_APP, BG_SUBTLE, BG_SURFACE, BORDER, DANGER,
    PAD, PAD_LG, RADIUS, RADIUS_SM, SECONDARY_BTN, SECONDARY_BTN_HOVER,
    SUCCESS, TEXT_PRIMARY, TEXT_SECONDARY, WARNING,
    apply_base_theme, font,
)
from utils.widgets import create_button
from app import modern_dialogs as dialogs

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


class SectionCaption(ctk.CTkLabel):
    def __init__(self, parent, text: str):
        super().__init__(parent, text=text, font=font(11, "bold"),
                          text_color=TEXT_SECONDARY, anchor="w")


class CompressDialog(ctk.CTkToplevel):
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
        apply_base_theme()
        self.title("Compress PDF")
        self.configure(fg_color=BG_APP)
        self.resizable(False, False)

        self._compressing = False
        self._progress_job = None
        self._cleanup_input_on_close = cleanup_input_on_close
        self._input_to_cleanup = current_pdf_path if cleanup_input_on_close else None

        self._build_ui(current_pdf_path)
        self._center_over_parent(parent, width=520)

        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- layout

    def _build_ui(self, current_pdf_path):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_LG)

        # ---- input file ---------------------------------------------------------
        SectionCaption(body, "INPUT PDF").pack(fill="x", pady=(0, 4))
        input_row = ctk.CTkFrame(body, fg_color="transparent")
        input_row.pack(fill="x", pady=(0, PAD_LG))
        self.input_entry = ctk.CTkEntry(
            input_row, height=34, corner_radius=RADIUS_SM, border_color=BORDER,
            fg_color=BG_SUBTLE, font=font(12))
        if current_pdf_path:
            self.input_entry.insert(0, current_pdf_path)
        self.input_entry.pack(side="left", fill="x", expand=True)
        create_button(input_row, text="Browse...", icon="open", command=self._browse_input,
                      variant="secondary", height=34).pack(side="left", padx=(8, 0))

        # ---- strategy ----------------------------------------------------------
        SectionCaption(body, "STRATEGY").pack(fill="x", pady=(0, 6))
        self.strategy = ctk.CTkSegmentedButton(
            body, values=["Smart Compress", "Screenshot Mode"],
            command=self._on_strategy_changed, fg_color=BG_SUBTLE,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_SUBTLE, font=font(12, "bold"), height=34,
        )
        self.strategy.set("Smart Compress")
        self.strategy.pack(fill="x", pady=(0, 6))
        self.strategy_hint = ctk.CTkLabel(
            body, text="Keeps text sharp/selectable -- only shrinks embedded images.",
            font=font(11), text_color=TEXT_SECONDARY, anchor="w", justify="left")
        self.strategy_hint.pack(fill="x", pady=(0, PAD_LG))

        # ---- smart compress controls --------------------------------------------
        self.smart_frame = ctk.CTkFrame(body, fg_color=BG_SUBTLE, corner_radius=RADIUS)
        self.smart_frame.pack(fill="x", pady=(0, PAD_LG))
        self.smart_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(self.smart_frame, text="Max output size", font=font(12),
                     text_color=TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=(PAD, 6), pady=(PAD, 4))
        self.preset_menu = ctk.CTkOptionMenu(
            self.smart_frame, values=[p[0] for p in _SIZE_PRESETS], command=self._on_preset_changed,
            fg_color=BG_SURFACE, button_color=SECONDARY_BTN, button_hover_color=SECONDARY_BTN_HOVER,
            text_color=TEXT_PRIMARY, dropdown_fg_color=BG_SURFACE, font=font(12), width=170)
        self.preset_menu.set(_SIZE_PRESETS[1][0])  # default 10 MB
        self.preset_menu.grid(row=0, column=1, sticky="w", padx=(0, PAD), pady=(PAD, 4))

        self.custom_size_entry = ctk.CTkEntry(
            self.smart_frame, height=30, width=70, corner_radius=RADIUS_SM,
            border_color=BORDER, fg_color=BG_SURFACE, font=font(12), state="disabled")
        self.custom_size_entry.insert(0, "10.0")
        self.custom_size_entry.grid(row=1, column=1, sticky="w", padx=(0, PAD), pady=(0, 4))

        ctk.CTkLabel(self.smart_frame, text="Compression mode", font=font(12),
                     text_color=TEXT_PRIMARY).grid(row=2, column=0, sticky="w", padx=(PAD, 6), pady=(4, PAD))
        self.mode_menu = ctk.CTkOptionMenu(
            self.smart_frame, values=[m[0] for m in _MODE_LABELS], fg_color=BG_SURFACE,
            button_color=SECONDARY_BTN, button_hover_color=SECONDARY_BTN_HOVER,
            text_color=TEXT_PRIMARY, dropdown_fg_color=BG_SURFACE, font=font(12), width=240)
        self.mode_menu.set(_MODE_LABELS[1][0])  # default Balanced
        self.mode_menu.grid(row=2, column=1, sticky="w", padx=(0, PAD), pady=(4, 4))

        ctk.CTkLabel(
            self.smart_frame,
            text="The maximum size is an upper limit, not a target -- a PDF that's\n"
                 "already smaller, or safely compresses well below it, is never\n"
                 "padded back up to fill the limit.",
            font=font(10), text_color=TEXT_SECONDARY, justify="left", anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=PAD, pady=(0, PAD))

        # ---- screenshot mode controls --------------------------------------------
        self.screenshot_frame = ctk.CTkFrame(body, fg_color=BG_SUBTLE, corner_radius=RADIUS)
        self.screenshot_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(self.screenshot_frame, text="Max size per page", font=font(12),
                     text_color=TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=(PAD, 6), pady=PAD)
        size_row = ctk.CTkFrame(self.screenshot_frame, fg_color="transparent")
        size_row.grid(row=0, column=1, sticky="w", pady=PAD)
        self.max_page_kb_entry = ctk.CTkEntry(
            size_row, height=30, width=70, corner_radius=RADIUS_SM,
            border_color=BORDER, fg_color=BG_SURFACE, font=font(12))
        self.max_page_kb_entry.insert(0, "200")
        self.max_page_kb_entry.pack(side="left")
        ctk.CTkLabel(size_row, text="KB", font=font(12), text_color=TEXT_SECONDARY).pack(
            side="left", padx=(6, 0))
        ctk.CTkLabel(
            self.screenshot_frame,
            text="Each page is rasterized at the best quality (150-200 DPI) that still\n"
                 "fits this cap -- good for A4 printing without ballooning file size.",
            font=font(10), text_color=TEXT_SECONDARY, justify="left", anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=PAD, pady=(0, PAD))

        # ---- status / progress ---------------------------------------------------
        self.status_label = ctk.CTkLabel(body, text="", font=font(12), text_color=TEXT_SECONDARY,
                                          anchor="w")
        self.status_label.pack(fill="x", pady=(0, 4))
        self.progress = ctk.CTkProgressBar(body, height=8, corner_radius=4, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(0, PAD_LG))

        # ---- result summary --------------------------------------------------------
        self.result_frame = ctk.CTkFrame(body, fg_color=BG_SUBTLE, corner_radius=RADIUS)
        self.result_labels: dict = {}
        for i, key in enumerate(("Original size", "Compressed size", "Reduction",
                                  "Pages", "Mode", "Status", "Output")):
            ctk.CTkLabel(self.result_frame, text=key, font=font(11, "bold"),
                         text_color=TEXT_SECONDARY, width=110, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(PAD, 4), pady=3)
            value_label = ctk.CTkLabel(self.result_frame, text="--", font=font(11),
                                        text_color=TEXT_PRIMARY, anchor="w", wraplength=280,
                                        justify="left")
            value_label.grid(row=i, column=1, sticky="w", padx=(0, PAD), pady=3)
            self.result_labels[key] = value_label
        # result_frame stays unpacked (hidden) until a compression run
        # actually produces a result -- see _on_done.

        # ---- buttons -----------------------------------------------------------
        self.btn_row = ctk.CTkFrame(body, fg_color="transparent")
        self.btn_row.pack(fill="x", pady=(PAD_LG, 0))
        create_button(self.btn_row, text="Close", command=self._on_close,
                      variant="secondary", width=100, height=36).pack(side="right")
        self.compress_button = create_button(
            self.btn_row, text="Compress...", icon="compress", command=self._start_compress,
            variant="primary", width=140, height=36)
        self.compress_button.pack(side="right", padx=(0, 8))

    def _center_over_parent(self, parent, width: int):
        self.update_idletasks()
        height = self.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except tk.TclError:
            px = py = 0
            pw, ph = self.winfo_screenwidth(), self.winfo_screenheight()
        x = px + max(0, (pw - width) // 2)
        y = py + max(0, (ph - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ---------------------------------------------------------------- strategy toggle

    def _on_strategy_changed(self, value: str):
        if value == "Screenshot Mode":
            self.smart_frame.pack_forget()
            self.strategy_hint.configure(
                text="Flattens every page to a compact image, like a screen capture --\n"
                     "predictable per-page size, but text is no longer selectable.")
            self.screenshot_frame.pack(fill="x", pady=(0, PAD_LG), before=self.status_label)
        else:
            self.screenshot_frame.pack_forget()
            self.strategy_hint.configure(
                text="Keeps text sharp/selectable -- only shrinks embedded images.")
            self.smart_frame.pack(fill="x", pady=(0, PAD_LG), before=self.status_label)

    def _on_preset_changed(self, value: str):
        self.custom_size_entry.configure(state="normal" if value == "Custom" else "disabled")

    def _browse_input(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")], parent=self)
        if path:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, path)

    def _resolve_max_size_mb(self) -> float:
        label = self.preset_menu.get()
        for name, value in _SIZE_PRESETS:
            if name == label and value is not None:
                return value
        return float(self.custom_size_entry.get())

    def _resolve_mode(self) -> CompressionMode:
        label = self.mode_menu.get()
        for name, mode in _MODE_LABELS:
            if name == label:
                return mode
        return CompressionMode.BALANCED

    # ---------------------------------------------------------------- compress flow

    def _start_compress(self):
        if self._compressing:
            return
        input_path = self.input_entry.get().strip()
        if not input_path or not os.path.exists(input_path):
            dialogs.show_error(self, "Compress PDF", "Please choose a valid input PDF.")
            return

        base, _ = os.path.splitext(os.path.basename(input_path))
        suggested = f"{base}_compressed.pdf"
        output_path = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=suggested,
            filetypes=[("PDF files", "*.pdf")], title="Save Compressed PDF As", parent=self)
        if not output_path:
            return

        screenshot_mode = self.strategy.get() == "Screenshot Mode"

        if screenshot_mode:
            try:
                max_page_kb = float(self.max_page_kb_entry.get())
            except ValueError:
                dialogs.show_error(self, "Compress PDF", "Enter a valid per-page size in KB.")
                return
        else:
            try:
                max_size_mb = self._resolve_max_size_mb()
            except ValueError:
                dialogs.show_error(self, "Compress PDF", "Enter a valid custom size in MB.")
                return
            mode = self._resolve_mode()

        self._compressing = True
        self.compress_button.configure(state="disabled")
        self.status_label.configure(text=f"Compressing {os.path.basename(input_path)} ...",
                                     text_color=WARNING)
        self._start_progress_animation()

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

    def _start_progress_animation(self):
        """Fakes an indeterminate progress bar (CTkProgressBar has no
        native indeterminate mode) by sweeping 0->1 repeatedly."""
        state = {"value": 0.0}

        def step():
            if not self._compressing:
                return
            state["value"] = (state["value"] + 0.04) % 1.0
            self.progress.set(state["value"])
            self._progress_job = self.after(16, step)

        step()

    def _stop_progress_animation(self):
        if self._progress_job:
            try:
                self.after_cancel(self._progress_job)
            except tk.TclError:
                pass
            self._progress_job = None

    def _on_done(self, result, error_message):
        self._compressing = False
        self._stop_progress_animation()
        self.compress_button.configure(state="normal")

        if error_message is not None:
            self.progress.set(0)
            self.status_label.configure(text="Compression failed.", text_color=DANGER)
            dialogs.show_error(self, "Compress PDF", error_message)
            return

        self.progress.set(1.0)
        self.status_label.configure(
            text="Done." if result.target_reached else "Done (target size could not be reached safely).",
            text_color=SUCCESS if result.target_reached else WARNING,
        )
        summary = {
            "Original size": f"{result.original_size / (1024 * 1024):.2f} MB",
            "Compressed size": f"{result.output_size / (1024 * 1024):.2f} MB",
            "Reduction": f"{result.reduction_percent:.1f}%",
            "Pages": str(result.page_count),
            "Mode": str(result.mode),
            "Status": result.message,
            "Output": result.output_path,
        }
        for key, value in summary.items():
            self.result_labels[key].configure(text=value)
        self.result_frame.pack(fill="x", pady=(0, PAD_LG), before=self.btn_row)
        self.update_idletasks()
        self._center_over_parent(self.master, width=520)

        # An explicit "done, click OK" moment -- leaving the dialog sitting
        # open afterward (as before) read as ambiguous/still-in-progress.
        # Closing it here, but only on success: a failed run stays open
        # (returned above) so the user can adjust settings and retry.
        # _on_close() (not a bare destroy()) so the "Compress PDF" button
        # flow's throwaway temp input file still gets cleaned up.
        display_summary = "\n".join(f"{k}: {v}" for k, v in summary.items())
        dialogs.show_info(self, "Compression Complete", display_summary)
        self._on_close()

    def _on_close(self):
        self._compressing = False
        self._stop_progress_animation()
        if self._cleanup_input_on_close and self._input_to_cleanup:
            try:
                os.remove(self._input_to_cleanup)
            except OSError:
                pass
        self.destroy()
