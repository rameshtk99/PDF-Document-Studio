using System.Threading;
using PDFDocumentStudio.Core.Interfaces;
using PdfSharp.Drawing;

namespace PDFDocumentStudio.Pdf.Text;

/// <summary>
/// Real font-metrics-backed implementation of <see cref="IFontMetricsProvider"/>, using the same
/// font files PDFsharp will use to draw the exported PDF — so <see cref="Core.TextLayout.TextLayoutEngine"/>
/// wraps text identically for preview and export. See docs/LEGACY_FEATURE_INVENTORY.md §4.
/// </summary>
public sealed class PdfSharpFontMetricsProvider(FontRegistry registry) : IFontMetricsProvider
{
    private readonly Lock _lock = new();
    private readonly XGraphics _measureContext = XGraphics.CreateMeasureContext(
        new XSize(20000, 20000), XGraphicsUnit.Point, XPageDirection.Downwards);

    public double MeasureWidth(string text, string fontName, double fontSize)
    {
        if (string.IsNullOrEmpty(text)) return 0.0;
        try
        {
            lock (_lock)
            {
                var font = new XFont(fontName, fontSize);
                return _measureContext.MeasureString(text, font).Width;
            }
        }
        catch (Exception)
        {
            // Legacy's final fallback rung: a crude estimate so layout degrades rather than throws.
            return text.Length * fontSize * 0.5;
        }
    }

    public bool IsFontAvailable(string fontName) => registry.FontsByDisplayName.ContainsKey(fontName);

    public IReadOnlyList<string> AvailableFontNames => registry.FontsByDisplayName.Keys.OrderBy(n => n).ToList();
}
