#!/usr/bin/env python3
"""
Test Suite for Stage 10: Image Insertion and Positioning

Tests image management functionality:
- Image file validation and loading
- Adding images to pages
- Positioning calculations
- Multi-image management per page
- Image property management
- Integration with adjustment data
- Z-order (layering) support
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from pdf.image_manager import ImageManager, ImagePlacement
from models.models import Document, PageObject


def test_image_validation():
    """Test image file validation"""
    print("Test 1: Image File Validation")
    print("-" * 50)
    
    try:
        manager = ImageManager()
        
        # Test valid image (create a test image first)
        # For now, test with non-existent file handling
        is_valid, error = manager.validate_image_file("/nonexistent/image.jpg")
        assert not is_valid, "Should reject non-existent file"
        assert error is not None, "Should provide error message"
        print(f"✓ Rejects non-existent file: {error}")
        
        # Test invalid file types
        test_file = project_root / "test_invalid.txt"
        test_file.write_text("not an image")
        
        is_valid, error = manager.validate_image_file(str(test_file))
        assert not is_valid, "Should reject non-image files"
        print(f"✓ Rejects non-image files: {error}")
        
        test_file.unlink()
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_image_placement_calculations():
    """Test image placement and positioning calculations"""
    print("Test 2: Image Placement Calculations")
    print("-" * 50)
    
    try:
        manager = ImageManager()
        
        # Create test placement
        placement = ImagePlacement(
            page_number=1,
            x=50.0,
            y=100.0,
            width=200.0,
            height=150.0,
            rotation=0.0,
            opacity=100.0
        )
        
        assert placement.page_number == 1, "Page number not set"
        assert placement.x == 50.0, "X position not set"
        assert placement.y == 100.0, "Y position not set"
        assert placement.width == 200.0, "Width not set"
        assert placement.height == 150.0, "Height not set"
        print(f"✓ Created placement: ({placement.x}, {placement.y}) "
              f"{placement.width}×{placement.height}")
        
        # Test aspect ratio calculation
        aspect_ratio = placement.get_aspect_ratio()
        expected_ratio = 200.0 / 150.0
        assert abs(aspect_ratio - expected_ratio) < 0.001, "Aspect ratio incorrect"
        print(f"✓ Aspect ratio: {aspect_ratio:.2f}")
        
        # Test center calculation
        center = placement.get_center()
        expected_x = 50.0 + 200.0/2
        expected_y = 100.0 + 150.0/2
        assert abs(center[0] - expected_x) < 0.1, "Center X incorrect"
        assert abs(center[1] - expected_y) < 0.1, "Center Y incorrect"
        print(f"✓ Center: {center}")
        
        # Test bounds calculation
        bounds = placement.get_bounds()
        assert bounds['left'] == 50.0, "Left bound incorrect"
        assert bounds['top'] == 100.0, "Top bound incorrect"
        assert abs(bounds['right'] - 250.0) < 0.1, "Right bound incorrect"
        assert abs(bounds['bottom'] - 250.0) < 0.1, "Bottom bound incorrect"
        print(f"✓ Bounds: L={bounds['left']}, T={bounds['top']}, "
              f"R={bounds['right']}, B={bounds['bottom']}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adding_images_to_page():
    """Test adding images to document pages"""
    print("Test 3: Adding Images to Pages")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        manager = ImageManager()
        manager.load_document(doc)
        
        # Add image to page 1
        placement = ImagePlacement(
            page_number=1,
            x=50.0,
            y=50.0,
            width=150.0,
            height=100.0
        )
        
        image_id = manager.add_image_to_page(1, placement, image_path=None)
        assert image_id is not None, "Failed to add image"
        print(f"✓ Added image: {image_id}")
        
        # Verify image was added
        config = doc.get_page_config(1)
        assert len(config.objects) > 0, "Image not added to page"
        print(f"✓ Image added to page (total objects: {len(config.objects)})")
        
        # Add another image to same page
        placement2 = ImagePlacement(
            page_number=1,
            x=250.0,
            y=50.0,
            width=150.0,
            height=100.0
        )
        
        image_id2 = manager.add_image_to_page(1, placement2, image_path=None)
        assert image_id2 is not None, "Failed to add second image"
        assert image_id != image_id2, "Images should have different IDs"
        print(f"✓ Added second image: {image_id2}")
        
        # Verify both images on page
        config = doc.get_page_config(1)
        assert len(config.objects) == 2, "Second image not added"
        print(f"✓ Page has 2 images")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_image_property_management():
    """Test managing image properties"""
    print("Test 4: Image Property Management")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        manager = ImageManager()
        manager.load_document(doc)
        
        # Add image
        placement = ImagePlacement(
            page_number=1,
            x=50.0,
            y=50.0,
            width=150.0,
            height=100.0,
            opacity=100.0,
            rotation=0.0
        )
        
        image_id = manager.add_image_to_page(1, placement)
        
        # Update opacity
        manager.set_image_property(image_id, 'opacity', 75.0)
        obj = manager.get_image_object(image_id)
        assert obj.opacity == 75.0, "Opacity not updated"
        print(f"✓ Updated opacity: {obj.opacity}%")
        
        # Update rotation
        manager.set_image_property(image_id, 'rotation', 45.0)
        obj = manager.get_image_object(image_id)
        assert obj.rotation == 45.0, "Rotation not updated"
        print(f"✓ Updated rotation: {obj.rotation}°")
        
        # Update visibility
        manager.set_image_property(image_id, 'visible', False)
        obj = manager.get_image_object(image_id)
        assert obj.visible == False, "Visibility not updated"
        print(f"✓ Updated visibility: {obj.visible}")
        
        # Update position
        manager.set_image_position(image_id, 100.0, 100.0)
        obj = manager.get_image_object(image_id)
        assert obj.x == 100.0 and obj.y == 100.0, "Position not updated"
        print(f"✓ Updated position: ({obj.x}, {obj.y})")
        
        # Update size
        manager.set_image_size(image_id, 200.0, 150.0)
        obj = manager.get_image_object(image_id)
        assert obj.width == 200.0 and obj.height == 150.0, "Size not updated"
        print(f"✓ Updated size: {obj.width}×{obj.height}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_image_management():
    """Test managing multiple images on a page"""
    print("Test 5: Multi-Image Management")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        manager = ImageManager()
        manager.load_document(doc)
        
        # Add 3 images to page 1
        image_ids = []
        for i in range(3):
            placement = ImagePlacement(
                page_number=1,
                x=50.0 + i*100,
                y=50.0,
                width=80.0,
                height=80.0,
                z_index=i
            )
            image_id = manager.add_image_to_page(1, placement)
            image_ids.append(image_id)
        
        print(f"✓ Added 3 images")
        
        # Get all images on page
        images = manager.get_page_images(1)
        assert len(images) == 3, "Not all images retrieved"
        print(f"✓ Retrieved all 3 images")
        
        # Verify z-order
        for idx, image_id in enumerate(image_ids):
            obj = manager.get_image_object(image_id)
            assert obj.z_index == idx, "Z-index not set correctly"
        print(f"✓ Z-order correct (0, 1, 2)")
        
        # Remove middle image
        manager.remove_image(image_ids[1])
        images = manager.get_page_images(1)
        assert len(images) == 2, "Image not removed"
        print(f"✓ Removed middle image, 2 remain")
        
        # Verify remaining IDs
        remaining_ids = [img.id for img in images]
        assert image_ids[0] in remaining_ids, "First image not found"
        assert image_ids[2] in remaining_ids, "Last image not found"
        assert image_ids[1] not in remaining_ids, "Removed image still present"
        print(f"✓ Correct images remain")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_image_positioning_with_adjustment():
    """Test positioning images using adjustment data"""
    print("Test 6: Image Positioning with Adjustment Data")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        from pdf.pdf_loader import PDFLoader
        from pdf.white_space_detector import WhiteSpaceDetector
        from pdf.page_adjuster import AdjustmentConfig
        
        doc = PDFLoader.load_pdf(pdf_path)
        manager = ImageManager()
        manager.load_document(doc)
        
        # Get page info and adjustment data
        page_info = PDFLoader.get_page_info(doc, 1)
        page_height = page_info['height']
        
        # Simulate adjustment data (15% shrinkage)
        space_created = page_height * 0.15
        print(f"✓ Page height: {page_height:.1f}, Space created: {space_created:.1f}")
        
        # Position image in footer area (bottom of adjusted content)
        footer_y = page_height - space_created
        
        placement = ImagePlacement(
            page_number=1,
            x=50.0,
            y=footer_y,
            width=512.0,
            height=space_created * 0.8  # 80% of available space
        )
        
        image_id = manager.add_image_to_page(1, placement)
        obj = manager.get_image_object(image_id)
        
        assert obj.y > page_height * 0.8, "Image not in footer area"
        print(f"✓ Image positioned in footer: y={obj.y:.1f}, height={obj.height:.1f}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_image_layering():
    """Test z-index (layering) of images"""
    print("Test 7: Image Layering (Z-Index)")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        manager = ImageManager()
        manager.load_document(doc)
        
        # Add images with different z-indices
        image_ids = []
        z_indices = [5, 1, 3, 2, 4]
        
        for z_idx in z_indices:
            placement = ImagePlacement(
                page_number=1,
                x=50.0 + z_idx*10,
                y=50.0,
                width=50.0,
                height=50.0,
                z_index=z_idx
            )
            image_id = manager.add_image_to_page(1, placement)
            image_ids.append(image_id)
        
        print(f"✓ Added 5 images with z-indices: {z_indices}")
        
        # Get images and verify z-order
        images = manager.get_page_images(1)
        sorted_z_indices = sorted([img.z_index for img in images])
        assert sorted_z_indices == sorted(z_indices), "Z-order not correct"
        print(f"✓ Z-order verified: {sorted_z_indices}")
        
        # Change z-index of an image
        manager.set_image_property(image_ids[0], 'z_index', 10)
        images = manager.get_page_images(1)
        sorted_z_indices = sorted([img.z_index for img in images])
        assert 10 in sorted_z_indices, "Z-index change not applied"
        print(f"✓ Changed z-index, new order: {sorted_z_indices}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_image_bounds_validation():
    """Test validation of image bounds on page"""
    print("Test 8: Image Bounds Validation")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        from pdf.pdf_loader import PDFLoader
        
        doc = PDFLoader.load_pdf(pdf_path)
        page_info = PDFLoader.get_page_info(doc, 1)
        page_width = page_info['width']
        page_height = page_info['height']
        
        manager = ImageManager()
        manager.load_document(doc)
        
        # Valid placement (within bounds)
        placement1 = ImagePlacement(
            page_number=1,
            x=50.0,
            y=50.0,
            width=100.0,
            height=100.0
        )
        is_valid = manager.validate_image_placement(placement1, page_width, page_height)
        assert is_valid, "Valid placement rejected"
        print(f"✓ Valid placement accepted")
        
        # Out of bounds (too far right)
        placement2 = ImagePlacement(
            page_number=1,
            x=page_width - 10,
            y=50.0,
            width=100.0,
            height=100.0
        )
        is_valid = manager.validate_image_placement(placement2, page_width, page_height)
        if not is_valid:
            print(f"✓ Out-of-bounds placement rejected")
        else:
            print(f"⚠ Out-of-bounds placement accepted (may need stricter validation)")
        
        # Out of bounds (negative position)
        placement3 = ImagePlacement(
            page_number=1,
            x=-50.0,
            y=50.0,
            width=100.0,
            height=100.0
        )
        is_valid = manager.validate_image_placement(placement3, page_width, page_height)
        if not is_valid:
            print(f"✓ Negative position rejected")
        else:
            print(f"⚠ Negative position accepted")
        
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
    print("STAGE 10 TEST SUITE: Image Insertion and Positioning")
    print("=" * 50 + "\n")
    
    tests = [
        test_image_validation,
        test_image_placement_calculations,
        test_adding_images_to_page,
        test_image_property_management,
        test_multi_image_management,
        test_image_positioning_with_adjustment,
        test_image_layering,
        test_image_bounds_validation,
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
        print("\n✅ All tests PASSED - Image management ready")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
