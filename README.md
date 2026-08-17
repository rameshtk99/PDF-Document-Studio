# PDF Document Studio

A visual PDF editor and CLI toolkit for adding page-by-page footers, placing image stamps, and compressing PDFs — while preserving the original document's text, vectors, and print quality.

---

## What it does

**GUI (default, `python main.py`):**
- **View & navigate** any PDF with a real page preview, thumbnails, and zoom (Fit Page / Fit Width / 100%). Mouse-wheel scrolling flows from one page into the next.
- **Footer editing, two ways**, both with a **live preview drawn directly on the page** and full **undo/redo** — nothing is written to disk until you explicitly export:
  - *Page Settings* tab — a different footer per page (or inherit the global one), with per-page Apply / Reset.
  - *Quick Footer* tab — one flat footer applied to every page at once.
  - Both support up to 5 columns, two lines per column, `{page}`/`{total}` placeholders, custom fonts (including Nepali/Devanagari TTF fonts like Preeti), configurable gap below content, and configurable spacing between a column's two lines.
- **Whitespace-aware, page-by-page footer placement** — each page is analyzed independently:
  - A page with plenty of blank space gets its footer positioned just below its actual content, not stranded at the far bottom edge.
  - A page with too little space gets the *minimum* necessary layout adjustment (content is compressed just enough to fit), leaving pages that already fit untouched.
  - Long footer text auto-shrinks to fit its column instead of overlapping a neighboring column.
- **Image/stamp insertion** — drag, resize via handles, and set exact X/Y/width/height/rotation/opacity, with lock/duplicate/delete.
- **PDF compression** (*File > Compress PDF...*) — reduces file size as much as safely possible without sacrificing readability: a lossless structural pass first, then (only for genuinely image-heavy/scanned pages) adaptive image downsampling/recompression that stops as soon as your chosen maximum size is met. Digital/text pages are never rasterized. A maximum size is always an upper bound, never a target — a small PDF is never padded up to fill it.
- **Project save/reopen** (`.pdfeditor` files) — every page's footer settings, image placements, and layout adjustments round-trip exactly.
- The original, simpler flat-footer form is still available from *Tools > Simple Footer Tool (Classic)*.

**CLI (`python main.py --input ... --output ...`):** unchanged, scriptable footer application and a `--compress` mode, for batch/automation use without the GUI.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
python main.py                    # launches the GUI
```

### CLI examples

Add a footer:
```bash
python main.py --input report.pdf --output report_footer.pdf \
  --footer "Company Name|2024" --footer "Page {page}|of {total}" \
  --font Arial --size 12
```

Compress a PDF (upper size limit, not a target):
```bash
python main.py --input scan.pdf --output scan_small.pdf \
  --compress --max-size-mb 10 --compress-mode balanced
```

Run `python main.py --help`-style guidance by invoking it with no arguments while GUI support is unavailable, or see `batch/cli.py` for the full flag reference.

---

## Project layout

```
pdf-footer-app/
├── main.py              # Entry point (GUI by default, CLI when args are passed)
├── requirements.txt
├── logo.ico              # App icon (title bar + taskbar)
├── app/                  # GUI: main editor window, panels, dialogs, undo commands
│   ├── editor_window.py     # PDFEditorApp -- the main window
│   ├── page_settings.py     # Per-page footer tab
│   ├── quick_footer_panel.py# Flat/global footer tab
│   ├── image_overlay.py     # Canvas drag/resize + image properties panel
│   ├── footer_preview.py    # Live footer preview overlay
│   ├── compress_dialog.py   # Compress PDF dialog
│   ├── document_commands.py # Real undo/redo commands
│   └── gui_app.py           # Classic simple footer form (Tools menu)
├── pdf/                  # PDF engine: loading, footer generation, compression, whitespace analysis
│   ├── pdf_handler.py       # FooterGenerator (legacy + per-page overlay drawing)
│   ├── document_exporter.py # Whitespace-aware, per-page export pipeline
│   ├── pdf_compressor.py    # Size-reduction engine
│   ├── white_space_detector.py
│   └── image_manager.py
├── models/                # Document/Page/FooterConfig/PageObject data model
├── viewer/                # PDF rendering + the Tkinter viewer/thumbnail widget
├── utils/                 # Config, fonts, constants, project (.pdfeditor) save/load
├── batch/                 # CLI argument parsing
├── tests/                 # test_stage*.py regression suite
├── docs/                  # Design specs and stage-by-stage implementation notes
└── output/                # Generated/test-run PDFs (safe to clear)
```

---

## Supported fonts

Standard: Arial, Times New Roman, Courier New, Verdana, Tahoma, Georgia, Calibri.
Nepali/Devanagari: Preeti, Ganesh, Kantipur (place the `.ttf` in the project root; registered automatically at startup).

> Devanagari fonts like Preeti render correctly once typed, but typing Devanagari itself requires a Preeti-layout keyboard — the app can't remap a plain English keyboard's keystrokes into Devanagari glyphs.

---

## Requirements

- Python 3.9+
- `pypdf`, `reportlab`, `PyMuPDF`, `Pillow`, `numpy` (see `requirements.txt`)
- Tkinter for GUI mode (falls back to CLI-only guidance if unavailable)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| GUI won't start / "tkinter not available" | `sudo apt install python3-tk` (Linux) or reinstall Python with Tcl/Tk support (Windows/Mac) |
| Page previews show a gray placeholder | `pip install PyMuPDF` (preferred) or `pdf2image` + Poppler |
| A font isn't in the dropdown | It isn't installed as a system font; install it or place a `.ttf` in the project root for custom fonts |
| Compress PDF says a password-protected file isn't supported | Remove the password first; encrypted PDFs are intentionally rejected rather than guessed at |

---

## Status

Phase 1 (viewer, per-page footers, image placement, undo/redo, project save/load) and the PDF compression module are implemented and wired into one working application — see `docs/IMPLEMENTATION_PROGRESS.md` for the detailed, stage-by-stage build log. Phase 2 (text-box objects, watermarks, header support, templates, guides/rulers, batch-processing UI) has not been started.
