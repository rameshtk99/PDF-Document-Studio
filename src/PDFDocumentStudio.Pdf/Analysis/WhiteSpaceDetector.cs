using System.Collections.Concurrent;
using PDFDocumentStudio.Pdf.Rendering;
using SkiaSharp;

namespace PDFDocumentStudio.Pdf.Analysis;

/// <summary>
/// Detects how much blank space exists below a page's actual content, so the footer engine
/// (<see cref="Core.Layout.FooterLayoutCalculator"/>) can place the footer relative to real
/// content rather than the raw page edge. Ports the legacy algorithm exactly: a row counts as
/// "content" if the FRACTION of dark pixels in it exceeds a threshold — not the row's mean
/// brightness, which under-detects a single thin text line. See docs/LEGACY_FEATURE_INVENTORY.md §3.
/// </summary>
public sealed class WhiteSpaceDetector(PdfPageRasterRenderer renderer)
{
    private const int WhiteThreshold = 240;
    private const double MinDarkFraction = 0.003;

    // A source page's own content never changes, so the result is safe to cache indefinitely —
    // callers like the live footer editor re-invoke this on every keystroke and must not re-render
    // the whole page each time.
    private readonly ConcurrentDictionary<(string SourcePath, int PageIndex), double> _cache = new();

    /// <summary>Fraction (0.0-1.0) of the page height that is blank below the last row of ink.
    /// 1.0 for a page with no detected content at all.</summary>
    public double AnalyzeContentBottomFraction(string sourcePath, int pageIndex) =>
        _cache.GetOrAdd((sourcePath, pageIndex), key =>
        {
            using var bitmap = renderer.RenderPage(key.SourcePath, key.PageIndex, PdfPageRasterRenderer.WhitespaceAnalysisDpi);
            return AnalyzeBitmap(bitmap);
        });

    internal static double AnalyzeBitmap(SKBitmap bitmap)
    {
        var width = bitmap.Width;
        var height = bitmap.Height;
        if (width == 0 || height == 0) return 1.0;

        var pixels = bitmap.Bytes;
        var bpp = bitmap.BytesPerPixel;
        var rowBytes = bitmap.RowBytes;
        if (bpp < 3) return 1.0; // unexpected format — degrade to "treat as blank" rather than throw

        var lastDarkRow = -1;
        for (var y = 0; y < height; y++)
        {
            var rowStart = y * rowBytes;
            var darkCount = 0;
            for (var x = 0; x < width; x++)
            {
                var idx = rowStart + x * bpp;
                if (idx + 2 >= pixels.Length) break;
                var luminance = (pixels[idx] + pixels[idx + 1] + pixels[idx + 2]) / 3;
                if (luminance < WhiteThreshold) darkCount++;
            }
            if ((double)darkCount / width > MinDarkFraction) lastDarkRow = y;
        }

        if (lastDarkRow < 0) return 1.0;
        return (double)(height - 1 - lastDarkRow) / height;
    }
}
