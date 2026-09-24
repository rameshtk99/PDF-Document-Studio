using PDFDocumentStudio.Pdf.Analysis;
using PDFDocumentStudio.Pdf.Rendering;
using PDFDocumentStudio.Pdf.Text;

namespace PDFDocumentStudio.Tests.Pdf;

public sealed class PdfTestFixture
{
    public FontRegistry FontRegistry { get; }
    public PdfSharpFontMetricsProvider Metrics { get; }
    public PdfPageRasterRenderer Renderer { get; }
    public WhiteSpaceDetector WhiteSpace { get; }
    public string SamplePdfPath { get; } = Path.Combine(AppContext.BaseDirectory, "Assets", "sample.pdf");

    public PdfTestFixture()
    {
        FontRegistry = new FontRegistry();
        FontRegistry.DiscoverFonts();
        FontRegistry.Install();
        Metrics = new PdfSharpFontMetricsProvider(FontRegistry);
        Renderer = new PdfPageRasterRenderer();
        WhiteSpace = new WhiteSpaceDetector(Renderer);
    }
}

[CollectionDefinition("Pdf")]
public sealed class PdfCollection : ICollectionFixture<PdfTestFixture>;
