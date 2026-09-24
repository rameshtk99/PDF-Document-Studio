using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Tests.Core;

public class PageRangeParserTests
{
    [Fact]
    public void Parse_All_ReturnsEveryPage() =>
        Assert.Equal([1, 2, 3, 4, 5], PageRangeParser.Parse("all", 5));

    [Fact]
    public void Parse_Empty_ReturnsEveryPage() =>
        Assert.Equal([1, 2, 3], PageRangeParser.Parse("", 3));

    [Fact]
    public void Parse_MixedCommaAndDashRanges_ReturnsSortedDedupedPages() =>
        Assert.Equal([1, 2, 3, 7, 10, 11, 12], PageRangeParser.Parse("1-3, 7, 10-12, 2", 12));

    [Fact]
    public void Parse_ReversedRange_IsNormalized() =>
        Assert.Equal([5, 6, 7], PageRangeParser.Parse("7-5", 10));

    [Fact]
    public void Parse_OutOfBoundsPages_AreClampedOut() =>
        Assert.Equal([1, 2], PageRangeParser.Parse("1-2, 99", 2));

    [Fact]
    public void Parse_ResolvesToNoValidPages_Throws() =>
        Assert.Throws<FormatException>(() => PageRangeParser.Parse("99", 5));

    [Fact]
    public void Parse_Malformed_Throws() =>
        Assert.Throws<FormatException>(() => PageRangeParser.Parse("abc", 5));
}
