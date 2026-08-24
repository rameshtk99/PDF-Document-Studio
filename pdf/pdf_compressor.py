"""
PDF Size Reduction / Compression module.

Reduces PDF file size as aggressively as reasonably safe while preserving
readability, tables, signatures, stamps, and A4 print quality. A
"maximum output size" is a hard ceiling to respect, never a target to hit
exactly -- small/already-lean PDFs are never inflated, and quality is
never sacrificed just to satisfy a number (see the design spec this
module implements, `PDF Compress Doc` at the project root).

Pipeline: analyze -> classify pages -> lossless structural optimization
-> (for genuinely image-heavy pages only) adaptive per-image
downsample/recompress candidate loop -> measure actual output size at
each step -> validate -> return the best safe result.

Digital/text/vector pages are never touched -- only pages whose images
cover a large fraction of the page (the scanned-document case) are
candidates for image recompression, and only their embedded raster
images are modified in place (via PyMuPDF's Page.replace_image, which
preserves the page's bbox/rotation/placement exactly, so page
dimensions/A4 layout are untouched by construction).
"""

import io
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from PIL import Image

_fitz = None


def _ensure_fitz():
    global _fitz
    if _fitz is None:
        import fitz
        _fitz = fitz
    return _fitz


class CompressionMode(str, Enum):
    LOSSLESS = 'lossless'
    BEST_QUALITY = 'best_quality'
    BALANCED = 'balanced'
    MAXIMUM = 'maximum'
    SCREENSHOT = 'screenshot'  # see PDFCompressor.compress_screenshot()


class PDFCompressionError(Exception):
    """Raised for conditions the compressor cannot safely handle
    (password-protected input, unreadable output, validation failure)."""
    pass


@dataclass
class CompressionResult:
    output_path: str
    original_size: int
    output_size: int
    page_count: int
    mode: str
    max_size_mb: float
    target_reached: bool
    message: str

    @property
    def reduction_percent(self) -> float:
        if self.original_size <= 0:
            return 0.0
        return ((self.original_size - self.output_size) / self.original_size) * 100.0


# (dpi, jpeg_quality) rungs to try in order, gentlest first. The last rung
# is the safety floor -- compression never goes below it.
_LADDER = [
    (180, 75),
    (180, 72),
    (160, 70),
    (150, 68),
    (150, 60),
]

# Rungs for compress_screenshot() (whole-PAGE rasterization, not just
# embedded images -- see that method). 150-200 DPI is the standard
# "reads sharp on A4 at arm's length / prints cleanly" range; the floor
# (100 DPI / 50 quality) is deliberately still legible for text rather than
# chasing the size cap past the point of being useful.
_SCREENSHOT_LADDER = [
    (200, 85),
    (180, 80),
    (160, 75),
    (150, 70),
    (150, 60),
    (120, 55),
    (100, 50),
]

_IMAGE_HEAVY_THRESHOLD = 0.15   # fraction of page area covered by images
_MIN_IMAGE_PIXELS = 40 * 40     # ignore tiny icons/bullets/rules

# A pixel counts as "colored" once its channels diverge by more than this.
_COLOR_PIXEL_CHANNEL_DIFF = 12
# If more than this fraction of sampled pixels are colored, the image is
# NOT grayscale-safe. Deliberately a small fraction, not a whole-image
# average: a compact colored stamp/seal/signature covers only a tiny
# fraction of a full scanned page, and averaging color difference across
# the whole image dilutes it away (verified against a synthetic page with
# a small red stamp -- an averaging approach wrongly greenlit converting
# it to grayscale; a colored-pixel-fraction approach correctly detects it).
_GRAYSCALE_COLOR_FRACTION_THRESHOLD = 0.0003


