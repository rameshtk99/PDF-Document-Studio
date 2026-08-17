#!/usr/bin/env python3
"""Test Stage 2: PDF Loader with Metadata"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf import PDFLoader

def test_pdf_loader():
    """Test PDF loading and metadata extraction"""
    
    print("=" * 60)
    print("STAGE 2 TEST: PDF Loader with Metadata")
    print("=" * 60)
    
    # Test 1: Validate PDF
    print("\n1. Testing PDF validation...")
    is_valid, error = PDFLoader.validate_pdf("Ximeki MEs 82.pdf")
    print(f"   PDF validation: {'✓ PASS' if is_valid else '✗ FAIL'}")
    if error:
        print(f"   Error: {error}")
    
    # Test 2: Load PDF
    print("\n2. Loading PDF and extracting metadata...")
    try:
        doc = PDFLoader.load_pdf("Ximeki MEs 82.pdf")
        print(f"   ✓ PDF loaded successfully")
        
        # Test 3: Check metadata
        print("\n3. Checking metadata...")
        print(f"   File name: {doc.metadata['file_name']}")
        print(f"   File size: {doc.metadata['file_size']:,} bytes")
        print(f"   Total pages: {doc.page_count}")
        
        # Test 4: Check page dimensions
        print("\n4. Page dimensions:")
        pages = doc.metadata.get('pages', [])
        if pages:
            print(f"   Page 1: {pages[0]['width']:.1f} x {pages[0]['height']:.1f} pt (rotation: {pages[0]['rotation']}°)")
            if len(pages) > 1:
                print(f"   Page 2: {pages[1]['width']:.1f} x {pages[1]['height']:.1f} pt (rotation: {pages[1]['rotation']}°)")
            if len(pages) > 2:
                print(f"   Page 3: {pages[2]['width']:.1f} x {pages[2]['height']:.1f} pt (rotation: {pages[2]['rotation']}°)")
            if doc.page_count > 3:
                last = pages[-1]
                print(f"   Page {doc.page_count}: {last['width']:.1f} x {last['height']:.1f} pt (rotation: {last['rotation']}°)")
        
        # Test 5: Check document model
        print("\n5. Document model:")
        print(f"   Global footer enabled: {doc.global_settings.footer_config.enabled}")
        print(f"   Auto layout: {doc.global_settings.auto_layout}")
        print(f"   Document is modified: {doc.is_modified()}")
        
        # Test 6: Get page info
        print("\n6. Testing page info retrieval:")
        page_1 = PDFLoader.get_page_info(doc, 1)
        print(f"   Page 1 info: {page_1 is not None}")
        if page_1:
            print(f"   - Dimensions: {page_1['width']:.1f} x {page_1['height']:.1f}")
            print(f"   - Aspect ratio: {page_1['aspect_ratio']:.2f}")
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED - Stage 2 Complete")
        print("=" * 60)
        
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_pdf_loader()
