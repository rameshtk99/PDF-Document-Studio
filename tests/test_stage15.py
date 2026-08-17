#!/usr/bin/env python3
"""
Stage 15: Footer Placement Algorithm Tests

Validates the two-path footer positioning logic:
  - No-shrink path: footer floats just below actual content (content-relative)
  - Shrink path: minimum-necessary vertical compression, footer at page bottom

All tests are pure-Python: no PDF I/O, no rendering, no Tkinter.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdf.document_exporter import (
    compute_content_relative_bottom_margin,
    SAFETY_GAP_PT,
    FOOTER_PHYSICAL_MARGIN_PT,
)


# ── helpers ───────────────────────────────────────────────────────────────────

class FakeAnalysis:
    """Minimal PageAnalysis stand-in with just bottom_margin (percentage)."""
    def __init__(self, bottom_pct: float):
        self.bottom_margin = bottom_pct   # whitespace % from page bottom


def footer_block_height(font_size: float, line_gap: float) -> float:
    return 2 * font_size + line_gap + SAFETY_GAP_PT


def required_height(content_gap: float, font_size: float, line_gap: float) -> float:
    return content_gap + footer_block_height(font_size, line_gap) + FOOTER_PHYSICAL_MARGIN_PT


def simulate_shrink(page_h: float, available_pts: float, req_h: float):
    """Return (scale_y, translate_y) for the minimum-necessary transform."""
    denom = page_h - available_pts
    assert denom > 0, "content must not fill the page"
    scale_y = (page_h - req_h) / denom
    translate_y = page_h * (1.0 - scale_y)
    return scale_y, translate_y


def apply_transform(y: float, scale_y: float, translate_y: float) -> float:
    return scale_y * y + translate_y


def check(condition: bool, msg: str):
    if not condition:
        raise AssertionError(msg)


# ── tests ─────────────────────────────────────────────────────────────────────

def test_01_large_whitespace_no_shrink():
    """Large whitespace: compute_content_relative_bottom_margin returns a
    positive renderer_bottom_margin and no compression is indicated."""
    page_h = 842.0
    content_gap = 20.0
    font_size = 13.0
    line_gap = 4.0
    whitespace_pct = 30.0   # 252.6 pt of whitespace at bottom

    analysis = FakeAnalysis(whitespace_pct)
    available_pts = page_h * whitespace_pct / 100.0   # 252.6
    req_h = required_height(content_gap, font_size, line_gap)

    check(available_pts >= req_h, "Should be no-shrink case")

    margin = compute_content_relative_bottom_margin(
        page_h, analysis, content_gap, font_size, line_gap)

    check(margin >= 0, f"margin must be non-negative, got {margin}")
    check(margin < available_pts, "margin must be less than available whitespace")

    # Gap between content and footer visual top must equal content_gap
    footer_top = margin + footer_block_height(font_size, line_gap)
    gap = available_pts - footer_top
    check(abs(gap - content_gap) < 0.5, f"gap {gap:.2f} != content_gap {content_gap}")
    print("  PASS test_01_large_whitespace_no_shrink")


def test_02_exact_fit_no_shrink():
    """Exactly enough whitespace: renderer_margin equals FOOTER_PHYSICAL_MARGIN_PT."""
    page_h = 842.0
    content_gap = 20.0
    font_size = 13.0
    line_gap = 4.0
    req_h = required_height(content_gap, font_size, line_gap)
    whitespace_pct = req_h / page_h * 100.0   # exactly required

    analysis = FakeAnalysis(whitespace_pct)
    margin = compute_content_relative_bottom_margin(
        page_h, analysis, content_gap, font_size, line_gap)

    # candidate = 0, so margin = FOOTER_PHYSICAL_MARGIN_PT + 0
    check(abs(margin - FOOTER_PHYSICAL_MARGIN_PT) < 0.5,
          f"exact-fit margin should be ~{FOOTER_PHYSICAL_MARGIN_PT}, got {margin:.3f}")
    print("  PASS test_02_exact_fit_no_shrink")


def test_03_small_deficit_shrink():
    """Small whitespace deficit: shrink case returns renderer_margin=0,
    and the transform lifts content bottom to required_height."""
    page_h = 842.0
    content_gap = 20.0
    font_size = 13.0
    line_gap = 4.0
    whitespace_pct = 5.0   # 42.1 pt whitespace, not enough
    available_pts = page_h * whitespace_pct / 100.0
    req_h = required_height(content_gap, font_size, line_gap)

    analysis = FakeAnalysis(whitespace_pct)
    check(available_pts < req_h, "Should be shrink case")

    margin = compute_content_relative_bottom_margin(
        page_h, analysis, content_gap, font_size, line_gap)
    check(margin == FOOTER_PHYSICAL_MARGIN_PT,
          f"shrink case must return FOOTER_PHYSICAL_MARGIN_PT={FOOTER_PHYSICAL_MARGIN_PT}, got {margin}")

    scale_y, translate_y = simulate_shrink(page_h, available_pts, req_h)
    check(0 < scale_y < 1, f"scale_y must be in (0,1): {scale_y}")

    new_content_bottom = apply_transform(available_pts, scale_y, translate_y)
    check(abs(new_content_bottom - req_h) < 0.5,
          f"content bottom {new_content_bottom:.2f} != required {req_h:.2f}")

    page_top = apply_transform(page_h, scale_y, translate_y)
    check(abs(page_top - page_h) < 0.5, "page top must stay anchored")
    print("  PASS test_03_small_deficit_shrink")


def test_04_large_deficit_shrink():
    """Large deficit (content nearly fills the page): more compression applied."""
    page_h = 842.0
    content_gap = 74.0   # ~1 inch gap
    font_size = 13.0
    line_gap = 4.0
    whitespace_pct = 1.0   # 8.4 pt whitespace – heavy deficit
    available_pts = page_h * whitespace_pct / 100.0
    req_h = required_height(content_gap, font_size, line_gap)

    analysis = FakeAnalysis(whitespace_pct)
    check(available_pts < req_h, "Should be shrink case")

    margin = compute_content_relative_bottom_margin(
        page_h, analysis, content_gap, font_size, line_gap)
    check(margin == FOOTER_PHYSICAL_MARGIN_PT,
          f"shrink case must return FOOTER_PHYSICAL_MARGIN_PT, got {margin}")

    scale_y, translate_y = simulate_shrink(page_h, available_pts, req_h)
    check(scale_y < 1, f"scale_y should be < 1 for compression: {scale_y}")

    new_bottom = apply_transform(available_pts, scale_y, translate_y)
    check(abs(new_bottom - req_h) < 0.5,
          f"content bottom {new_bottom:.2f} != required {req_h:.2f}")
    print("  PASS test_04_large_deficit_shrink")


def test_05_different_pages_different_ratios():
    """Two pages with the same footer config but different content density
    must receive different (per-page) scale factors."""
    page_h = 842.0
    content_gap = 20.0
    font_size = 13.0
    line_gap = 4.0
    req_h = required_height(content_gap, font_size, line_gap)

    available_a = page_h * 0.01   # very dense page (~8 pt whitespace)
    available_b = page_h * 0.03   # slightly less dense (~25 pt whitespace)

    check(available_a < req_h and available_b < req_h, "Both need shrink")

    scale_a, _ = simulate_shrink(page_h, available_a, req_h)
    scale_b, _ = simulate_shrink(page_h, available_b, req_h)

    check(abs(scale_a - scale_b) > 0.001,
          f"Different pages must get different scale: {scale_a:.4f} vs {scale_b:.4f}")
    check(scale_a < scale_b, "Denser page should be compressed more")
    print("  PASS test_05_different_pages_different_ratios")


def test_06_larger_font_larger_required_height():
    """Larger font size increases required_height, shifting the threshold."""
    page_h = 842.0
    content_gap = 20.0
    line_gap = 4.0
    small_fs = 10.0
    large_fs = 18.0

    req_small = required_height(content_gap, small_fs, line_gap)
    req_large = required_height(content_gap, large_fs, line_gap)

    check(req_large > req_small,
          f"Larger font must increase required_height: {req_large} vs {req_small}")

    # A page that just passes with small font should fail with large font
    whitespace_pct = (req_small + 1.0) / page_h * 100.0
    available_pts = page_h * whitespace_pct / 100.0
    analysis = FakeAnalysis(whitespace_pct)

    margin_small = compute_content_relative_bottom_margin(
        page_h, analysis, content_gap, small_fs, line_gap)
    check(margin_small >= 0, "Small font no-shrink case must give non-negative margin")

    if available_pts < req_large:
        margin_large = compute_content_relative_bottom_margin(
            page_h, analysis, content_gap, large_fs, line_gap)
        check(margin_large == FOOTER_PHYSICAL_MARGIN_PT,
              f"Large font shrink case must return FOOTER_PHYSICAL_MARGIN_PT, got {margin_large}")
    print("  PASS test_06_larger_font_larger_required_height")


def test_07_analysis_none_fallback():
    """When whitespace analysis is unavailable, function falls back to
    returning configured_gap_pt (no crash, reasonable default)."""
    margin = compute_content_relative_bottom_margin(
        842.0, None, 74.0, 13.0, 4.0)
    check(margin == 74.0,
          f"None analysis must return configured_gap_pt=74, got {margin}")
    print("  PASS test_07_analysis_none_fallback")


def test_08_minimum_compression_vs_old_formula():
    """The new minimum-compression formula compresses LESS than the old
    all-page formula (ratio = (page_h - req_h) / page_h)."""
    page_h = 842.0
    content_gap = 20.0
    font_size = 13.0
    line_gap = 4.0
    whitespace_pct = 5.0
    available_pts = page_h * whitespace_pct / 100.0
    req_h = required_height(content_gap, font_size, line_gap)

    # New formula (minimum-necessary)
    new_scale, _ = simulate_shrink(page_h, available_pts, req_h)

    # Old formula (anchored at y=0 — more aggressive)
    old_ratio = (page_h - req_h) / page_h

    check(new_scale > old_ratio,
          f"Minimum compression (scale={new_scale:.4f}) must be "
          f"less aggressive than old formula (ratio={old_ratio:.4f})")
    print("  PASS test_08_minimum_compression_vs_old_formula")


def test_09_shrink_returns_physical_margin():
    """In the shrink case, compute_content_relative_bottom_margin returns
    FOOTER_PHYSICAL_MARGIN_PT (printer-safe minimum, not 0)."""
    page_h = 842.0
    whitespace_pct = 2.0
    analysis = FakeAnalysis(whitespace_pct)
    margin = compute_content_relative_bottom_margin(
        page_h, analysis, 50.0, 13.0, 4.0)
    check(margin == FOOTER_PHYSICAL_MARGIN_PT,
          f"Shrink case must return {FOOTER_PHYSICAL_MARGIN_PT}, got {margin}")
    check(margin > 0, "margin must be > 0 (printer safety)")
    print("  PASS test_09_shrink_returns_physical_margin")


def test_10_no_shrink_gap_equals_content_gap():
    """In the no-shrink case, the actual gap between content bottom and
    footer visual top equals content_gap exactly, and margin >= FOOTER_PHYSICAL_MARGIN_PT."""
    page_h = 842.0
    content_gap = 36.0
    font_size = 11.0
    line_gap = 3.0
    whitespace_pct = 25.0
    available_pts = page_h * whitespace_pct / 100.0
    analysis = FakeAnalysis(whitespace_pct)

    margin = compute_content_relative_bottom_margin(
        page_h, analysis, content_gap, font_size, line_gap)

    check(margin >= FOOTER_PHYSICAL_MARGIN_PT,
          f"margin {margin:.1f} must be >= FOOTER_PHYSICAL_MARGIN_PT {FOOTER_PHYSICAL_MARGIN_PT}")

    # footer visual top = margin + footer_block_height (baseline of line1 + approx ascent)
    footer_top = margin + footer_block_height(font_size, line_gap)
    gap = available_pts - footer_top

    check(abs(gap - content_gap) < 0.5,
          f"Gap {gap:.3f} must equal content_gap {content_gap}")
    print("  PASS test_10_no_shrink_gap_equals_content_gap")


def test_11_transform_page_top_stays_anchored():
    """The minimum-compression transform never moves the page top."""
    page_h = 842.0
    cases = [
        (5.0, 20.0, 13.0, 4.0),
        (1.0, 74.0, 13.0, 4.0),
        (8.0, 36.0, 16.0, 6.0),
    ]
    for whitespace_pct, content_gap, font_size, line_gap in cases:
        available_pts = page_h * whitespace_pct / 100.0
        req_h = required_height(content_gap, font_size, line_gap)
        if available_pts >= req_h:
            continue
        scale_y, translate_y = simulate_shrink(page_h, available_pts, req_h)
        top_after = apply_transform(page_h, scale_y, translate_y)
        check(abs(top_after - page_h) < 0.01,
              f"Page top moved: {top_after:.3f} != {page_h} "
              f"(wsp={whitespace_pct}%, gap={content_gap})")
    print("  PASS test_11_transform_page_top_stays_anchored")


def test_12_transform_content_bottom_lands_at_required():
    """After the minimum-compression transform, the content bottom lands
    exactly at required_height (within floating-point tolerance)."""
    page_h = 842.0
    cases = [
        (5.0, 20.0, 13.0, 4.0),
        (1.0, 74.0, 13.0, 4.0),
        (8.0, 36.0, 16.0, 6.0),
        (3.0, 50.0, 10.0, 3.0),
    ]
    for whitespace_pct, content_gap, font_size, line_gap in cases:
        available_pts = page_h * whitespace_pct / 100.0
        req_h = required_height(content_gap, font_size, line_gap)
        if available_pts >= req_h:
            continue
        scale_y, translate_y = simulate_shrink(page_h, available_pts, req_h)
        new_bottom = apply_transform(available_pts, scale_y, translate_y)
        check(abs(new_bottom - req_h) < 0.01,
              f"Content bottom {new_bottom:.3f} != required {req_h:.3f} "
              f"(wsp={whitespace_pct}%, gap={content_gap})")
    print("  PASS test_12_transform_content_bottom_lands_at_required")


# ── runner ────────────────────────────────────────────────────────────────────

TESTS = [
    test_01_large_whitespace_no_shrink,
    test_02_exact_fit_no_shrink,
    test_03_small_deficit_shrink,
    test_04_large_deficit_shrink,
    test_05_different_pages_different_ratios,
    test_06_larger_font_larger_required_height,
    test_07_analysis_none_fallback,
    test_08_minimum_compression_vs_old_formula,
    test_09_shrink_returns_physical_margin,
    test_10_no_shrink_gap_equals_content_gap,
    test_11_transform_page_top_stays_anchored,
    test_12_transform_content_bottom_lands_at_required,
]


def main():
    print("\n" + "=" * 60)
    print("Stage 15: Footer Placement Algorithm Tests")
    print("=" * 60)
    failures = []
    for test_fn in TESTS:
        try:
            test_fn()
        except AssertionError as exc:
            print(f"  FAIL {test_fn.__name__}: {exc}")
            failures.append(test_fn.__name__)
        except Exception as exc:
            print(f"  ERROR {test_fn.__name__}: {exc}")
            failures.append(test_fn.__name__)

    print("\n" + "-" * 60)
    if failures:
        print(f"FAILED: {len(failures)} / {len(TESTS)}")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"All {len(TESTS)} tests passed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