class PDFCompressor:
    """Document-aware PDF size reducer. See module docstring for the
    overall pipeline."""

    def compress(self, input_path: str, output_path: str,
                 max_size_mb: float = 10.0,
                 mode: CompressionMode = CompressionMode.BALANCED) -> CompressionResult:
        fitz = _ensure_fitz()
        mode = CompressionMode(mode)

        if not os.path.exists(input_path):
            raise PDFCompressionError(f"Input file not found: {input_path}")

        original_size = os.path.getsize(input_path)
        max_size_bytes = max_size_mb * 1024 * 1024

        tmp_dir = tempfile.mkdtemp(prefix="pdfcompress_")
        try:
            doc = fitz.open(input_path)
            try:
                if doc.needs_pass:
                    raise PDFCompressionError(
                        "Password-protected PDFs are not supported for compression.")

                page_count = doc.page_count

                # Stage 1: lossless structural optimization.
                baseline_path = os.path.join(tmp_dir, "stage1_structural.pdf")
                self._save_structural(doc, baseline_path)
                baseline_size = os.path.getsize(baseline_path)

                if baseline_size >= original_size:
                    # Structural resave didn't help (can happen on already
                    # lean PDFs) -- fall back to the original bytes.
                    baseline_path = os.path.join(tmp_dir, "stage1_original_copy.pdf")
                    shutil.copyfile(input_path, baseline_path)
                    baseline_size = original_size

                if mode == CompressionMode.LOSSLESS or baseline_size <= max_size_bytes:
                    return self._conclude(doc, baseline_path, output_path, original_size,
                                           baseline_size, page_count, mode, max_size_mb)

                # Stage 2: classify pages, find genuinely image-heavy ones.
                analysis_doc = fitz.open(baseline_path)
                try:
                    queued = self._classify_images(analysis_doc)
                    analyzed = self._analyze_images(analysis_doc, queued) if queued else {}
                finally:
                    analysis_doc.close()

                if not analyzed:
                    # No safe image-recompression opportunity (e.g. a
                    # digital/text PDF) -- report the best safe result.
                    return self._conclude(doc, baseline_path, output_path, original_size,
                                           baseline_size, page_count, mode, max_size_mb)

                # Stage 3: adaptive candidate loop.
                best_path, best_size = baseline_path, baseline_size
                for idx, (dpi, quality) in enumerate(_LADDER):
                    cand_doc = fitz.open(baseline_path)
                    try:
                        self._apply_candidate(cand_doc, analyzed, dpi, quality)
                        cand_path = os.path.join(tmp_dir, f"stage2_candidate_{idx}.pdf")
                        self._save_structural(cand_doc, cand_path)
                    finally:
                        cand_doc.close()

                    cand_size = os.path.getsize(cand_path)
                    if cand_size < best_size:
                        best_path, best_size = cand_path, cand_size

                    fits = cand_size <= max_size_bytes
                    if fits and mode != CompressionMode.MAXIMUM:
                        break
                    if mode == CompressionMode.BEST_QUALITY and idx >= 1:
                        # Only try the two gentlest rungs when prioritizing quality.
                        break

                return self._conclude(doc, best_path, output_path, original_size,
                                       best_size, page_count, mode, max_size_mb)
            finally:
                doc.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def compress_screenshot(self, input_path: str, output_path: str,
                             max_page_size_kb: float = 200.0) -> CompressionResult:
        """"Screenshot" style compression: every page is rasterized whole
        (like a screen capture of the rendered page, the same way a
        snipping tool would grab it) and re-inserted at its original
        physical size, instead of selectively recompressing embedded
        images. This flattens text/vector content to a picture -- text
        stops being selectable/searchable -- in exchange for a
        predictable, aggressive per-page size cap regardless of what's on
        the page. Use compress() (the default, document-aware pipeline)
        when text/vector content should stay untouched.

        Each page is rasterized at the gentlest (dpi, jpeg_quality) rung
        (see _SCREENSHOT_LADDER) that fits under max_page_size_kb, so
        quality is only sacrificed as far as the cap actually requires --
        never blanket-degraded to the harshest rung.
        """
        fitz = _ensure_fitz()
        if not os.path.exists(input_path):
            raise PDFCompressionError(f"Input file not found: {input_path}")

        original_size = os.path.getsize(input_path)
        max_page_bytes = max_page_size_kb * 1024

        doc = fitz.open(input_path)
        try:
            if doc.needs_pass:
                raise PDFCompressionError(
                    "Password-protected PDFs are not supported for compression.")

            page_count = doc.page_count
            out_doc = fitz.open()
            try:
                pages_under_cap = 0
                for page_index in range(page_count):
                    page = doc[page_index]
                    jpeg_bytes, fits = self._rasterize_page_under_cap(page, max_page_bytes)
                    if fits:
                        pages_under_cap += 1
                    new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
                    new_page.insert_image(new_page.rect, stream=jpeg_bytes)

                tmp_dir = tempfile.mkdtemp(prefix="pdfscreenshot_")
                try:
                    tmp_path = os.path.join(tmp_dir, "screenshot_output.pdf")
                    out_doc.save(tmp_path, garbage=4, deflate=True, clean=True, use_objstms=1)
                    self._validate(tmp_path, doc)
                    shutil.copyfile(tmp_path, output_path)
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            finally:
                out_doc.close()
        finally:
            doc.close()

        output_size = os.path.getsize(output_path)
        all_fit = pages_under_cap == page_count
        message = (
            f"Flattened {page_count} page(s) to images (~{max_page_size_kb:g} KB/page target); "
            f"{pages_under_cap}/{page_count} page(s) at or under the cap."
        )
        return CompressionResult(
            output_path=output_path,
            original_size=original_size,
            output_size=output_size,
            page_count=page_count,
            mode=CompressionMode.SCREENSHOT.value,
            max_size_mb=(max_page_size_kb * page_count) / 1024.0,
            target_reached=all_fit,
            message=message,
        )

    @staticmethod
    def _rasterize_page_under_cap(page, max_page_bytes: float):
        """Render `page` to a JPEG, trying _SCREENSHOT_LADDER rungs in
        order until one fits under max_page_bytes. Returns (jpeg_bytes,
        fits) -- if even the safety-floor rung doesn't fit, its bytes are
        still returned (fits=False) rather than degrading further."""
        fitz = _ensure_fitz()
        result_bytes = b""
        for dpi, quality in _SCREENSHOT_LADDER:
            scale = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            pil.save(buf, format='JPEG', quality=quality, optimize=True)
            result_bytes = buf.getvalue()
            if len(result_bytes) <= max_page_bytes:
                return result_bytes, True
        return result_bytes, False

    # -- pipeline stages -----------------------------------------------------

    @staticmethod
    def _save_structural(doc, path: str):
        """Lossless structural optimization: strip unused objects, compress
        cross-reference/object streams and content streams. Measured to
        matter a lot on some PDFs and do nothing on already-lean ones --
        callers must compare against the pre-save size, never assume this
        always shrinks the file."""
        doc.save(path, garbage=4, deflate=True, clean=True,
                  use_objstms=1, deflate_fonts=True)

    def _classify_images(self, doc) -> Dict[int, List[int]]:
        """Return {page_index: [xref, ...]} for pages whose images cover
        enough of the page to count as "image-heavy" (the scanned-document
        case). Pages with only a small logo/icon, or no images, are
        omitted entirely and never touched."""
        queued: Dict[int, List[int]] = {}
        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_area = abs(page.rect.width * page.rect.height)
            if page_area <= 0:
                continue
            images = page.get_images(full=True)
            if not images:
                continue

            covered_area = 0.0
            xrefs_on_page: List[int] = []
            seen = set()
            for img in images:
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    rects = page.get_image_rects(xref)
                except Exception:
                    rects = []
                for r in rects:
                    covered_area += abs(r.width * r.height)
                width_px, height_px = img[2], img[3]
                if width_px * height_px >= _MIN_IMAGE_PIXELS:
                    xrefs_on_page.append(xref)

            if xrefs_on_page and (covered_area / page_area) >= _IMAGE_HEAVY_THRESHOLD:
                queued[page_index] = xrefs_on_page
        return queued

    def _analyze_images(self, doc, queued: Dict[int, List[int]]) -> Dict[int, Dict[int, dict]]:
        """One-time, per-image analysis (grayscale-safety + effective
        current DPI + placed size), reused across every candidate in the
        ladder rather than recomputed each time."""
        analyzed: Dict[int, Dict[int, dict]] = {}
        for page_index, xrefs in queued.items():
            page = doc[page_index]
            page_info = {}
            for xref in xrefs:
                try:
                    raw = doc.extract_image(xref)
                    pil = Image.open(io.BytesIO(raw['image']))
                    if pil.mode not in ('RGB', 'L'):
                        pil = pil.convert('RGB')

                    rects = page.get_image_rects(xref)
                    rect_w_pt = rect_h_pt = None
                    if rects:
                        r = rects[0]
                        rect_w_pt, rect_h_pt = abs(r.width), abs(r.height)

                    effective_dpi = None
                    if rect_w_pt:
                        effective_dpi = pil.width / (rect_w_pt / 72.0)

                    page_info[xref] = {
                        'is_grayscale': self._is_grayscale_safe(pil),
                        'effective_dpi': effective_dpi,
                        'rect_w_pt': rect_w_pt,
                        'rect_h_pt': rect_h_pt,
                    }
                except Exception:
                    continue
            if page_info:
                analyzed[page_index] = page_info
        return analyzed

    @staticmethod
    def _is_grayscale_safe(pil: Image.Image) -> bool:
        """Grayscale-safety check: count the fraction of pixels (over a
        500x500 thumbnail, so this stays fast regardless of source
        resolution -- kept large enough that a compact stamp/seal still
        shows up) that are clearly colored, rather than averaging color
        difference across the whole image. Averaging dilutes a small but
        meaningful colored region (a stamp covering a few percent of a
        page) into a near-zero whole-image average, wrongly greenlighting
        grayscale conversion -- exactly what the spec warns against for
        colored stamps/seals/signatures/highlights."""
        if pil.mode == 'L':
            return True
        try:
            rgb = pil.convert('RGB') if pil.mode != 'RGB' else pil
        except Exception:
            return False

        small = rgb.copy()
        small.thumbnail((500, 500))
        pixels = small.getdata()
        total = len(pixels)
        if total == 0:
            return False

        colored = sum(1 for (r, g, b) in pixels
                       if (abs(r - g) + abs(g - b) + abs(r - b)) > _COLOR_PIXEL_CHANNEL_DIFF)
        return (colored / total) < _GRAYSCALE_COLOR_FRACTION_THRESHOLD

    def _apply_candidate(self, cand_doc, analyzed: Dict[int, Dict[int, dict]],
                          dpi: int, quality: int):
        for page_index, xref_info in analyzed.items():
            page = cand_doc[page_index]
            for xref, info in xref_info.items():
                effective_dpi = info.get('effective_dpi')
                if effective_dpi is not None and effective_dpi <= dpi:
                    # Already at or below this rung's target resolution --
                    # don't re-degrade an already-efficient image.
                    continue
                new_bytes = self._recompress_image(cand_doc, xref, info, dpi, quality)
                if new_bytes is not None:
                    try:
                        page.replace_image(xref, stream=new_bytes)
                    except Exception:
                        pass

    @staticmethod
    def _recompress_image(doc, xref: int, info: dict, dpi: int, quality: int) -> Optional[bytes]:
        try:
            raw = doc.extract_image(xref)
            pil = Image.open(io.BytesIO(raw['image']))
            if pil.mode not in ('RGB', 'L'):
                pil = pil.convert('RGB')

            rect_w_pt, rect_h_pt = info.get('rect_w_pt'), info.get('rect_h_pt')
            if rect_w_pt and rect_h_pt:
                target_w = max(1, int(rect_w_pt / 72.0 * dpi))
                target_h = max(1, int(rect_h_pt / 72.0 * dpi))
                if target_w < pil.width or target_h < pil.height:
                    pil = pil.resize((target_w, target_h), Image.Resampling.LANCZOS)

            if info.get('is_grayscale') and pil.mode != 'L':
                pil = pil.convert('L')

            buf = io.BytesIO()
            pil.save(buf, format='JPEG', quality=quality, optimize=True)
            return buf.getvalue()
        except Exception:
            return None

    def _validate(self, candidate_path: str, original_doc):
        fitz = _ensure_fitz()
        try:
            check_doc = fitz.open(candidate_path)
        except Exception as e:
            raise PDFCompressionError(f"Compressed output failed to open: {e}")
        try:
            if check_doc.page_count != original_doc.page_count:
                raise PDFCompressionError(
                    f"Validation failed: page count changed "
                    f"({original_doc.page_count} -> {check_doc.page_count})")
            for i in range(original_doc.page_count):
                orig_rect = original_doc[i].rect
                new_rect = check_doc[i].rect
                if (abs(orig_rect.width - new_rect.width) > 0.5 or
                        abs(orig_rect.height - new_rect.height) > 0.5):
                    raise PDFCompressionError(
                        f"Validation failed: page {i + 1} dimensions changed")
        finally:
            check_doc.close()

    def _conclude(self, original_doc, chosen_path: str, output_path: str,
                   original_size: int, chosen_size: int, page_count: int,
                   mode: CompressionMode, max_size_mb: float) -> CompressionResult:
        self._validate(chosen_path, original_doc)
        shutil.copyfile(chosen_path, output_path)
        output_size = os.path.getsize(output_path)
        target_reached = output_size <= max_size_mb * 1024 * 1024
        message = self._build_message(original_size, output_size, max_size_mb, target_reached)
        return CompressionResult(
            output_path=output_path,
            original_size=original_size,
            output_size=output_size,
            page_count=page_count,
            mode=mode.value,
            max_size_mb=max_size_mb,
            target_reached=target_reached,
            message=message,
        )

    @staticmethod
    def _build_message(original_size: int, output_size: int, max_size_mb: float,
                        target_reached: bool) -> str:
        orig_mb = original_size / (1024 * 1024)
        out_mb = output_size / (1024 * 1024)
        reduction = 0.0 if original_size <= 0 else (
            (original_size - output_size) / original_size) * 100.0
        if target_reached:
            return (f"Reduced from {orig_mb:.2f} MB to {out_mb:.2f} MB "
                     f"({reduction:.1f}% smaller). Within the {max_size_mb:g} MB limit.")
        return (f"Could not safely reduce below {max_size_mb:g} MB without risking "
                 f"readability. Best safe result: {orig_mb:.2f} MB -> {out_mb:.2f} MB "
                 f"({reduction:.1f}% smaller).")
