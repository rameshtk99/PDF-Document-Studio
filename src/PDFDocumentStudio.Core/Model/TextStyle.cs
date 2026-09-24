namespace PDFDocumentStudio.Core.Model;

public enum TextAlign { Left, Center, Right }

/// <summary>
/// Complete style/content schema for a text page object. Mirrors the legacy app's
/// normalize_style() contract: every field has a safe default, and a deserializer reading an
/// older/hand-edited project file should repair invalid values (out-of-range size, bad color,
/// unknown alignment) rather than throw, since values may originate from a foreign or older file.
/// </summary>
public sealed record TextStyle
{
    public string Text { get; init; } = string.Empty;
    public string FontName { get; init; } = "Arial";
    public double FontSize { get; init; } = 12.0;

    /// <summary>Hex color, "#RRGGBB".</summary>
    public string Color { get; init; } = "#000000";

    public TextAlign Align { get; init; } = TextAlign.Left;

    /// <summary>Line height as a multiple of <see cref="FontSize"/>.</summary>
    public double LineSpacing { get; init; } = 1.25;

    /// <summary>
    /// True = "point text": never wraps (only explicit newlines break a line), and the object's
    /// box is recomputed to exactly fit its content after every edit, growing downward from a
    /// fixed top edge. False = "paragraph text": word-wrapped to the box width.
    /// </summary>
    public bool AutoSize { get; init; } = true;

    /// <summary>Inset in PDF points applied on all four sides of the text box.</summary>
    public double Padding { get; init; } = 2.0;

    /// <summary>Below this drag size (in either axis, PDF points) a click/drag is treated as point text.</summary>
    public const double MinTextBoxPt = 12.0;

    public TextStyle Normalized()
    {
        var fontSize = FontSize is >= 1.0 and <= 4096.0 ? FontSize : 12.0;
        var padding = Padding is >= 0.0 and <= 256.0 ? Padding : 2.0;
        var lineSpacing = LineSpacing is > 0.0 and <= 10.0 ? LineSpacing : 1.25;
        var color = IsValidHexColor(Color) ? Color : "#000000";
        var fontName = string.IsNullOrWhiteSpace(FontName) ? "Arial" : FontName;

        return this with
        {
            FontSize = fontSize,
            Padding = padding,
            LineSpacing = lineSpacing,
            Color = color,
            FontName = fontName,
        };
    }

    private static bool IsValidHexColor(string? value) =>
        value is { Length: 7 } && value[0] == '#' &&
        value[1..].All(Uri.IsHexDigit);
}
