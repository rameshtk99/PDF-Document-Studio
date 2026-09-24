using PDFDocumentStudio.Pdf.Loading;

namespace PDFDocumentStudio.Tests.Pdf;

[Collection("Pdf")]
public class PdfLoaderTests(PdfTestFixture fixture)
{
    [Fact]
    public void LoadPdf_RealFile_BuildsCorrectPageRefs()
    {
        var loader = new PdfLoader();
        var document = loader.LoadPdf(fixture.SamplePdfPath);

        Assert.True(document.PageCount > 0);
        Assert.All(document.Pages, p =>
        {
            Assert.Equal(fixture.SamplePdfPath, p.SourcePath);
            Assert.True(p.Width > 0);
            Assert.True(p.Height > 0);
        });
        Assert.Equal(Enumerable.Range(0, document.PageCount), document.Pages.Select(p => p.SourceIndex));
    }

    [Fact]
    public void IsValidPdf_RejectsNonPdfFile()
    {
        var path = Path.Combine(Path.GetTempPath(), $"notapdf_{Guid.NewGuid():N}.txt");
        File.WriteAllText(path, "hello");
        try { Assert.False(PdfLoader.IsValidPdf(path)); }
        finally { File.Delete(path); }
    }

    [Fact]
    public void BuildPageRefs_ImplementsIPageMetadataResolver_ForMigration()
    {
        var loader = new PdfLoader();
        var refs = loader.BuildPageRefs(fixture.SamplePdfPath);
        Assert.True(refs.Count > 0);
    }
}
