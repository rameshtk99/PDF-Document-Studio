using System.Collections.Concurrent;
using System.Drawing;
using PDFtoImage;
using SkiaSharp;

namespace PDFDocumentStudio.Pdf.Rendering;

/// <summary>
/// Low-level page-to-bitmap rasterizer, backed by PDFium (via PDFtoImage) — the cross-platform
/// replacement for the legacy app's PyMuPDF-based renderer. Used by whitespace analysis, marquee
/// capture, thumbnails, and (wrapped with viewport/tile caching) the Rendering layer's live page
/// view. See docs/LEGACY_FEATURE_INVENTORY.md §2 for the DPI conventions this mirrors: 150 DPI
/// main canvas, 24 DPI thumbnails, 150 DPI whitespace analysis, 200 DPI marquee capture.
/// </summary>
public sealed class PdfPageRasterRenderer
{
    public const double MainCanvasDpi = 150.0;
    public const double ThumbnailDpi = 24.0;
    public const double WhitespaceAnalysisDpi = 150.0;
    public const double MarqueeCaptureDpi = 200.0;

    private readonly ConcurrentDictionary<string, byte[]> _fileBytesCache = new();

    /// <summary>Renders one page at the given DPI. <paramref name="boundsInPoints"/>, if given,
    /// renders only that PDF-point-space region (used by the tile cache to render a viewport slice
    /// instead of a whole large page) with the DPI applied to the bounds rather than the full page.</summary>
    public SKBitmap RenderPage(string sourcePath, int pageIndex, double dpi, RectangleF? boundsInPoints = null)
    {
        var options = new RenderOptions(
            Dpi: (int)Math.Round(dpi),
            Bounds: boundsInPoints,
            DpiRelativeToBounds: boundsInPoints.HasValue,
            AntiAliasing: PdfAntiAliasing.All);

        return Conversion.ToImage(GetBytes(sourcePath), pageIndex, password: string.Empty, options: options);
    }

    public SizeF GetPageSize(string sourcePath, int pageIndex) =>
        Conversion.GetPageSize(GetBytes(sourcePath), pageIndex, password: string.Empty);

    public int GetPageCount(string sourcePath) => Conversion.GetPageCount(GetBytes(sourcePath), password: string.Empty);

    /// <summary>Drops the cached bytes for a source file — call if the file on disk may have changed.</summary>
    public void Invalidate(string sourcePath) => _fileBytesCache.TryRemove(sourcePath, out _);

    private byte[] GetBytes(string sourcePath) => _fileBytesCache.GetOrAdd(sourcePath, File.ReadAllBytes);
}
