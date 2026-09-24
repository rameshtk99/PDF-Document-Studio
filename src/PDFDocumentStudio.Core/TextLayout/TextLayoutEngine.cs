using System.Text;
using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.TextLayout;

/// <summary>One laid-out line of text, positioned relative to the text box's top-left corner.</summary>
public readonly record struct LaidOutLine(string Text, double X, double BaselineFromTop, double Width);

public sealed record TextLayoutResult(IReadOnlyList<LaidOutLine> Lines, double ContentWidth, double ContentHeight);

/// <summary>
/// The single shared line-breaking/measurement authority. Every renderer (Avalonia canvas preview,
/// marquee snippet raster, PDF export) must consume this engine's output rather than re-measuring
/// or re-wrapping independently — that duplication is exactly what caused preview/export drift in
/// the legacy app before it was consolidated. See docs/LEGACY_FEATURE_INVENTORY.md §4.
/// </summary>
public sealed class TextLayoutEngine(IFontMetricsProvider metrics)
{
    /// <summary>Baseline-from-cap-height approximation used everywhere in this engine — deliberately
    /// not font-metrics-exact (matches the legacy app's own documented approximation).</summary>
    private const double AscentRatio = 0.8;

    public TextLayoutResult Layout(TextStyle rawStyle, double boxWidth)
    {
        var style = rawStyle.Normalized();
        var paragraphs = style.Text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');

        var usableWidth = Math.Max(1.0, boxWidth - 2 * style.Padding);
        var lines = style.AutoSize
            ? paragraphs.ToList() // point text: only explicit newlines break a line, never wraps
            : paragraphs.SelectMany(p => WrapParagraph(p, style.FontName, style.FontSize, usableWidth)).ToList();

        if (lines.Count == 0) lines.Add(string.Empty);

        var lineHeight = style.FontSize * style.LineSpacing;
        var ascent = style.FontSize * AscentRatio;
        var measured = lines.Select(l => (Text: l, Width: metrics.MeasureWidth(l, style.FontName, style.FontSize))).ToList();
        var widest = measured.Count == 0 ? 0.0 : measured.Max(m => m.Width);
        var effectiveWidth = style.AutoSize ? widest : usableWidth;

        var laidOut = new List<LaidOutLine>(measured.Count);
        for (var i = 0; i < measured.Count; i++)
        {
            var (text, width) = measured[i];
            var offset = style.Align switch
            {
                TextAlign.Center => (effectiveWidth - width) / 2.0,
                TextAlign.Right => effectiveWidth - width,
                _ => 0.0,
            };
            laidOut.Add(new LaidOutLine(text, style.Padding + Math.Max(0, offset), style.Padding + i * lineHeight + ascent, width));
        }

        var contentWidth = style.AutoSize ? widest + 2 * style.Padding : boxWidth;
        var contentHeight = measured.Count * lineHeight + 2 * style.Padding;

        return new TextLayoutResult(laidOut, contentWidth, contentHeight);
    }

    /// <summary>Word-wraps one paragraph to <paramref name="usableWidth"/>. A single word wider than
    /// the whole line is split character-by-character so a line never overflows — at least one
    /// character always goes into a chunk, guaranteeing termination.</summary>
    private List<string> WrapParagraph(string paragraph, string fontName, double fontSize, double usableWidth)
    {
        double Width(string s) => metrics.MeasureWidth(s, fontName, fontSize);

        var lines = new List<string>();
        if (paragraph.Length == 0) { lines.Add(string.Empty); return lines; }

        var currentLine = new StringBuilder();

        foreach (var word in paragraph.Split(' '))
        {
            var candidate = currentLine.Length == 0 ? word : currentLine + " " + word;
            if (Width(candidate) <= usableWidth)
            {
                currentLine.Clear();
                currentLine.Append(candidate);
                continue;
            }

            if (currentLine.Length > 0)
            {
                lines.Add(currentLine.ToString());
                currentLine.Clear();
            }

            if (Width(word) <= usableWidth)
            {
                currentLine.Append(word);
                continue;
            }

            // The word alone doesn't fit — split it character by character.
            var chunk = new StringBuilder();
            foreach (var ch in word)
            {
                var candidateChunk = chunk.ToString() + ch;
                if (chunk.Length == 0 || Width(candidateChunk) <= usableWidth)
                {
                    chunk.Append(ch);
                }
                else
                {
                    lines.Add(chunk.ToString());
                    chunk.Clear();
                    chunk.Append(ch);
                }
            }
            currentLine.Append(chunk);
        }

        if (currentLine.Length > 0) lines.Add(currentLine.ToString());
        if (lines.Count == 0) lines.Add(string.Empty);
        return lines;
    }
}
