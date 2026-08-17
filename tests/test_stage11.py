#!/usr/bin/env python3
"""
Test Suite for Stage 11: Interactive Image Editing

Tests interactive image manipulation functionality:
- Drag-and-drop repositioning
- Resize handle detection and manipulation
- Z-order controls (bring forward, send back, arrange)
- Snap-to-grid alignment
- Visual selection feedback
- Mouse event handling on images
- Multi-image interaction
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from pdf.image_manager import ImageManager, ImagePlacement
from app.image_editor import ImageEditor, ResizeHandle, SelectionBox
from models.models import Document, PageObject


def test_resize_handle_detection():
    """Test detection of resize handles"""
    print("Test 1: Resize Handle Detection")
    print("-" * 50)
    
    try:
        editor = ImageEditor()
        
        # Create selection box at specific position
        selection = SelectionBox(
            x=50.0,
            y=50.0,
            width=200.0,
            height=150.0
        )
        
        # Test corner handles
        corners = selection.get_resize_handles()
        assert len(corners) == 8, "Should have 8 resize handles"
        print(f"✓ Created 8 resize handles: TL, T, TR, R, BR, B, BL, L")
        
        # Verify handle types
        handle_types = [h.handle_type for h in corners]
        expected_types = ['TL', 'T', 'TR', 'R', 'BR', 'B', 'BL', 'L']
        assert all(t in handle_types for t in expected_types), "Missing handle types"
        print(f"✓ All handle types present")
        
        # Verify handle positions
        tl_handle = [h for h in corners if h.handle_type == 'TL'][0]
        br_handle = [h for h in corners if h.handle_type == 'BR'][0]
        
        assert abs(tl_handle.x - 50.0) < 1, "TL handle X incorrect"
        assert abs(br_handle.x - 250.0) < 1, "BR handle X incorrect"
        print(f"✓ Handle positions correct")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mouse_hit_detection():
    """Test hit detection for clicking on images"""
    print("Test 2: Mouse Hit Detection")
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
        editor = ImageEditor()
        
        # Add image to page
        placement = ImagePlacement(
            page_number=1,
            x=100.0,
            y=100.0,
            width=200.0,
            height=150.0
        )
        image_id = manager.add_image_to_page(1, placement)
        
        # Test hit on image center
        hit = editor.get_hit_target(100.0 + 100.0, 100.0 + 75.0, [image_id], manager)
        assert hit is not None, "Should detect hit on image center"
        print(f"✓ Hit detected on image center: {hit}")
        
        # Test hit on image border
        hit = editor.get_hit_target(100.0, 100.0, [image_id], manager)
        assert hit is not None, "Should detect hit on image border"
        print(f"✓ Hit detected on image border")
        
        # Test miss outside image
        hit = editor.get_hit_target(500.0, 500.0, [image_id], manager)
        assert hit is None, "Should not detect hit outside image"
        print(f"✓ No hit detected outside image")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_drag_and_drop():
    """Test drag-and-drop repositioning"""
    print("Test 3: Drag-and-Drop Repositioning")
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
        editor = ImageEditor()
        editor.load_document(doc)
        
        # Add image
        placement = ImagePlacement(
            page_number=1,
            x=100.0,
            y=100.0,
            width=150.0,
            height=100.0
        )
        image_id = manager.add_image_to_page(1, placement)
        editor.set_manager(manager)
        
        # Simulate drag
        editor.start_drag(100.0 + 75.0, 100.0 + 50.0, image_id)
        assert editor.dragging_object == image_id, "Drag not started"
        print(f"✓ Drag started on image")
        
        # Move to new position
        editor.drag_to(200.0, 200.0)
        obj = manager.get_image_object(image_id)
        assert obj.x > 100.0 and obj.y > 100.0, "Image not moved"
        print(f"✓ Image repositioned: ({obj.x}, {obj.y})")
        
        # End drag
        editor.end_drag()
        assert editor.dragging_object is None, "Drag not ended"
        print(f"✓ Drag completed")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_resize_handles_interaction():
    """Test resizing via handles"""
    print("Test 4: Resize Handles Interaction")
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
        editor = ImageEditor()
        editor.load_document(doc)
        
        # Add image
        placement = ImagePlacement(
            page_number=1,
            x=100.0,
            y=100.0,
            width=200.0,
            height=150.0
        )
        image_id = manager.add_image_to_page(1, placement)
        editor.set_manager(manager)
        
        # Detect resize handle
        selection = SelectionBox(100.0, 100.0, 200.0, 150.0)
        handles = selection.get_resize_handles()
        br_handle = [h for h in handles if h.handle_type == 'BR'][0]
        
        # Drag bottom-right corner
        editor.start_resize(br_handle, image_id)
        assert editor.resizing_object == image_id, "Resize not started"
        print(f"✓ Resize started on BR handle")
        
        # Drag to new position
        editor.drag_to(350.0, 300.0)
        obj = manager.get_image_object(image_id)
        assert obj.width > 200.0 and obj.height > 150.0, "Image not resized"
        print(f"✓ Image resized: {obj.width:.1f}×{obj.height:.1f}")
        
        # End resize
        editor.end_drag()
        assert editor.resizing_object is None, "Resize not ended"
        print(f"✓ Resize completed")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_selection_box():
    """Test selection box feedback"""
    print("Test 5: Selection Box Visual Feedback")
    print("-" * 50)
    
    try:
        editor = ImageEditor()
        
        # Create selection
        selection = SelectionBox(50.0, 50.0, 200.0, 150.0)
        assert selection.is_visible == True, "Selection should be visible"
        print(f"✓ Selection box created and visible")
        
        # Get selection bounds
        bounds = selection.get_bounds()
        assert bounds['left'] == 50.0, "Left bound incorrect"
        assert bounds['top'] == 50.0, "Top bound incorrect"
        assert bounds['right'] == 250.0, "Right bound incorrect"
        assert bounds['bottom'] == 200.0, "Bottom bound incorrect"
        print(f"✓ Selection bounds correct")
        
        # Test selection properties
        assert selection.stroke_width == 2.0, "Stroke width not default"
        assert selection.stroke_color == '#0080FF', "Color not default"
        print(f"✓ Selection properties set (stroke={selection.stroke_width}px, color={selection.stroke_color})")
        
        # Update selection position
        selection.move(100.0, 100.0)
        assert selection.x == 100.0, "Selection not moved"
        print(f"✓ Selection moved to (100.0, 100.0)")
        
        # Resize selection
        selection.resize(250.0, 200.0)
        assert selection.width == 250.0 and selection.height == 200.0, "Selection not resized"
        print(f"✓ Selection resized to 250×200")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_z_order_controls():
    """Test z-order manipulation (bring forward, send back)"""
    print("Test 6: Z-Order Controls")
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
        editor = ImageEditor()
        editor.load_document(doc)
        editor.set_manager(manager)
        
        # Add 3 images with z-indices 0, 1, 2
        image_ids = []
        for i in range(3):
            placement = ImagePlacement(
                page_number=1,
                x=50.0 + i*50,
                y=50.0,
                width=100.0,
                height=100.0,
                z_index=i
            )
            image_id = manager.add_image_to_page(1, placement)
            image_ids.append(image_id)
        
        print(f"✓ Added 3 images with z-indices 0, 1, 2")
        
        # Bring forward (middle image from z=1 to z=2)
        editor.bring_forward(image_ids[1])
        obj = manager.get_image_object(image_ids[1])
        assert obj.z_index > 1, "Image not brought forward"
        print(f"✓ Brought middle image forward (z={obj.z_index})")
        
        # Send back (middle image to back)
        editor.send_to_back(image_ids[1])
        obj = manager.get_image_object(image_ids[1])
        assert obj.z_index == 0, "Image not sent to back"
        print(f"✓ Sent image to back (z={obj.z_index})")
        
        # Bring to front
        editor.bring_to_front(image_ids[2])
        obj = manager.get_image_object(image_ids[2])
        images = manager.get_page_images(1)
        max_z = max(img.z_index for img in images)
        assert obj.z_index == max_z, "Image not brought to front"
        print(f"✓ Brought image to front (z={obj.z_index})")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_snap_to_grid():
    """Test snap-to-grid alignment"""
    print("Test 7: Snap-to-Grid Alignment")
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
        editor = ImageEditor()
        editor.load_document(doc)
        editor.set_manager(manager)
        
        # Add image
        placement = ImagePlacement(
            page_number=1,
            x=57.0,  # Slightly off grid
            y=63.0,  # Slightly off grid
            width=150.0,
            height=100.0
        )
        image_id = manager.add_image_to_page(1, placement)
        
        # Enable snap-to-grid with 10pt grid
        editor.enable_grid(grid_size=10.0)
        assert editor.grid_enabled == True, "Grid not enabled"
        print(f"✓ Snap-to-grid enabled (10pt grid)")
        
        # Apply snap
        snapped = editor.snap_to_grid(57.0, 63.0)
        assert snapped[0] == 60.0, "X not snapped correctly"
        assert snapped[1] == 60.0, "Y not snapped correctly"
        print(f"✓ Snapped (57, 63) → (60, 60)")
        
        # Snap image position
        editor.snap_object_to_grid(image_id)
        obj = manager.get_image_object(image_id)
        assert obj.x % 10.0 == 0, "X not aligned to grid"
        assert obj.y % 10.0 == 0, "Y not aligned to grid"
        print(f"✓ Image position snapped to ({obj.x}, {obj.y})")
        
        # Disable grid
        editor.enable_grid(enabled=False)
        assert editor.grid_enabled == False, "Grid not disabled"
        print(f"✓ Snap-to-grid disabled")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_select_and_group_operations():
    """Test selecting and operating on multiple images"""
    print("Test 8: Multi-Select and Group Operations")
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
        editor = ImageEditor()
        editor.load_document(doc)
        editor.set_manager(manager)
        
        # Add 3 images
        image_ids = []
        for i in range(3):
            placement = ImagePlacement(
                page_number=1,
                x=50.0 + i*100,
                y=50.0,
                width=80.0,
                height=80.0
            )
            image_id = manager.add_image_to_page(1, placement)
            image_ids.append(image_id)
        
        print(f"✓ Added 3 images")
        
        # Select multiple images
        editor.select_objects(image_ids[:2])
        assert len(editor.selected_objects) == 2, "Not all selected"
        print(f"✓ Selected 2 images")
        
        # Group operations - change opacity for all selected
        for obj_id in editor.selected_objects:
            manager.set_image_property(obj_id, 'opacity', 50.0)
        
        for obj_id in editor.selected_objects:
            obj = manager.get_image_object(obj_id)
            assert obj.opacity == 50.0, "Opacity not changed"
        print(f"✓ Changed opacity for all selected images")
        
        # Deselect all
        editor.deselect_all()
        assert len(editor.selected_objects) == 0, "Objects not deselected"
        print(f"✓ Deselected all objects")
        
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
    print("STAGE 11 TEST SUITE: Interactive Image Editing")
    print("=" * 50 + "\n")
    
    tests = [
        test_resize_handle_detection,
        test_mouse_hit_detection,
        test_drag_and_drop,
        test_resize_handles_interaction,
        test_selection_box,
        test_z_order_controls,
        test_snap_to_grid,
        test_multi_select_and_group_operations,
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
        print("\n✅ All tests PASSED - Interactive image editing ready")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
