using PDFDocumentStudio.Core.Serialization;
using PDFDocumentStudio.Core.TextLayout;
using PDFDocumentStudio.Features.Documents;
using PDFDocumentStudio.Features.Footer;
using PDFDocumentStudio.Pdf.Analysis;
using PDFDocumentStudio.Pdf.Compression;
using PDFDocumentStudio.Pdf.Export;
using PDFDocumentStudio.Pdf.Loading;
using PDFDocumentStudio.Pdf.Rendering;
using PDFDocumentStudio.Pdf.Text;
using PDFDocumentStudio.Rendering.Caching;

namespace PDFDocumentStudio.App.Services;

/// <summary>Composition root — constructs and wires every backend service the app needs.</summary>
public sealed class AppServices
{
    public FontRegistry FontRegistry { get; }
    public PdfLoader PdfLoader { get; }
    public PdfPageRasterRenderer PageRenderer { get; }
    public PageBitmapCache BitmapCache { get; }
    public DocumentExporter Exporter { get; }
    public PdfCompressor Compressor { get; }
    public ProjectSerializer ProjectSerializer { get; }
    public DocumentWorkspace Workspace { get; }
    public FooterPreviewService FooterPreview { get; }
    public FooterDraftStore FooterDrafts { get; }
    public TextLayoutEngine TextLayout { get; }

    public AppServices()
    {
        FontRegistry = new FontRegistry();
        FontRegistry.DiscoverFonts(AppContext.BaseDirectory);
        FontRegistry.Install();

        var metrics = new PdfSharpFontMetricsProvider(FontRegistry);
        PdfLoader = new PdfLoader();
        PageRenderer = new PdfPageRasterRenderer();
        BitmapCache = new PageBitmapCache(PageRenderer);
        var whiteSpace = new WhiteSpaceDetector(PageRenderer);
        Exporter = new DocumentExporter(whiteSpace, metrics);
        Compressor = new PdfCompressor();
        ProjectSerializer = new ProjectSerializer(PdfLoader);
        Workspace = new DocumentWorkspace(PdfLoader, ProjectSerializer, Exporter, Compressor);
        FooterPreview = new FooterPreviewService(whiteSpace, metrics);
        FooterDrafts = new FooterDraftStore();
        TextLayout = new TextLayoutEngine(metrics);
    }
}
