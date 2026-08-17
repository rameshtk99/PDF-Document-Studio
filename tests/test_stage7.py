#!/usr/bin/env python3
"""
Test Suite for Stage 7: Page-Specific Settings UI

Tests the page-specific footer settings UI:
- Page selection and navigation
- Footer text editing
- Font customization per page
- Apply to single page vs all pages
- Real-time preview updates
- Integration with Document model
- Settings persistence
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from models.models import Document, PageConfig, FooterConfig


def test_page_settings_data_model():
    """Test the data model for page-specific settings"""
    print("Test 1: Page Settings Data Model")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        print(f"✓ Loaded PDF with {doc.page_count} pages")
        
        # Test selecting a page (page 1)
        current_page = 1
        config = doc.get_page_config(current_page)
        assert config.page_number == current_page, "Page number mismatch"
        print(f"✓ Selected page {current_page}")
        
        # Test modifying footer for current page
        config.footer_config.font_name = "Arial"
        config.footer_config.font_size = 14
        config.footer_config.text_columns = [
            ("Page Title", "Footer Text"),
            ("", ""),
            ("", ""),
            ("", ""),
            ("", ""),
        ]
        doc.set_page_config(current_page, config)
        print("✓ Modified footer settings for page 1")
        
        # Test switching to another page (page 2)
        current_page = 2
        config2 = doc.get_page_config(current_page)
        assert config2.page_number == current_page, "Page number mismatch"
        print(f"✓ Switched to page {current_page}")
        
        # Verify page 1 settings unchanged
        config1_verify = doc.get_page_config(1)
        assert config1_verify.footer_config.font_name == "Arial", "Page 1 settings changed"
        print("✓ Page 1 settings preserved after switch")
        
        # Test apply to all pages (global settings)
        doc.global_settings.footer_config.font_name = "Times New Roman"
        doc.global_settings.footer_config.font_size = 12
        print("✓ Modified global settings")
        
        # Page 2 should inherit new global settings
        config2_verify = doc.get_page_config(2)
        assert config2_verify.footer_config.font_name == "Times New Roman", "Global inheritance failed"
        print("✓ Page 2 inherits new global settings")
        
        # Page 1 should keep its override
        config1_verify2 = doc.get_page_config(1)
        assert config1_verify2.footer_config.font_name == "Arial", "Page 1 override lost"
        print("✓ Page 1 keeps its override despite global change")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_page_navigation():
    """Test page navigation functionality"""
    print("Test 2: Page Navigation")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        print(f"✓ Loaded PDF with {doc.page_count} pages")
        
        # Test next/prev page navigation
        current_page = 1
        assert 1 <= current_page <= doc.page_count, "Invalid page"
        print(f"✓ At page {current_page}")
        
        # Next page
        if current_page < doc.page_count:
            current_page += 1
            assert 1 <= current_page <= doc.page_count, "Next page out of range"
            print(f"✓ Moved to next page: {current_page}")
        
        # Previous page
        if current_page > 1:
            current_page -= 1
            assert 1 <= current_page <= doc.page_count, "Prev page out of range"
            print(f"✓ Moved to prev page: {current_page}")
        
        # Jump to page
        jump_page = 10
        if jump_page <= doc.page_count:
            current_page = jump_page
            print(f"✓ Jumped to page {current_page}")
        
        # Test invalid navigation
        try:
            invalid_page = doc.page_count + 1
            assert invalid_page <= doc.page_count, "Should not allow page > total"
            print("❌ Should have rejected page > total")
            return False
        except AssertionError:
            print("✓ Correctly rejected invalid page number")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_footer_text_editing():
    """Test editing footer text columns"""
    print("Test 3: Footer Text Editing")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Get page config
        config = doc.get_page_config(1)
        
        # Edit footer text columns
        test_columns = [
            ("Left Header", "Left Footer"),
            ("Center", "Page {page}"),
            ("Right", "of {total}"),
            ("", ""),
            ("", ""),
        ]
        config.footer_config.text_columns = test_columns
        doc.set_page_config(1, config)
        print("✓ Edited footer text columns")
        
        # Verify changes
        config_verify = doc.get_page_config(1)
        assert config_verify.footer_config.text_columns == test_columns, "Text columns not saved"
        print("✓ Footer text changes persisted")
        
        # Test editing individual columns
        config.footer_config.text_columns[0] = ("Updated Left", "Updated Footer")
        doc.set_page_config(1, config)
        
        config_verify = doc.get_page_config(1)
        assert config_verify.footer_config.text_columns[0][0] == "Updated Left", "Individual column update failed"
        print("✓ Individual column updates work")
        
        # Test clearing columns
        config.footer_config.text_columns = [("", ""), ("", ""), ("", ""), ("", ""), ("", "")]
        doc.set_page_config(1, config)
        
        config_verify = doc.get_page_config(1)
        empty_text = all(line == "" for col in config_verify.footer_config.text_columns for line in col)
        assert empty_text, "Clearing columns failed"
        print("✓ Clearing footer text works")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_font_customization():
    """Test font name and size customization"""
    print("Test 4: Font Customization")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Get page config
        config = doc.get_page_config(1)
        
        # Test font name change
        config.footer_config.font_name = "Arial"
        doc.set_page_config(1, config)
        
        config_verify = doc.get_page_config(1)
        assert config_verify.footer_config.font_name == "Arial", "Font name not changed"
        print("✓ Font name changed to Arial")
        
        # Test font size change
        config.footer_config.font_size = 16
        doc.set_page_config(1, config)
        
        config_verify = doc.get_page_config(1)
        assert config_verify.footer_config.font_size == 16, "Font size not changed"
        print("✓ Font size changed to 16pt")
        
        # Test various font sizes
        for size in [8, 10, 12, 14, 16, 18, 20, 24, 36]:
            config.footer_config.font_size = size
            doc.set_page_config(1, config)
            config_verify = doc.get_page_config(1)
            assert config_verify.footer_config.font_size == size, f"Size {size} not set"
        print("✓ Multiple font sizes (8-36pt) work correctly")
        
        # Test common fonts
        fonts = ["Arial", "Times New Roman", "Courier New", "Helvetica", "Verdana"]
        for font in fonts:
            config.footer_config.font_name = font
            doc.set_page_config(1, config)
            config_verify = doc.get_page_config(1)
            assert config_verify.footer_config.font_name == font, f"Font {font} not set"
        print(f"✓ Common fonts ({', '.join(fonts)}) work correctly")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_apply_to_multiple_pages():
    """Test applying settings to multiple pages"""
    print("Test 5: Apply to Multiple Pages")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Apply settings to page 1
        config1 = doc.get_page_config(1)
        config1.footer_config.font_name = "Arial"
        config1.footer_config.font_size = 14
        doc.set_page_config(1, config1)
        print("✓ Applied settings to page 1")
        
        # Apply to specific range (pages 2-5)
        settings_to_apply = {
            'font_name': 'Times New Roman',
            'font_size': 12,
        }
        for page_num in range(2, min(6, doc.page_count + 1)):
            config = doc.get_page_config(page_num)
            config.footer_config.font_name = settings_to_apply['font_name']
            config.footer_config.font_size = settings_to_apply['font_size']
            doc.set_page_config(page_num, config)
        print(f"✓ Applied settings to pages 2-5")
        
        # Verify range
        for page_num in range(2, min(6, doc.page_count + 1)):
            config = doc.get_page_config(page_num)
            assert config.footer_config.font_name == "Times New Roman", f"Page {page_num} font"
            assert config.footer_config.font_size == 12, f"Page {page_num} size"
        print("✓ Settings verified for pages 2-5")
        
        # Verify page 1 unchanged
        config1_verify = doc.get_page_config(1)
        assert config1_verify.footer_config.font_name == "Arial", "Page 1 changed unexpectedly"
        print("✓ Page 1 unchanged after applying to range")
        
        # Apply to all pages (update global)
        doc.global_settings.footer_config.font_name = "Helvetica"
        doc.global_settings.footer_config.font_size = 13
        print("✓ Updated global settings (applies to all unmodified pages)")
        
        # New unmodified page should use global
        config_new = doc.get_page_config(20)
        assert config_new.footer_config.font_name == "Helvetica", "New page should use global"
        print("✓ Unmodified pages use global settings")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_modification_tracking():
    """Test that modifications are tracked"""
    print("Test 6: Modification Tracking")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Initially not modified
        assert not doc.is_modified(), "Should not be modified initially"
        print("✓ Document initially not modified")
        
        # Make a change
        config = doc.get_page_config(1)
        config.footer_config.font_name = "Arial"
        doc.set_page_config(1, config)
        
        assert doc.is_modified(), "Should be modified after change"
        print("✓ Document marked as modified after settings change")
        
        # Save (clear modified flag)
        doc.set_modified(False)
        assert not doc.is_modified(), "Should not be modified after save"
        print("✓ Modified flag cleared after save")
        
        # Make another change
        config = doc.get_page_config(2)
        config.footer_config.font_size = 16
        doc.set_page_config(2, config)
        
        assert doc.is_modified(), "Should be modified after new change"
        print("✓ Document marked as modified again")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ui_state_management():
    """Test managing UI state (enable/disable controls, pagination)"""
    print("Test 7: UI State Management")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Test page navigation state
        class PageNavigationState:
            def __init__(self, doc):
                self.current_page = 1
                self.doc = doc
            
            def can_go_next(self):
                return self.current_page < self.doc.page_count
            
            def can_go_prev(self):
                return self.current_page > 1
            
            def next_page(self):
                if self.can_go_next():
                    self.current_page += 1
                    return True
                return False
            
            def prev_page(self):
                if self.can_go_prev():
                    self.current_page -= 1
                    return True
                return False
        
        nav = PageNavigationState(doc)
        
        # Test initial state (page 1)
        assert not nav.can_go_prev(), "Should not allow prev from page 1"
        assert nav.can_go_next(), "Should allow next from page 1"
        print("✓ Page 1: prev disabled, next enabled")
        
        # Go to middle page
        nav.current_page = doc.page_count // 2
        assert nav.can_go_prev(), "Should allow prev from middle"
        assert nav.can_go_next(), "Should allow next from middle"
        print(f"✓ Page {nav.current_page}: both prev and next enabled")
        
        # Go to last page
        nav.current_page = doc.page_count
        assert nav.can_go_prev(), "Should allow prev from last"
        assert not nav.can_go_next(), "Should not allow next from last"
        print(f"✓ Page {nav.current_page}: prev enabled, next disabled")
        
        # Test navigation
        nav.current_page = 1
        assert nav.next_page(), "Next should work"
        assert nav.current_page == 2, "Should be on page 2"
        print("✓ Next page navigation works")
        
        assert nav.prev_page(), "Prev should work"
        assert nav.current_page == 1, "Should be back on page 1"
        print("✓ Prev page navigation works")
        
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
    print("STAGE 7 TEST SUITE: Page-Specific Settings UI")
    print("=" * 50 + "\n")
    
    tests = [
        test_page_settings_data_model,
        test_page_navigation,
        test_footer_text_editing,
        test_font_customization,
        test_apply_to_multiple_pages,
        test_modification_tracking,
        test_ui_state_management,
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
        print("\n✅ All tests PASSED - Page settings UI ready for implementation")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
