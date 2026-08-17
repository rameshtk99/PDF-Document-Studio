#!/usr/bin/env python3
"""
Test Suite for Stage 6: Footer Editor Preservation with Document Model

Tests the footer editor integration with Document model:
- Load PDF into Document model
- Edit footer settings for specific pages
- Preserve settings when switching pages
- Maintain backward compatibility
- Save/load projects with footer settings
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdf.pdf_loader import PDFLoader
from models.models import Document, FooterConfig
from pdf.pdf_handler import FooterGenerator


def test_document_footer_config():
    """Test Document model footer configuration"""
    print("Test 1: Document Footer Configuration")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        # Load PDF
        doc = PDFLoader.load_pdf(pdf_path)
        print(f"✓ Loaded PDF with {doc.page_count} pages")
        
        # Verify global footer config
        assert doc.global_settings.footer_config.enabled, "Footer should be enabled by default"
        assert doc.global_settings.footer_config.font_name == "Helvetica", "Default font should be Helvetica"
        assert doc.global_settings.footer_config.font_size == 13, "Default size should be 13"
        print("✓ Global footer config verified")
        
        # Get default page config (should inherit global)
        config1 = doc.get_page_config(1)
        assert config1.footer_config.enabled, "Page 1 footer should be enabled"
        assert config1.footer_config.font_name == "Helvetica", "Page 1 should inherit global font"
        assert config1.footer_config.font_size == 13, "Page 1 should inherit global size"
        print("✓ Page 1 inherits global footer settings")
        
        # Modify page 1 footer settings
        config1.footer_config.font_name = "Arial"
        config1.footer_config.font_size = 16
        config1.footer_config.text_columns = [("Header 1", "Footer 1"), ("", ""), ("", ""), ("", ""), ("", "")]
        doc.set_page_config(1, config1)
        
        assert doc.is_modified(), "Document should be marked as modified"
        print("✓ Page 1 footer settings modified")
        
        # Verify page 1 has override
        config1_verify = doc.get_page_config(1)
        assert config1_verify.footer_config.font_name == "Arial", "Page 1 font override not working"
        assert config1_verify.footer_config.font_size == 16, "Page 1 size override not working"
        assert config1_verify.footer_config.text_columns[0] == ("Header 1", "Footer 1"), "Text columns not saved"
        print("✓ Page 1 overrides preserved")
        
        # Verify page 2 still uses global
        config2 = doc.get_page_config(2)
        assert config2.footer_config.font_name == "Helvetica", "Page 2 should use global font"
        assert config2.footer_config.font_size == 13, "Page 2 should use global size"
        print("✓ Page 2 unaffected by page 1 changes")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_footer_text_columns():
    """Test footer text columns configuration"""
    print("Test 2: Footer Text Columns Configuration")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Get page config for page 1
        config = doc.get_page_config(1)
        
        # Set 3 columns with specific content
        config.footer_config.text_columns = [
            ("Left Header", "Left Footer"),
            ("Center Header", "Center Footer"),
            ("Right Header", "Right Footer"),
        ]
        doc.set_page_config(1, config)
        
        # Verify
        config_verify = doc.get_page_config(1)
        assert len(config_verify.footer_config.text_columns) == 3, "Should have 3 columns"
        assert config_verify.footer_config.text_columns[0] == ("Left Header", "Left Footer"), "Column 1 mismatch"
        assert config_verify.footer_config.text_columns[1] == ("Center Header", "Center Footer"), "Column 2 mismatch"
        assert config_verify.footer_config.text_columns[2] == ("Right Header", "Right Footer"), "Column 3 mismatch"
        print("✓ 3 footer columns configured correctly")
        
        # Test with 5 columns
        config.footer_config.text_columns = [
            ("Col1", "Footer1"),
            ("Col2", "Footer2"),
            ("Col3", "Footer3"),
            ("Col4", "Footer4"),
            ("Col5", "Footer5"),
        ]
        doc.set_page_config(1, config)
        
        config_verify = doc.get_page_config(1)
        assert len(config_verify.footer_config.text_columns) == 5, "Should have 5 columns"
        print("✓ 5 footer columns configured correctly")
        
        # Test with special characters (page/total placeholders)
        config.footer_config.text_columns = [
            ("Page {page}", "of {total}"),
            ("© 2026", "All Rights"),
        ]
        doc.set_page_config(1, config)
        
        config_verify = doc.get_page_config(1)
        assert "{page}" in config_verify.footer_config.text_columns[0][0], "Placeholder not preserved"
        assert "{total}" in config_verify.footer_config.text_columns[0][1], "Placeholder not preserved"
        print("✓ Placeholders {page} and {total} preserved")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_pages_different_settings():
    """Test different footer settings for different pages"""
    print("Test 3: Multiple Pages with Different Settings")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Page 1: Arial, size 14
        config1 = doc.get_page_config(1)
        config1.footer_config.font_name = "Arial"
        config1.footer_config.font_size = 14
        config1.footer_config.text_columns = [("Page 1", "Header"), ("", ""), ("", ""), ("", ""), ("", "")]
        doc.set_page_config(1, config1)
        print("✓ Configured page 1 (Arial, 14pt)")
        
        # Page 2: Times, size 12
        config2 = doc.get_page_config(2)
        config2.footer_config.font_name = "Times New Roman"
        config2.footer_config.font_size = 12
        config2.footer_config.text_columns = [("Page 2", "Header"), ("", ""), ("", ""), ("", ""), ("", "")]
        doc.set_page_config(2, config2)
        print("✓ Configured page 2 (Times, 12pt)")
        
        # Page 3: Courier, size 10
        config3 = doc.get_page_config(3)
        config3.footer_config.font_name = "Courier New"
        config3.footer_config.font_size = 10
        config3.footer_config.text_columns = [("Page 3", "Header"), ("", ""), ("", ""), ("", ""), ("", "")]
        doc.set_page_config(3, config3)
        print("✓ Configured page 3 (Courier, 10pt)")
        
        # Verify page 1
        v1 = doc.get_page_config(1)
        assert v1.footer_config.font_name == "Arial", "Page 1 font"
        assert v1.footer_config.font_size == 14, "Page 1 size"
        assert v1.footer_config.text_columns[0][0] == "Page 1", "Page 1 text"
        print("✓ Page 1 settings verified")
        
        # Verify page 2
        v2 = doc.get_page_config(2)
        assert v2.footer_config.font_name == "Times New Roman", "Page 2 font"
        assert v2.footer_config.font_size == 12, "Page 2 size"
        assert v2.footer_config.text_columns[0][0] == "Page 2", "Page 2 text"
        print("✓ Page 2 settings verified")
        
        # Verify page 3
        v3 = doc.get_page_config(3)
        assert v3.footer_config.font_name == "Courier New", "Page 3 font"
        assert v3.footer_config.font_size == 10, "Page 3 size"
        assert v3.footer_config.text_columns[0][0] == "Page 3", "Page 3 text"
        print("✓ Page 3 settings verified")
        
        # Verify page 4 uses global
        v4 = doc.get_page_config(4)
        assert v4.footer_config.font_name == "Helvetica", "Page 4 should use global"
        print("✓ Page 4 still uses global settings")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_footer_generation_with_document():
    """Test that FooterGenerator still works with Document model"""
    print("Test 4: Footer Generation with Document Model")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    (project_root / "output").mkdir(exist_ok=True)
    output_path = str(project_root / "output" / "test_stage6_footer_gen.pdf")
    
    try:
        # Load PDF with Document model
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Set footer on all pages via global settings
        doc.global_settings.footer_config.font_name = "Arial"
        doc.global_settings.footer_config.font_size = 14
        doc.global_settings.footer_config.text_columns = [
            ("Stage 6", "Test"),
            ("", ""),
            ("", ""),
            ("", ""),
            ("", ""),
        ]
        
        # Generate footer using global settings
        footer_items = doc.global_settings.footer_config.text_columns
        FooterGenerator.add_footer_to_pdf(
            pdf_path,
            output_path,
            footer_items,
            font_name=doc.global_settings.footer_config.font_name,
            font_size=doc.global_settings.footer_config.font_size
        )
        
        # Verify output file
        assert os.path.exists(output_path), "Output file not created"
        file_size = os.path.getsize(output_path)
        assert file_size > 0, "Output file is empty"
        print(f"✓ PDF generated with footer (size: {file_size} bytes)")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass


def test_footer_config_json_serialization():
    """Test that footer config can be serialized to JSON for project files"""
    print("Test 5: Footer Config JSON Serialization")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    
    try:
        import json
        
        doc = PDFLoader.load_pdf(pdf_path)
        
        # Configure page
        config = doc.get_page_config(1)
        config.footer_config.font_name = "Arial"
        config.footer_config.font_size = 16
        config.footer_config.text_columns = [
            ("Header 1", "Footer 1"),
            ("Header 2", "Footer 2"),
        ]
        doc.set_page_config(1, config)
        
        # Serialize footer config to dict (for JSON)
        footer_dict = {
            "enabled": config.footer_config.enabled,
            "font_name": config.footer_config.font_name,
            "font_size": config.footer_config.font_size,
            "text_columns": config.footer_config.text_columns,
            "left_margin": config.footer_config.left_margin,
            "right_margin": config.footer_config.right_margin,
            "bottom_margin": config.footer_config.bottom_margin,
            "line_gap": config.footer_config.line_gap,
        }
        
        # Convert to JSON string
        json_str = json.dumps(footer_dict, ensure_ascii=False, indent=2)
        assert "Arial" in json_str, "Font name not in JSON"
        assert "Header 1" in json_str, "Text columns not in JSON"
        print("✓ Footer config serialized to JSON")
        
        # Deserialize back
        restored = json.loads(json_str)
        assert restored["font_name"] == "Arial", "Font name not restored"
        assert restored["font_size"] == 16, "Font size not restored"
        # Note: JSON converts tuples to lists, so we compare as lists
        assert restored["text_columns"][0] == ["Header 1", "Footer 1"], "Text columns not restored (note: tuples become lists in JSON)"
        print("✓ Footer config deserialized from JSON")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """Test that old CLI usage still works"""
    print("Test 6: Backward Compatibility")
    print("-" * 50)
    
    pdf_files = list(project_root.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found")
        return False
    
    pdf_path = str(pdf_files[0])
    (project_root / "output").mkdir(exist_ok=True)
    output_path = str(project_root / "output" / "test_stage6_cli_compat.pdf")
    
    try:
        # Use old-style footer generation (without Document model)
        footer_items = [
            ("Old Style", "Footer"),
            ("Works", "Still"),
            ("", ""),
            ("", ""),
            ("", ""),
        ]
        
        FooterGenerator.add_footer_to_pdf(
            pdf_path,
            output_path,
            footer_items,
            font_name="Arial",
            font_size=13
        )
        
        assert os.path.exists(output_path), "Output file not created"
        file_size = os.path.getsize(output_path)
        assert file_size > 0, "Output file is empty"
        print(f"✓ Old-style footer generation works (size: {file_size} bytes)")
        
        # Now load with Document model
        doc = PDFLoader.load_pdf(output_path)
        assert doc.page_count > 0, "Document should load"
        print("✓ Generated PDF loads correctly in Document model")
        
        print("✓ Test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 50)
    print("STAGE 6 TEST SUITE: Footer Editor Preservation")
    print("=" * 50 + "\n")
    
    tests = [
        test_document_footer_config,
        test_footer_text_columns,
        test_multiple_pages_different_settings,
        test_footer_generation_with_document,
        test_footer_config_json_serialization,
        test_backward_compatibility,
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
        print("\n✅ All tests PASSED - Footer preservation is working")
        return True
    else:
        print("\n⚠ Some tests failed - Review and fix")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
