#!/usr/bin/env python3
"""
Stage 13: Project Save/Load Test Suite  
Tests for saving and loading PDF footer projects in .pdfeditor format
"""

import sys
import os
import json
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.models import Document, PageConfig, FooterConfig, PageObject, GlobalSettings
from utils.project_manager import ProjectManager

# Use sample PDF from project root
SAMPLE_PDF = "test2.pdf"


def test_project_manager_initialization():
    """Test ProjectManager initialization"""
    print("Test 1: ProjectManager Initialization")
    print("-" * 50)
    
    try:
        # Test creation without project file
        manager1 = ProjectManager()
        assert manager1.project_file is None, "Project file should be None"
        assert manager1.document is None, "Document should be None"
        print(f"✓ Manager created without project file")
        
        # Test creation with project file
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "test.pdfeditor"
            manager2 = ProjectManager(project_file)
            assert manager2.project_file == project_file, "Project file not set"
            print(f"✓ Manager created with project file")
            
            # Test is_modified flag
            assert not manager2.is_modified(), "Should not be modified initially"
            manager2.mark_modified()
            assert manager2.is_modified(), "Should be modified after mark_modified()"
            print(f"✓ Modification tracking works")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_create_new_project():
    """Test creating a new project from PDF"""
    print("Test 2: Create New Project")
    print("-" * 50)
    
    try:
        manager = ProjectManager()
        
        # Create new project
        doc = manager.new_project(SAMPLE_PDF)
        
        assert doc is not None, "Document not created"
        assert manager.document is not None, "Manager document not set"
        assert doc.pdf_path == SAMPLE_PDF, "PDF path mismatch"
        assert doc.page_count > 0, "Page count not set"
        print(f"✓ Project created: {doc.page_count} pages")
        
        # Verify document structure
        assert isinstance(doc.page_configs, dict), "Page configs not dict"
        assert isinstance(doc.global_settings, GlobalSettings), "Global settings invalid"
        print(f"✓ Document structure valid")
        
        # Verify not modified initially
        assert not manager.is_modified(), "New project marked modified"
        print(f"✓ Project state correct")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_save_and_load_project():
    """Test saving and loading project"""
    print("Test 3: Save and Load Project")
    print("-" * 50)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "test_project.pdfeditor"
            
            # Create and save project
            manager1 = ProjectManager(project_file)
            doc1 = manager1.new_project(SAMPLE_PDF)
            
            # Add page configuration
            page_cfg = PageConfig(page_number=0)
            page_cfg.footer_config = FooterConfig(
                text_columns=[("Stage 13: Save/Load", "")],
                font_name="Arial",
                font_size=11
            )
            doc1.page_configs[0] = page_cfg
            
            # Save project
            assert manager1.save(), "Save failed"
            assert project_file.exists(), "Project file not created"
            print(f"✓ Project saved: {project_file.name}")
            
            # Load project
            manager2 = ProjectManager(project_file)
            doc2 = manager2.load()
            
            assert doc2 is not None, "Document not loaded"
            assert doc2.page_count == doc1.page_count, "Page count mismatch"
            assert doc2.pdf_path == doc1.pdf_path, "PDF path mismatch"
            print(f"✓ Project loaded: {doc2.page_count} pages")
            
            # Verify page configuration
            assert 0 in doc2.page_configs, "Page config not loaded"
            loaded_cfg = doc2.page_configs[0]
            assert loaded_cfg.footer_config.text_columns[0][0] == "Stage 13: Save/Load", "Footer text not preserved"
            assert loaded_cfg.footer_config.font_name == "Arial", "Font not preserved"
            assert loaded_cfg.footer_config.font_size == 11, "Font size not preserved"
            print(f"✓ Page configuration preserved")
            
            # Verify JSON format
            with open(project_file, 'r') as f:
                data = json.load(f)
            assert data['version'] == '1.0', "Version not in file"
            assert 'pdf_path' in data, "PDF path not in file"
            assert 'page_configs' in data, "Page configs not in file"
            print(f"✓ JSON format valid")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_project_with_images():
    """Test saving/loading projects with image objects"""
    print("Test 4: Project with Images")
    print("-" * 50)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "images_project.pdfeditor"
            
            # Create project with images
            manager = ProjectManager(project_file)
            doc = manager.new_project(SAMPLE_PDF)
            
            # Add page with images
            page_cfg = PageConfig(page_number=0)
            
            # Add image objects
            img1 = PageObject(
                id="img_1",
                type="image",
                x=100.0, y=200.0,
                width=150.0, height=120.0,
                opacity=100, z_index=1,
                properties={"source": "image1.png"}
            )
            img2 = PageObject(
                id="img_2",
                type="image",
                x=300.0, y=200.0,
                width=150.0, height=120.0,
                opacity=75, z_index=2,
                properties={"source": "image2.png"}
            )
            
            page_cfg.objects.append(img1)
            page_cfg.objects.append(img2)
            doc.page_configs[0] = page_cfg
            
            # Save project
            assert manager.save(), "Save with images failed"
            print(f"✓ Project with 2 images saved")
            
            # Load and verify
            manager2 = ProjectManager(project_file)
            doc2 = manager2.load()
            
            assert 0 in doc2.page_configs, "Page config not loaded"
            loaded_cfg = doc2.page_configs[0]
            assert len(loaded_cfg.objects) == 2, "Image objects not loaded"
            
            img1_loaded = loaded_cfg.objects[0]
            assert img1_loaded.id == "img_1", "Image 1 ID mismatch"
            assert img1_loaded.x == 100.0, "Image 1 X mismatch"
            assert img1_loaded.y == 200.0, "Image 1 Y mismatch"
            print(f"✓ Image 1 properties preserved")
            
            img2_loaded = loaded_cfg.objects[1]
            assert img2_loaded.id == "img_2", "Image 2 ID mismatch"
            assert img2_loaded.opacity == 75, "Image 2 opacity mismatch"
            assert img2_loaded.z_index == 2, "Image 2 z-index mismatch"
            print(f"✓ Image 2 properties preserved")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_save_as_functionality():
    """Test save_as method"""
    print("Test 5: Save As")
    print("-" * 50)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file1 = Path(tmpdir) / "original.pdfeditor"
            project_file2 = Path(tmpdir) / "copy.pdfeditor"
            
            # Create and save original
            manager = ProjectManager(project_file1)
            doc = manager.new_project(SAMPLE_PDF)
            manager.save()
            
            assert project_file1.exists(), "Original file not created"
            print(f"✓ Original project saved")
            
            # Save as new file
            assert manager.save_as(project_file2), "Save as failed"
            assert project_file2.exists(), "Copy file not created"
            print(f"✓ Project saved to new location")
            
            # Verify both files exist and are valid
            manager3 = ProjectManager(project_file2)
            doc2 = manager3.load()
            assert doc2.page_count == doc.page_count, "Copied project mismatch"
            print(f"✓ Copied project loads correctly")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_project_validation():
    """Test project file validation"""
    print("Test 6: Project Validation")
    print("-" * 50)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test 1: Invalid JSON
            bad_json_file = Path(tmpdir) / "bad.pdfeditor"
            bad_json_file.write_text("{ invalid json }")
            
            manager = ProjectManager(bad_json_file)
            try:
                manager.load()
                assert False, "Should have raised error on bad JSON"
            except json.JSONDecodeError:
                print(f"✓ Invalid JSON detected")
            
            # Test 2: Missing required fields
            incomplete_file = Path(tmpdir) / "incomplete.pdfeditor"
            incomplete_data = {'version': '1.0'}  # Missing required fields
            incomplete_file.write_text(json.dumps(incomplete_data))
            
            manager2 = ProjectManager(incomplete_file)
            try:
                manager2.load()
                assert False, "Should have raised error on incomplete data"
            except ValueError as e:
                print(f"✓ Incomplete data detected: {e}")
            
            # Test 3: Invalid version
            bad_version_file = Path(tmpdir) / "badver.pdfeditor"
            bad_ver_data = {
                'version': '2.0',  # Unsupported version
                'pdf_path': 'test.pdf',
                'page_count': 1,
                'page_configs': {}
            }
            bad_version_file.write_text(json.dumps(bad_ver_data))
            
            manager3 = ProjectManager(bad_version_file)
            try:
                manager3.load()
                assert False, "Should have raised error on unsupported version"
            except ValueError as e:
                print(f"✓ Version validation works: {e}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adjustment_data_persistence():
    """Test persistence of Stage 9 adjustment data"""
    print("Test 7: Adjustment Data Persistence")
    print("-" * 50)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "adjust.pdfeditor"
            
            # Create project with adjustment data
            manager = ProjectManager(project_file)
            doc = manager.new_project(SAMPLE_PDF)
            
            # Add page with adjustment data
            page_cfg = PageConfig(page_number=0)
            page_cfg.adjustment_data = {
                'shrinkage_percent': 15,
                'adjusted_height': 672.0,
                'freed_space': 120.0,
                'direction': 'bottom'
            }
            doc.page_configs[0] = page_cfg
            
            # Save and load
            manager.save()
            print(f"✓ Project with adjustment data saved")
            
            manager2 = ProjectManager(project_file)
            doc2 = manager2.load()
            
            assert 0 in doc2.page_configs, "Page not loaded"
            loaded_cfg = doc2.page_configs[0]
            assert loaded_cfg.adjustment_data is not None, "Adjustment data not preserved"
            
            adjust = loaded_cfg.adjustment_data
            assert adjust['shrinkage_percent'] == 15, "Shrinkage not preserved"
            assert adjust['adjusted_height'] == 672.0, "Height not preserved"
            assert adjust['freed_space'] == 120.0, "Freed space not preserved"
            print(f"✓ Adjustment data preserved across save/load")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_round_trip_consistency():
    """Test round-trip consistency: save → load → save → load"""
    print("Test 8: Round-Trip Consistency")
    print("-" * 50)
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "roundtrip.pdfeditor"
            
            # First save
            manager1 = ProjectManager(project_file)
            doc1 = manager1.new_project(SAMPLE_PDF)
            
            for i in range(min(3, doc1.page_count)):
                cfg = PageConfig(page_number=i)
                cfg.footer_config = FooterConfig(
                    text_columns=[(f"Page {i+1}", "")],
                    font_name="Arial",
                    font_size=10 + i
                )
                doc1.page_configs[i] = cfg
            
            manager1.save()
            print(f"✓ First save complete")
            
            # First load
            manager2 = ProjectManager(project_file)
            doc2 = manager2.load()
            print(f"✓ First load complete")
            
            # Second save (save what we loaded)
            manager2.save()
            print(f"✓ Second save complete")
            
            # Second load
            manager3 = ProjectManager(project_file)
            doc3 = manager3.load()
            print(f"✓ Second load complete")
            
            # Verify consistency
            assert doc1.page_count == doc2.page_count == doc3.page_count, "Page count mismatch"
            
            for i in range(min(3, doc1.page_count)):
                cfg1 = doc1.page_configs.get(i)
                cfg2 = doc2.page_configs.get(i)
                cfg3 = doc3.page_configs.get(i)
                
                if cfg1:
                    assert cfg2 is not None and cfg3 is not None, f"Page {i} config missing"
                    assert cfg2.footer_config.text_columns == cfg1.footer_config.text_columns, f"Page {i} text mismatch"
                    assert cfg3.footer_config.text_columns == cfg1.footer_config.text_columns, f"Page {i} text mismatch after 2nd round"
            
            print(f"✓ Data consistent through round trip")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("STAGE 13 TEST SUITE: Project Save/Load")
    print("=" * 50 + "\n")
    
    tests = [
        test_project_manager_initialization,
        test_create_new_project,
        test_save_and_load_project,
        test_project_with_images,
        test_save_as_functionality,
        test_project_validation,
        test_adjustment_data_persistence,
        test_round_trip_consistency,
    ]
    
    passed = sum(1 for test in tests if test())
    total = len(tests)
    
    print("=" * 50)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 50 + "\n")
    
    if passed == total:
        print("✅ All tests PASSED - Project save/load ready")
        sys.exit(0)
    else:
        print("⚠ Some tests failed - Review and fix")
        sys.exit(1)
