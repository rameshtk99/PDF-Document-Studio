using PDFDocumentStudio.Core.Interfaces;

namespace PDFDocumentStudio.Tests.Core;

/// <summary>Deterministic width model (0.5em per character) so layout tests don't depend on a real font engine.</summary>
public sealed class FakeFontMetricsProvider : IFontMetricsProvider
{
    public double MeasureWidth(string text, string fontName, double fontSize) => text.Length * fontSize * 0.5;
    public bool IsFontAvailable(string fontName) => true;
    public IReadOnlyList<string> AvailableFontNames => ["Fake"];
}
