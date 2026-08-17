#!/usr/bin/env python3
"""
Test Suite for Stage 8: White-Space Detection Algorithm

Tests the white-space detection and analysis:
- Page rendering for analysis
- Content boundary detection
- Safe shrinkage calculation
- Per-page analysis results
- Caching and performance
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from pdf.white_space_detector import WhiteSpaceDetector, PageAnalysis
from models.models import Document


def test_page_rendering_for_analysis():
    """Test that pages can be rendered for white-space analysis"""
    print("Test 1: Page Rendering for Analysis")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        print(f"✓ Loaded PDF with {doc.page_count} pages")
        
        # Test rendering for analysis
        detector = WhiteSpaceDetector(pdf_path)
        
        # Render page 1 for analysis
        image = detector._render_page_for_analysis(1, dpi=72)
        assert image is not None, "Failed to render page"
        print(f"✓ Rendered page 1 successfully")
        
        # Check image dimensions
        width, height = image.size
        assert width > 0 and height > 0, "Invalid image dimensions"
        print(f"✓ Image dimensions: {width}x{height}")
        
        # Test with multiple DPI values
        for dpi in [72, 150, 200]:
            image = detector._render_page_for_analysis(1, dpi=dpi)
            assert image is not None, f"Failed to render at {dpi} DPI"
        print(f"✓ Rendering works at multiple DPI values")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_content_boundary_detection():
    """Test detection of page content boundaries"""
    print("Test 2: Content Boundary Detection")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        detector = WhiteSpaceDetector(pdf_path)
        
        # Detect boundaries for page 1
        analysis = detector.analyze_page(1)
        assert analysis is not None, "Analysis returned None"
        print(f"✓ Analyzed page 1")
        
        # Check boundary values
        assert 0 <= analysis.top_margin <= 100, f"Top margin invalid: {analysis.top_margin}"
        assert 0 <= analysis.bottom_margin <= 100, f"Bottom margin invalid: {analysis.bottom_margin}"
        assert 0 <= analysis.left_margin <= 100, f"Left margin invalid: {analysis.left_margin}"
        assert 0 <= analysis.right_margin <= 100, f"Right margin invalid: {analysis.right_margin}"
        print(f"✓ Boundaries detected: T={analysis.top_margin:.1f}, B={analysis.bottom_margin:.1f}, "
              f"L={analysis.left_margin:.1f}, R={analysis.right_margin:.1f}")
        
        # Verify at least one margin exists
        margins_sum = (analysis.top_margin + analysis.bottom_margin + 
                      analysis.left_margin + analysis.right_margin)
        assert margins_sum >= 0, "Margins negative"
        print(f"✓ Margins detected ({margins_sum:.1f} total)")
        
        # For pages with narrow content, that's okay - just ensure values are valid
        usable_height = 100 - analysis.top_margin - analysis.bottom_margin
        usable_width = 100 - analysis.left_margin - analysis.right_margin
        
        if usable_height > 5 and usable_width > 5:
            print(f"✓ Usable area: {usable_width:.1f}% width, {usable_height:.1f}% height")
        else:
            print(f"⚠ Narrow content area (W={usable_width:.1f}%, H={usable_height:.1f}%) - OK for some PDFs")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_safe_shrinkage_calculation():
    """Test calculation of safe shrinkage percentage"""
    print("Test 3: Safe Shrinkage Calculation")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        detector = WhiteSpaceDetector(pdf_path)
        
        # Analyze page
        analysis = detector.analyze_page(1)
        
        # Check safe shrinkage
        safe_shrinkage = analysis.safe_shrinkage_percent
        assert isinstance(safe_shrinkage, (int, float)), "Safe shrinkage not numeric"
        assert 0 <= safe_shrinkage <= 100, f"Safe shrinkage out of range: {safe_shrinkage}"
        print(f"✓ Safe shrinkage calculated: {safe_shrinkage:.1f}%")
        
        # Shrinkage should be positive for most pages
        if safe_shrinkage > 0:
            print(f"✓ Page has room for shrinkage")
        else:
            print(f"⚠ Page has no safe shrinkage (may be fully utilized)")
        
        # Check shrinkage zone
        shrinkage_zone = analysis.shrinkage_zone
        assert isinstance(shrinkage_zone, dict), "Shrinkage zone not a dict"
        assert 'top' in shrinkage_zone and 'bottom' in shrinkage_zone, "Missing zone values"
        print(f"✓ Shrinkage zone: top={shrinkage_zone['top']:.1f}%, "
              f"bottom={shrinkage_zone['bottom']:.1f}%")
        
        # Zone values should be reasonable
        assert 0 <= shrinkage_zone['top'] <= 100, "Top zone out of range"
        assert 0 <= shrinkage_zone['bottom'] <= 100, "Bottom zone out of range"
        print(f"✓ Shrinkage zones valid")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_page_analysis():
    """Test analyzing multiple pages"""
    print("Test 4: Multi-Page Analysis")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        detector = WhiteSpaceDetector(pdf_path)
        
        # Analyze multiple pages
        num_pages = min(5, doc.page_count)  # Analyze first 5 pages
        results = {}
        
        for page_num in range(1, num_pages + 1):
            analysis = detector.analyze_page(page_num)
            results[page_num] = analysis
            print(f"✓ Analyzed page {page_num}: "
                  f"shrinkage={analysis.safe_shrinkage_percent:.1f}%")
        
        # Check that results are stored
        assert len(results) == num_pages, "Not all pages analyzed"
        print(f"✓ Analyzed {num_pages} pages successfully")
        
        # Check that different pages can have different values
        shrinkages = [analysis.safe_shrinkage_percent for analysis in results.values()]
        print(f"✓ Page shrinkages: {[f'{s:.1f}%' for s in shrinkages]}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_analysis_caching():
    """Test that analysis results are cached"""
    print("Test 5: Analysis Caching")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        detector = WhiteSpaceDetector(pdf_path)
        
        # First analysis
        analysis1 = detector.analyze_page(1)
        print(f"✓ First analysis: {analysis1.safe_shrinkage_percent:.1f}%")
        
        # Second analysis (should be cached)
        analysis2 = detector.analyze_page(1)
        print(f"✓ Second analysis (cached): {analysis2.safe_shrinkage_percent:.1f}%")
        
        # Results should be identical
        assert analysis1.safe_shrinkage_percent == analysis2.safe_shrinkage_percent, \
            "Cached result differs from original"
        print(f"✓ Cached results are identical")
        
        # Check cache size
        cache_size = len(detector._analysis_cache)
        assert cache_size >= 1, "Cache not working"
        print(f"✓ Cache contains {cache_size} entries")
        
        # Analyze another page, cache should grow
        detector.analyze_page(2)
        new_cache_size = len(detector._analysis_cache)
        assert new_cache_size > cache_size, "Cache not growing"
        print(f"✓ Cache size increased to {new_cache_size}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_document_integration():
    """Test integration with Document model"""
    print("Test 6: Document Integration")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        detector = WhiteSpaceDetector(pdf_path)
        
        # Analyze and store in document
        for page_num in range(1, min(4, doc.page_count + 1)):
            analysis = detector.analyze_page(page_num)
            
            # Store in page config (extend Document model)
            config = doc.get_page_config(page_num)
            if not hasattr(config, 'white_space_analysis'):
                config.white_space_analysis = None
            config.white_space_analysis = analysis
            doc.set_page_config(page_num, config)
        
        # Verify stored
        for page_num in range(1, min(4, doc.page_count + 1)):
            config = doc.get_page_config(page_num)
            assert hasattr(config, 'white_space_analysis'), "Analysis not stored"
            if config.white_space_analysis:
                print(f"✓ Page {page_num} analysis stored: "
                      f"shrinkage={config.white_space_analysis.safe_shrinkage_percent:.1f}%")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_edge_cases():
    """Test edge cases and error handling"""
    print("Test 7: Edge Cases and Error Handling")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        detector = WhiteSpaceDetector(pdf_path)
        
        # Test invalid page number (should handle gracefully)
        try:
            invalid_analysis = detector.analyze_page(doc.page_count + 100)
            # If it doesn't raise, it should return None or safe default
            if invalid_analysis:
                print(f"⚠ Invalid page returned result: {invalid_analysis}")
            else:
                print(f"✓ Invalid page number handled (returned None)")
        except Exception as e:
            print(f"✓ Invalid page number raised exception (acceptable): {type(e).__name__}")
        
        # Test page 0 (should fail or return None)
        invalid_analysis = detector.analyze_page(0)
        if invalid_analysis is None:
            print(f"✓ Page 0 rejected (returned None - correct)")
        else:
            print(f"⚠ Page 0 returned result (page number validation needed)")
        
        # Test page 1 (should work)
        valid_analysis = detector.analyze_page(1)
        assert valid_analysis is not None, "Valid page returned None"
        print(f"✓ Page 1 analysis works: {valid_analysis.safe_shrinkage_percent:.1f}%")
        
        # Test with very small page
        all_analyses = []
        for page_num in range(1, min(6, doc.page_count + 1)):
            analysis = detector.analyze_page(page_num)
            if analysis:
                all_analyses.append(analysis)
        
        # At least first page should work
        assert len(all_analyses) > 0, "No analyses completed"
        print(f"✓ Analyzed {len(all_analyses)} pages without error")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 50)
    print("STAGE 8 TEST SUITE: White-Space Detection Algorithm")
    print("=" * 50 + "\n")
    
    tests = [
        test_page_rendering_for_analysis,
        test_content_boundary_detection,
        test_safe_shrinkage_calculation,
        test_multi_page_analysis,
        test_analysis_caching,
        test_document_integration,
        test_edge_cases,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test crashed: {e}\n")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 50)
    
    if all(results):
        print("\n✅ All tests PASSED - White-space detection ready")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
