using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Core.TextLayout;

namespace PDFDocumentStudio.Tests.Core;

public class TextLayoutEngineTests
{
    private readonly TextLayoutEngine _engine = new(new FakeFontMetricsProvider());

    [Fact]
    public void PointText_NeverWraps_OnlyExplicitNewlinesBreak()
    {
        var style = new TextStyle { Text = "a very long line of text here", AutoSize = true, FontSize = 12 };
        var result = _engine.Layout(style, boxWidth: 20); // far too narrow to fit if wrapping were applied
        Assert.Single(result.Lines);
    }

    [Fact]
    public void PointText_ExplicitNewlineProducesMultipleLines()
    {
        var style = new TextStyle { Text = "line one\nline two", AutoSize = true, FontSize = 12 };
        var result = _engine.Layout(style, boxWidth: 500);
        Assert.Equal(2, result.Lines.Count);
    }

    [Fact]
    public void ParagraphText_WrapsToFitBoxWidth()
    {
        // FakeFontMetrics: width = chars * fontSize * 0.5. FontSize 10 -> 5pt/char.
        var style = new TextStyle { Text = "aaaa bbbb cccc", AutoSize = false, FontSize = 10, Padding = 0 };
        var result = _engine.Layout(style, boxWidth: 25); // ~5 chars per line
        Assert.True(result.Lines.Count > 1);
        Assert.All(result.Lines, l => Assert.True(l.Width <= 25 + 0.01));
    }

    [Fact]
    public void ParagraphText_WordWiderThanLine_SplitsCharacterByCharacter()
    {
        var style = new TextStyle { Text = "supercalifragilistic", AutoSize = false, FontSize = 10, Padding = 0 };
        var result = _engine.Layout(style, boxWidth: 20); // ~2 chars per line
        Assert.True(result.Lines.Count > 1);
        Assert.All(result.Lines, l => Assert.True(l.Width <= 20 + 0.01));
        Assert.Equal("supercalifragilistic", string.Concat(result.Lines.Select(l => l.Text)));
    }

    [Theory]
    [InlineData(TextAlign.Left, 0.0)]
    [InlineData(TextAlign.Right, 10.0)]
    public void Alignment_OffsetsShortLineWithinWiderBox(TextAlign align, double expectedMinOffset)
    {
        var style = new TextStyle { Text = "hi", AutoSize = false, FontSize = 10, Align = align, Padding = 0 };
        var result = _engine.Layout(style, boxWidth: 20); // "hi" = 10pt wide, box = 20pt
        var line = Assert.Single(result.Lines);
        Assert.True(line.X >= expectedMinOffset - 0.01);
    }

    [Fact]
    public void Normalized_RepairsInvalidValuesInsteadOfThrowing()
    {
        var style = new TextStyle { FontSize = -5, Color = "not-a-color" };
        var normalized = style.Normalized();
        Assert.Equal(12.0, normalized.FontSize);
        Assert.Equal("#000000", normalized.Color);
    }
}
