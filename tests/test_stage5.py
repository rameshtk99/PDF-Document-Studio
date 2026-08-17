#!/usr/bin/env python3
"""
Test Suite for Stage 5: Document Model Integration

Tests the document model functionality:
- Document creation and page management
- Page-specific configurations
- Object management
- Global settings and overrides
- Modification tracking
- Project persistence structure
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.models import (
    Document, PageConfig, PageObject, FooterConfig, GlobalSettings
)
from pdf.pdf_loader import PDFLoader


def test_document_creation():
    """Test basic document creation"""
    print("Test 1: Document Creation")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    # Create document
    try:
        doc = Document(pdf_path)
        print(f"✓ Created Document for: {Path(pdf_path).name}")
        
        # Verify initial state
        assert doc.page_count == 0, "Initial page count should be 0"
        assert doc.pdf_path == pdf_path, "PDF path mismatch"
        assert isinstance(doc.global_settings, GlobalSettings), "Missing GlobalSettings"
        assert isinstance(doc.metadata, dict), "Metadata should be dict"
        assert len(doc.page_configs) == 0, "Should have no page configs initially"
        assert not doc.is_modified(), "Should not be modified initially"
        
        print("✓ Initial state validated")
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_page_configuration():
    """Test page configuration management"""
    print("Test 2: Page Configuration Management")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        # Load document with metadata
        doc = PDFLoader.load_pdf(pdf_path)
        print(f"✓ Loaded PDF with {doc.page_count} pages")
        
        # Get default page config (page 1)
        config1 = doc.get_page_config(1)
        assert config1.page_number == 1, "Page number mismatch"
        assert config1.footer_config.enabled, "Footer should be enabled by default"
        assert not config1.overrides_global, "Default config should not override global"
        print("✓ Default page config (page 1) verified")
        
        # Set custom page config (page 2)
        custom_config = PageConfig(page_number=2)
        custom_config.footer_config.font_size = 18
        doc.set_page_config(2, custom_config)
        
        config2 = doc.get_page_config(2)
        assert config2.page_number == 2, "Page number mismatch"
        assert config2.footer_config.font_size == 18, "Font size not updated"
        assert config2.overrides_global, "Should be marked as overriding global"
        assert doc.is_modified(), "Document should be marked as modified"
        print("✓ Custom page config (page 2) set and verified")
        
        # Verify page 1 config unchanged
        config1_again = doc.get_page_config(1)
        assert config1_again.footer_config.font_size == 13, "Page 1 should keep default font size"
        print("✓ Page 1 config unchanged after setting page 2")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_object_management():
    """Test PageObject and object management"""
    print("Test 3: Object Management")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        doc.set_modified(False)  # Reset modified flag
        
        # Create PageObject
        obj1 = PageObject(
            type="image",
            page_number=1,
            x=100, y=200,
            width=200, height=150,
            properties={"path": "stamp.png"}
        )
        print(f"✓ Created PageObject with ID: {obj1.id}")
        
        # Add object to page
        doc.add_object_to_page(1, obj1)
        assert doc.is_modified(), "Should be modified after adding object"
        print("✓ Object added to page 1")
        
        # Verify object in page config
        config = doc.get_page_config(1)
        assert len(config.objects) == 1, "Should have 1 object"
        assert config.objects[0].id == obj1.id, "Object ID mismatch"
        print("✓ Object found in page config")
        
        # Find object by ID
        found_obj = doc.get_object(obj1.id)
        assert found_obj is not None, "Object not found"
        assert found_obj.properties["path"] == "stamp.png", "Properties mismatch"
        print("✓ Object retrieved by ID")
        
        # Add another object
        obj2 = PageObject(
            type="text",
            page_number=2,
            x=50, y=100,
            width=300, height=50,
            properties={"text": "Copyright 2026"}
        )
        doc.add_object_to_page(2, obj2)
        print("✓ Second object added to page 2")
        
        # Remove first object
        doc.remove_object(obj1.id)
        config1 = doc.get_page_config(1)
        assert len(config1.objects) == 0, "Object should be removed from page 1"
        
        # Verify second object still exists
        found_obj2 = doc.get_object(obj2.id)
        assert found_obj2 is not None, "Second object should still exist"
        print("✓ First object removed, second object still exists")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_global_settings():
    """Test global settings and page defaults"""
    print("Test 4: Global Settings")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = Document(pdf_path)
        
        # Verify default global settings
        gs = doc.global_settings
        assert gs.auto_layout, "auto_layout should be True by default"
        assert gs.preserve_original, "preserve_original should be True by default"
        assert gs.allow_page_shrinking, "allow_page_shrinking should be True by default"
        print("✓ Default global settings verified")
        
        # Modify global settings
        gs.footer_config.font_size = 16
        gs.footer_config.font_name = "Arial"
        gs.auto_layout = False
        print("✓ Global settings modified")
        
        # Get page config should use global settings
        config = doc.get_page_config(5)
        assert config.footer_config.font_size == 16, "Should use global font size"
        assert config.footer_config.font_name == "Arial", "Should use global font name"
        assert not config.auto_layout, "Should use global auto_layout setting"
        print("✓ New page config inherits global settings")
        
        # Set page-specific override
        config.footer_config.font_size = 20
        doc.set_page_config(5, config)
        
        # Verify override
        config5 = doc.get_page_config(5)
        assert config5.footer_config.font_size == 20, "Page-specific override not applied"
        assert config5.footer_config.font_name == "Arial", "Should still use global font name"
        print("✓ Page-specific overrides work correctly")
        
        # Verify other pages use global
        config6 = doc.get_page_config(6)
        assert config6.footer_config.font_size == 16, "Page 6 should use global font size"
        print("✓ Global settings still apply to unmodified pages")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_modification_tracking():
    """Test modification flag tracking"""
    print("Test 5: Modification Tracking")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = Document(pdf_path)
        assert not doc.is_modified(), "Should not be modified initially"
        print("✓ Initial: not modified")
        
        # Modify global settings
        doc.global_settings.auto_layout = False
        # Note: This doesn't automatically set modified flag in current design
        print("✓ Global settings can be modified")
        
        # Set page config (should mark as modified)
        config = PageConfig(page_number=1)
        doc.set_page_config(1, config)
        assert doc.is_modified(), "Should be modified after set_page_config"
        print("✓ Modified after setting page config")
        
        # Mark as saved
        doc.set_modified(False)
        assert not doc.is_modified(), "Should not be modified after marking saved"
        print("✓ Modification flag can be reset")
        
        # Add object (should mark as modified)
        obj = PageObject()
        doc.add_object_to_page(1, obj)
        assert doc.is_modified(), "Should be modified after adding object"
        print("✓ Modified after adding object")
        
        # Remove object (should mark as modified)
        doc.set_modified(False)
        doc.remove_object(obj.id)
        assert doc.is_modified(), "Should be modified after removing object"
        print("✓ Modified after removing object")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_project_path():
    """Test project path management"""
    print("Test 6: Project Path Management")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = Document(pdf_path)
        
        # Initially no project path
        assert doc.get_project_path() is None, "Should have no project path initially"
        print("✓ Initially no project path")
        
        # Set project path
        project_file = "my_project.pdfeditor"
        doc.set_project_path(project_file)
        assert doc.get_project_path() == project_file, "Project path not set"
        print(f"✓ Project path set to: {project_file}")
        
        # Update project path
        new_project_file = "updated_project.pdfeditor"
        doc.set_project_path(new_project_file)
        assert doc.get_project_path() == new_project_file, "Project path not updated"
        print(f"✓ Project path updated to: {new_project_file}")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_document_integration():
    """Test Document model works with PDFLoader"""
    print("Test 7: Document + PDFLoader Integration")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        # Load with PDFLoader (returns Document)
        doc = PDFLoader.load_pdf(pdf_path)
        assert isinstance(doc, Document), "PDFLoader should return Document instance"
        print(f"✓ PDFLoader.load_pdf() returns Document")
        
        # Verify metadata is populated
        assert doc.page_count > 0, "Page count should be set by loader"
        assert len(doc.metadata) > 0, "Metadata should be populated by loader"
        print(f"✓ Document metadata populated ({doc.page_count} pages)")
        
        # Can get page configs (should inherit from global)
        for page_num in [1, 2, 5]:
            config = doc.get_page_config(page_num)
            assert config.page_number == page_num, "Page number mismatch"
            assert config.footer_config.enabled, "Footer should be enabled by default"
        print("✓ Page configs work correctly")
        
        # Can modify and track changes
        obj = PageObject(type="watermark", page_number=1)
        doc.add_object_to_page(1, obj)
        assert doc.is_modified(), "Should be modified after adding object"
        print("✓ Can add objects to loaded document")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 50)
    print("STAGE 5 TEST SUITE: Document Model Integration")
    print("=" * 50 + "\n")
    
    tests = [
        test_document_creation,
        test_page_configuration,
        test_object_management,
        test_global_settings,
        test_modification_tracking,
        test_project_path,
        test_document_integration,
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
        print("\n✅ All tests PASSED - Document model is production ready")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
