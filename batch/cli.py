"""
Command-line interface for PDF Document Studio
Preserves all existing CLI functionality
"""

import sys
import os
import argparse
import json
from pdf import FooterGenerator, PDFCompressor, CompressionMode, PDFCompressionError


def run_cli():
    """
    Run in CLI mode to add footer to a PDF.
    
    Usage examples:
      python main.py --input in.pdf --output out.pdf --footer "Left line1|Left line2" --footer "Center1|Center2" --font Arial --size 12
      python main.py --input in.pdf --output out.pdf --footers-file footers.json
    
    footers.json format: [["L1","L2"], ["C1","C2"], ...]
    """
    
    # If the user invoked the script with no CLI arguments and GUI is not available,
    # print guidance and exit cleanly
    if len(sys.argv) <= 1:
        print("\nNo GUI available and no CLI arguments provided.")
        print("To use the GUI install tkinter and restart:")
        print("  sudo apt update && sudo apt install -y python3-tk\n")
        print("Or run the CLI mode with arguments, for example:")
        print('  python main.py --input in.pdf --output out.pdf --footer "Left|Right"\n')
        os._exit(0)
    
    parser = argparse.ArgumentParser(
        description="PDF Document Studio (CLI mode): add footer columns to a PDF, or compress a PDF.")
    parser.add_argument('--input', '-i', required=True, help="Input PDF path")
    parser.add_argument('--output', '-o', required=True, help="Output PDF path")
    parser.add_argument('--footer', action='append', help='Footer column as "line1|line2" (repeat for each column)')
    parser.add_argument('--footers-file', help='Path to JSON file containing list of [line1, line2] pairs')
    parser.add_argument('--font', default='Helvetica', help='Font name (Tk name mapped to ReportLab)')
    parser.add_argument('--size', type=float, default=12.0, help='Font size')
    parser.add_argument('--compress', action='store_true',
                        help='Compress/reduce the size of --input instead of adding a footer')
    parser.add_argument('--max-size-mb', type=float, default=10.0,
                        help='Maximum output size in MB for --compress (upper bound, not a target)')
    parser.add_argument('--compress-mode', choices=[m.value for m in CompressionMode],
                        default=CompressionMode.BALANCED.value,
                        help='Compression mode for --compress')

    args = parser.parse_args()

    if args.compress:
        try:
            result = PDFCompressor().compress(
                args.input, args.output,
                max_size_mb=args.max_size_mb, mode=CompressionMode(args.compress_mode)
            )
            print(f"Original size:   {result.original_size / (1024*1024):.2f} MB")
            print(f"Compressed size: {result.output_size / (1024*1024):.2f} MB")
            print(f"Reduction:       {result.reduction_percent:.1f}%")
            print(f"Pages:           {result.page_count}")
            print(f"Status:          {result.message}")
        except PDFCompressionError as e:
            print(f"Error: {e}", file=sys.stderr)
            os._exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            os._exit(1)
        return

    # Process footer items
    footer_items = []
    
    if args.footers_file:
        try:
            with open(args.footers_file, 'r', encoding='utf-8') as f:
                footer_items = json.load(f)
                # Ensure list of pairs
                footer_items = [(str(a), str(b)) for a, b in footer_items]
        except Exception as e:
            print(f"Could not load footers file: {e}", file=sys.stderr)
            os._exit(1)
    else:
        footer_items = []
        if args.footer:
            for fstr in args.footer:
                parts = fstr.split('|', 1)
                if len(parts) == 1:
                    footer_items.append((parts[0], ""))
                else:
                    footer_items.append((parts[0], parts[1]))
        else:
            print("No footers provided. Use --footer or --footers-file.", file=sys.stderr)
            os._exit(1)
    
    # Add footer to PDF
    try:
        FooterGenerator.add_footer_to_pdf(
            args.input,
            args.output,
            footer_items,
            font_name=args.font,
            font_size=args.size
        )
        print(f"Footer added successfully: {args.output}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        os._exit(1)
