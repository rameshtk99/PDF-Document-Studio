namespace PDFDocumentStudio.Core.Interfaces;

/// <summary>
/// Text-measurement abstraction the shared layout engine depends on, kept in Core so Core never
/// takes a dependency on a concrete PDF/font library. The Pdf layer supplies the real
/// implementation (backed by the same font metrics used to draw the exported PDF), so preview,
/// marquee capture, and export all wrap text identically — see docs/LEGACY_FEATURE_INVENTORY.md §4.
/// </summary>
public interface IFontMetricsProvider
{
    /// <summary>Width, in PDF points, of <paramref name="text"/> set in <paramref name="fontName"/>
    /// at <paramref name="fontSize"/>. Must degrade gracefully (approximate rather than throw) for
    /// an unresolvable font name.</summary>
    double MeasureWidth(string text, string fontName, double fontSize);

    /// <summary>True if a real, distinct glyph outline is available for this font name (as opposed
    /// to falling back to a generic substitute) — used to decide whether a custom/Nepali font is
    /// actually usable, not just silently substituted.</summary>
    bool IsFontAvailable(string fontName);

    /// <summary>All font names currently resolvable (system + registered custom fonts), for
    /// populating a font picker.</summary>
    IReadOnlyList<string> AvailableFontNames { get; }
}
