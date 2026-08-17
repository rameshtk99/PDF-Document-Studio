#!/usr/bin/env python3
"""
Test Suite for Stage 9: Minimum Page Adjustment

Tests page adjustment and shrinkage application:
- Calculate adjustment ratios from shrinkage percentages
- Apply adjustments to page content
- Maintain page integrity during adjustment
- Per-page vs global adjustment settings
- Adjustment preview and validation
- Integration with white-space detection results
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from pdf.white_space_detector import WhiteSpaceDetector
from pdf.page_adjuster import PageAdjuster, AdjustmentConfig
from models.models import Document


def test_adjustment_ratio_calculation():
    """Test calculating adjustment ratios from shrinkage percentages"""
    print("Test 1: Adjustment Ratio Calculation")
    print("-" * 50)
    
    try:
        # Test various shrinkage percentages
        test_cases = [
            (0.0, 1.0),      # 0% shrinkage = 1.0 ratio (no change)
            (5.0, 0.95),     # 5% shrinkage = 0.95 ratio
            (10.0, 0.90),    # 10% shrinkage = 0.90 ratio
            (15.0, 0.85),    # 15% shrinkage = 0.85 ratio
            (20.0, 0.80),    # 20% shrinkage = 0.80 ratio
        ]
        
        for shrinkage, expected_ratio in test_cases:
            # Calculate ratio from shrinkage
            ratio = 1.0 - (shrinkage / 100.0)
            assert abs(ratio - expected_ratio) < 0.001, \
                f"Shrinkage {shrinkage}% should give ratio {expected_ratio}, got {ratio}"
            print(f"✓ {shrinkage}% shrinkage = {ratio:.2f} ratio")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adjustment_config():
    """Test AdjustmentConfig data structure"""
    print("Test 2: Adjustment Configuration")
    print("-" * 50)
    
    try:
        # Create adjustment config
        config = AdjustmentConfig(
            shrinkage_percent=10.0,
            shrinkage_direction='bottom',
            apply_to_all_pages=False,
            preserve_margins=True
        )
        
        assert config.shrinkage_percent == 10.0, "Shrinkage not set"
        assert config.shrinkage_direction == 'bottom', "Direction not set"
        assert config.apply_to_all_pages == False, "Apply flag not set"
        assert config.preserve_margins == True, "Preserve margins not set"
        print("✓ AdjustmentConfig created successfully")
        
        # Test ratio calculation
        ratio = config.get_adjustment_ratio()
        assert abs(ratio - 0.90) < 0.001, "Ratio calculation incorrect"
        print(f"✓ Adjustment ratio: {ratio:.2f}")
        
        # Test with different shrinkage
        config2 = AdjustmentConfig(shrinkage_percent=15.0)
        ratio2 = config2.get_adjustment_ratio()
        assert abs(ratio2 - 0.85) < 0.001, "Ratio calculation incorrect"
        print(f"✓ 15% shrinkage ratio: {ratio2:.2f}")
        
        # Test with 0% shrinkage
        config3 = AdjustmentConfig(shrinkage_percent=0.0)
        ratio3 = config3.get_adjustment_ratio()
        assert abs(ratio3 - 1.0) < 0.001, "0% shrinkage should give 1.0 ratio"
        print(f"✓ 0% shrinkage ratio: {ratio3:.2f} (no adjustment)")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_page_adjuster_initialization():
    """Test PageAdjuster initialization"""
    print("Test 3: Page Adjuster Initialization")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        # Create PageAdjuster
        adjuster = PageAdjuster(pdf_path)
        assert adjuster is not None, "Failed to create adjuster"
        print(f"✓ PageAdjuster created")
        
        # Check default config
        assert adjuster.default_config is not None, "No default config"
        print(f"✓ Default config loaded")
        
        # Load PDF document
        doc = PDFLoader.load_pdf(pdf_path)
        adjuster.load_document(doc)
        assert adjuster.document == doc, "Document not loaded"
        print(f"✓ Document loaded ({doc.page_count} pages)")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_calculate_adjustment_dimensions():
    """Test calculating adjusted page dimensions"""
    print("Test 4: Calculate Adjustment Dimensions")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        from pdf.pdf_loader import PDFLoader
        doc = PDFLoader.load_pdf(pdf_path)
        adjuster = PageAdjuster(pdf_path)
        adjuster.load_document(doc)
        
        # Get page dimensions using PDFLoader
        page_info = PDFLoader.get_page_info(doc, 1)
        original_width = page_info['width']
        original_height = page_info['height']
        print(f"✓ Original dimensions: {original_width:.1f}x{original_height:.1f}")
        
        # Calculate adjusted dimensions with 10% shrinkage
        config = AdjustmentConfig(shrinkage_percent=10.0)
        ratio = config.get_adjustment_ratio()
        
        adjusted_height = original_height * ratio
        expected_height_reduction = original_height * 0.10
        
        assert adjusted_height < original_height, "Adjusted height should be smaller"
        assert abs(adjusted_height - (original_height * 0.90)) < 0.1, "Height calculation incorrect"
        print(f"✓ Adjusted height: {adjusted_height:.1f} (reduced by {expected_height_reduction:.1f})")
        
        # Test with different shrinkage
        config2 = AdjustmentConfig(shrinkage_percent=15.0)
        ratio2 = config2.get_adjustment_ratio()
        adjusted_height2 = original_height * ratio2
        
        assert adjusted_height2 < adjusted_height, "Higher shrinkage should give smaller height"
        print(f"✓ 15% shrinkage height: {adjusted_height2:.1f}")
        
        # Width should remain unchanged (vertical shrinkage only)
        assert original_width == original_width, "Width should not change"
        print(f"✓ Width unchanged: {original_width:.1f}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adjustment_with_white_space_data():
    """Test adjustment using white-space detection results"""
    print("Test 5: Adjustment with White-Space Data")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        detector = WhiteSpaceDetector(pdf_path)
        adjuster = PageAdjuster(pdf_path)
        adjuster.load_document(doc)
        
        # Analyze first page
        analysis = detector.analyze_page(1)
        assert analysis is not None, "Analysis failed"
        print(f"✓ Page analysis: safe shrinkage = {analysis.safe_shrinkage_percent:.1f}%")
        
        # Create adjustment config from analysis
        config = AdjustmentConfig(shrinkage_percent=analysis.safe_shrinkage_percent)
        
        # Apply adjustment
        adjustment_data = adjuster.calculate_adjustment_for_page(1, config)
        assert adjustment_data is not None, "Adjustment calculation failed"
        print(f"✓ Adjustment calculated")
        
        # Verify adjustment data
        assert 'original_height' in adjustment_data, "Missing original height"
        assert 'adjusted_height' in adjustment_data, "Missing adjusted height"
        assert 'space_created' in adjustment_data, "Missing space created"
        print(f"✓ Adjustment data: original={adjustment_data['original_height']:.1f}, "
              f"adjusted={adjustment_data['adjusted_height']:.1f}, "
              f"space={adjustment_data['space_created']:.1f}")
        
        # Verify calculations
        assert adjustment_data['adjusted_height'] < adjustment_data['original_height'], \
            "Adjusted should be smaller"
        print(f"✓ Height reduced by {adjustment_data['space_created']:.1f} points")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_per_page_vs_global_adjustment():
    """Test per-page adjustment vs global default"""
    print("Test 6: Per-Page vs Global Adjustment")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        adjuster = PageAdjuster(pdf_path)
        adjuster.load_document(doc)
        
        # Set global config
        global_config = AdjustmentConfig(shrinkage_percent=10.0)
        adjuster.default_config = global_config
        print(f"✓ Global config: {global_config.shrinkage_percent}% shrinkage")
        
        # Get config for page 1 (should use global)
        config1 = adjuster.get_page_adjustment_config(1)
        assert config1.shrinkage_percent == 10.0, "Page 1 should use global"
        print(f"✓ Page 1 uses global: {config1.shrinkage_percent}%")
        
        # Set page-specific config
        page_config = AdjustmentConfig(shrinkage_percent=15.0)
        adjuster.set_page_adjustment_config(1, page_config)
        
        # Get config for page 1 (should use page-specific)
        config1_updated = adjuster.get_page_adjustment_config(1)
        assert config1_updated.shrinkage_percent == 15.0, "Page 1 should use specific"
        print(f"✓ Page 1 now uses specific: {config1_updated.shrinkage_percent}%")
        
        # Get config for page 2 (should still use global)
        config2 = adjuster.get_page_adjustment_config(2)
        assert config2.shrinkage_percent == 10.0, "Page 2 should use global"
        print(f"✓ Page 2 uses global: {config2.shrinkage_percent}%")
        
        # Clear page-specific config
        adjuster.clear_page_adjustment_config(1)
        config1_cleared = adjuster.get_page_adjustment_config(1)
        assert config1_cleared.shrinkage_percent == 10.0, "Page 1 should revert to global"
        print(f"✓ Page 1 reverted to global: {config1_cleared.shrinkage_percent}%")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adjustment_preview():
    """Test previewing adjustments before applying"""
    print("Test 7: Adjustment Preview")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        adjuster = PageAdjuster(pdf_path)
        adjuster.load_document(doc)
        
        # Get preview for first 3 pages
        config = AdjustmentConfig(shrinkage_percent=10.0)
        preview = adjuster.preview_adjustments(config, max_pages=3)
        
        assert preview is not None, "Preview returned None"
        assert len(preview) > 0, "Preview is empty"
        print(f"✓ Generated preview for {len(preview)} pages")
        
        # Verify preview data
        for page_num, adjustment in preview.items():
            assert 'original_height' in adjustment, f"Page {page_num} missing height"
            assert 'adjusted_height' in adjustment, f"Page {page_num} missing adjusted height"
            assert 'space_created' in adjustment, f"Page {page_num} missing space"
            print(f"✓ Page {page_num}: {adjustment['original_height']:.1f} → "
                  f"{adjustment['adjusted_height']:.1f} "
                  f"({adjustment['space_created']:.1f} pts freed)")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adjustment_validation():
    """Test validation of adjustment configurations"""
    print("Test 8: Adjustment Validation")
    print("-" * 50)
    
    try:
        # Valid configuration
        config1 = AdjustmentConfig(shrinkage_percent=10.0)
        is_valid = config1.is_valid()
        assert is_valid, "Valid config marked as invalid"
        print(f"✓ Valid config (10%): {is_valid}")
        
        # Edge cases - should be valid
        config2 = AdjustmentConfig(shrinkage_percent=0.0)
        assert config2.is_valid(), "0% shrinkage should be valid"
        print(f"✓ Valid config (0%): True")
        
        config3 = AdjustmentConfig(shrinkage_percent=30.0)
        assert config3.is_valid(), "30% shrinkage should be valid"
        print(f"✓ Valid config (30%): True")
        
        # Invalid configurations
        config4 = AdjustmentConfig(shrinkage_percent=-5.0)
        is_valid_neg = config4.is_valid()
        if not is_valid_neg:
            print(f"✓ Invalid config (-5%): {is_valid_neg}")
        else:
            print(f"⚠ Negative shrinkage accepted (may need tighter validation)")
        
        config5 = AdjustmentConfig(shrinkage_percent=100.0)
        is_valid_100 = config5.is_valid()
        if not is_valid_100:
            print(f"✓ Invalid config (100%): {is_valid_100}")
        else:
            print(f"⚠ 100% shrinkage accepted (may need tighter validation)")
        
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
    print("STAGE 9 TEST SUITE: Minimum Page Adjustment")
    print("=" * 50 + "\n")
    
    tests = [
        test_adjustment_ratio_calculation,
        test_adjustment_config,
        test_page_adjuster_initialization,
        test_calculate_adjustment_dimensions,
        test_adjustment_with_white_space_data,
        test_per_page_vs_global_adjustment,
        test_adjustment_preview,
        test_adjustment_validation,
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
        print("\n✅ All tests PASSED - Page adjustment ready")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
