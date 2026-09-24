using PDFDocumentStudio.Pdf.Text;

namespace PDFDocumentStudio.Tests.Pdf;

[Collection("Pdf")]
public class FontRegistryTests(PdfTestFixture fixture)
{
    [Fact]
    public void DiscoverFonts_OnWindowsBox_FindsAtLeastOneFont()
    {
        Assert.NotEmpty(fixture.FontRegistry.FontsByDisplayName);
        Assert.NotNull(fixture.FontRegistry.FallbackFontName);
    }

    [Fact]
    public void MeasureWidth_LongerTextIsWider()
    {
        var shortWidth = fixture.Metrics.MeasureWidth("hi", fixture.FontRegistry.FallbackFontName!, 12);
        var longWidth = fixture.Metrics.MeasureWidth("hello world", fixture.FontRegistry.FallbackFontName!, 12);
        Assert.True(longWidth > shortWidth);
    }
}
